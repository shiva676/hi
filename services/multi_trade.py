"""Enable multiple simultaneous demo trades while keeping settlement server-side."""

from types import MethodType


def install_multi_trade_support(trading):
    def open_trade(self, user_id, direction, amount):
        from config import TRADE_DURATION_SECONDS, MIN_TRADE_AMOUNT, MAX_TRADE_AMOUNT
        from services.market import market

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
        entry_price = state.get("price")
        entry_market_time = state.get("price_time")
        if entry_price is None:
            return {"success": False, "error": "Market price is unavailable."}
        if not state.get("connected"):
            return {"success": False, "error": "Market connection is unavailable."}
        if entry_market_time is None:
            return {"success": False, "error": "Waiting for live market data."}

        entry_time = int(entry_market_time)
        expiry_time = entry_time + TRADE_DURATION_SECONDS * 1000
        created_at = self._utc_now()

        # FOR UPDATE serializes balance deductions for rapid simultaneous clicks.
        with self.lock:
            connection = self._get_connection()
            try:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT id, demo_balance FROM users WHERE id = %s FOR UPDATE",
                    (user_id,)
                )
                user = cursor.fetchone()
                if user is None:
                    connection.rollback()
                    return {"success": False, "error": "User not found."}

                balance = float(user["demo_balance"])
                if balance < amount:
                    connection.rollback()
                    return {"success": False, "error": "Insufficient demo balance."}

                new_balance = balance - amount
                cursor.execute(
                    "UPDATE users SET demo_balance = %s, updated_at = %s WHERE id = %s",
                    (new_balance, created_at, user_id)
                )
                cursor.execute(
                    """
                    INSERT INTO demo_trades
                    (user_id, direction, amount, entry_price, exit_price,
                     entry_time, expiry_time, status, result, profit, created_at)
                    VALUES (%s, %s, %s, %s, NULL, %s, %s, 'OPEN', NULL, 0, %s)
                    RETURNING id
                    """,
                    (user_id, direction, amount, float(entry_price), entry_time,
                     expiry_time, created_at)
                )
                trade_id = cursor.fetchone()["id"]
                connection.commit()
            except Exception as error:
                connection.rollback()
                print("Open multi-trade database error:", error, flush=True)
                return {"success": False, "error": "Unable to create trade."}
            finally:
                connection.close()

        trade = {
            "id": trade_id,
            "user_id": user_id,
            "direction": direction,
            "amount": amount,
            "entry_price": float(entry_price),
            "entry_time": entry_time,
            "expiry_time": expiry_time,
            "duration": TRADE_DURATION_SECONDS,
            "status": "OPEN",
            "balance": new_balance
        }
        self._notify_listeners({"type": "trade_opened", "user_id": user_id, "trade": trade})
        return {"success": True, "trade": trade}

    trading.open_trade = MethodType(open_trade, trading)
    print("Multiple simultaneous demo trades enabled.", flush=True)
