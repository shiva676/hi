import threading
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL, TRADE_DURATION_SECONDS, DEMO_PAYOUT, MIN_TRADE_AMOUNT, MAX_TRADE_AMOUNT
from services.market import market


class TradingService:
    def __init__(self):
        self.running = False
        self.worker_thread = None
        self.lock = threading.RLock()
        self.listeners = []

    def _get_connection(self):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured.")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)

    def _utc_now(self):
        return datetime.now(timezone.utc).isoformat()

    def open_trade(self, user_id, direction, amount):
        direction = str(direction).upper().strip()
        if direction not in ("UP", "DOWN"):
            return {"success": False, "error": "Invalid direction."}
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"success": False, "error": "Invalid trade amount."}
        if amount < MIN_TRADE_AMOUNT:
            return {"success": False, "error": f"Minimum trade amount is ${MIN_TRADE_AMOUNT:.2f}."}
        if amount > MAX_TRADE_AMOUNT:
            return {"success": False, "error": f"Maximum trade amount is ${MAX_TRADE_AMOUNT:.2f}."}

        state = market.get_current_market_state()
        price = state.get("price")
        price_time = state.get("price_time")
        if price is None:
            return {"success": False, "error": "Market price is unavailable."}
        if price_time is None:
            return {"success": False, "error": "Waiting for live market data."}
        # Do not block trades just because the websocket is reconnecting.
        # A fresh REST price is enough for the demo trade engine.
        if not state.get("connected") and not state.get("socket_connected"):
            return {"success": False, "error": "Live market data is reconnecting. Try again in a moment."}

        entry_price = float(price)
        entry_time = int(price_time)
        expiry_time = entry_time + int(TRADE_DURATION_SECONDS * 1000)
        created_at = self._utc_now()

        with self.lock:
            connection = self._get_connection()
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT id, demo_balance FROM users WHERE id = %s FOR UPDATE", (user_id,))
                user = cursor.fetchone()
                if not user:
                    connection.rollback()
                    return {"success": False, "error": "User not found."}
                balance = float(user["demo_balance"])
                if balance < amount:
                    connection.rollback()
                    return {"success": False, "error": "Insufficient demo balance."}

                new_balance = balance - amount
                cursor.execute(
                    "UPDATE users SET demo_balance = %s, updated_at = %s WHERE id = %s",
                    (new_balance, created_at, user_id),
                )
                cursor.execute(
                    """INSERT INTO demo_trades
                       (user_id, direction, amount, entry_price, exit_price, entry_time,
                        expiry_time, status, result, profit, created_at)
                       VALUES (%s,%s,%s,%s,NULL,%s,%s,'OPEN',NULL,0,%s)
                       RETURNING id""",
                    (user_id, direction, amount, entry_price, entry_time, expiry_time, created_at),
                )
                trade_id = cursor.fetchone()["id"]
                connection.commit()
            except Exception as error:
                connection.rollback()
                print("Open trade database error:", repr(error), flush=True)
                return {"success": False, "error": "Unable to create trade."}
            finally:
                connection.close()

        trade = {
            "id": trade_id, "user_id": user_id, "direction": direction, "amount": amount,
            "entry_price": entry_price, "entry_time": entry_time, "expiry_time": expiry_time,
            "duration": TRADE_DURATION_SECONDS, "status": "OPEN", "balance": new_balance,
        }
        self._notify_listeners({"type": "trade_opened", "user_id": user_id, "trade": trade})
        return {"success": True, "trade": trade}

    def get_open_trades(self, user_id):
        connection = self._get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT * FROM demo_trades WHERE user_id = %s AND status = 'OPEN' ORDER BY expiry_time ASC, id ASC",
                (user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def get_open_trade(self, user_id):
        trades = self.get_open_trades(user_id)
        return trades[0] if trades else None

    def get_trade(self, trade_id):
        connection = self._get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM demo_trades WHERE id = %s", (trade_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def get_trade_history(self, user_id, limit=20):
        try:
            limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            limit = 20
        connection = self._get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM demo_trades WHERE user_id = %s ORDER BY id DESC LIMIT %s", (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _determine_result(self, direction, entry_price, exit_price):
        entry_price, exit_price = float(entry_price), float(exit_price)
        if exit_price == entry_price:
            return "DRAW"
        if direction == "UP":
            return "WIN" if exit_price > entry_price else "LOSS"
        return "WIN" if exit_price < entry_price else "LOSS"

    def settle_trade(self, trade_id):
        with self.lock:
            trade = self.get_trade(trade_id)
            if not trade:
                return {"success": False, "error": "Trade not found."}
            if trade["status"] != "OPEN":
                return {"success": True, "already_settled": True, "trade": trade}

            expiry_time = int(trade["expiry_time"])
            tick = market.get_first_trade_at_or_after(expiry_time)
            if tick is None:
                return {"success": False, "waiting_for_market": True}

            exit_price = float(tick["price"])
            entry_price = float(trade["entry_price"])
            amount = float(trade["amount"])
            result = self._determine_result(trade["direction"], entry_price, exit_price)
            if result == "WIN":
                profit = amount * DEMO_PAYOUT
                credit = amount + profit
            elif result == "DRAW":
                profit = 0.0
                credit = amount
            else:
                profit = -amount
                credit = 0.0

            connection = self._get_connection()
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT status FROM demo_trades WHERE id = %s FOR UPDATE", (trade_id,))
                row = cursor.fetchone()
                if not row or row["status"] != "OPEN":
                    connection.rollback()
                    return {"success": True, "already_settled": True}

                if credit > 0:
                    cursor.execute(
                        "UPDATE users SET demo_balance = demo_balance + %s, updated_at = %s WHERE id = %s",
                        (credit, self._utc_now(), trade["user_id"]),
                    )
                cursor.execute(
                    "UPDATE demo_trades SET exit_price=%s,status='CLOSED',result=%s,profit=%s WHERE id=%s AND status='OPEN'",
                    (exit_price, result, profit, trade_id),
                )
                cursor.execute("SELECT demo_balance FROM users WHERE id=%s", (trade["user_id"],))
                final_balance = float(cursor.fetchone()["demo_balance"])
                connection.commit()
            except Exception as error:
                connection.rollback()
                print("Settlement database error:", repr(error), flush=True)
                return {"success": False, "error": "Settlement failed."}
            finally:
                connection.close()

        settled = {
            **trade, "exit_price": exit_price, "status": "CLOSED", "result": result,
            "profit": profit, "balance": final_balance, "settlement_market_time": int(tick["time"]),
        }
        self._notify_listeners({"type": "trade_settled", "user_id": trade["user_id"], "trade": settled})
        return {"success": True, "trade": settled}

    def _get_expired_trades(self):
        state = market.get_current_market_state()
        market_time = state.get("price_time")
        if market_time is None:
            return []
        connection = self._get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM demo_trades WHERE status='OPEN' AND expiry_time <= %s ORDER BY expiry_time ASC",
                (int(market_time),),
            )
            return [row["id"] for row in cursor.fetchall()]
        finally:
            connection.close()

    def _settlement_worker(self):
        print("Trade settlement engine started.", flush=True)
        while self.running:
            try:
                for trade_id in self._get_expired_trades():
                    self.settle_trade(trade_id)
            except Exception as error:
                print("Settlement worker error:", repr(error), flush=True)
            time.sleep(0.25)

    def start(self):
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._settlement_worker, daemon=True, name="TradeSettlementThread")
        self.worker_thread.start()

    def stop(self):
        self.running = False

    def add_listener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def remove_listener(self, callback):
        try:
            self.listeners.remove(callback)
        except ValueError:
            pass

    def _notify_listeners(self, event):
        for callback in list(self.listeners):
            try:
                callback(event)
            except Exception as error:
                print("Trading listener error:", repr(error), flush=True)


trading = TradingService()
