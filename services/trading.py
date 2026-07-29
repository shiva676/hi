import sqlite3
import threading
import time
from datetime import datetime, timezone

from config import (
    DATABASE_PATH,
    TRADE_DURATION_SECONDS,
    DEMO_PAYOUT,
    MIN_TRADE_AMOUNT,
    MAX_TRADE_AMOUNT
)

from services.market import market


# ============================================================
# TRADING SERVICE
# ============================================================

class TradingService:

    def __init__(self):

        self.running = False

        self.worker_thread = None

        # Prevent two threads from modifying
        # balances/trades simultaneously.
        self.lock = threading.RLock()

        # Event listeners will later allow
        # websocket.py to push trade results
        # to connected users.
        self.listeners = []


    # ========================================================
    # DATABASE CONNECTION
    # ========================================================

    def _get_connection(self):

        connection = sqlite3.connect(
            DATABASE_PATH,
            timeout=10
        )

        connection.row_factory = sqlite3.Row

        return connection


    # ========================================================
    # CURRENT UTC TIME
    # ========================================================

    def _utc_now(self):

        return datetime.now(
            timezone.utc
        ).isoformat()


    # ========================================================
    # OPEN TRADE
    # ========================================================

    def open_trade(
        self,
        user_id,
        direction,
        amount
    ):

        """
        Creates a new demo trade.

        IMPORTANT:

        Frontend does NOT provide:

        - entry price
        - expiry time
        - result
        - balance
        - payout

        Backend determines all of them.
        """

        # ----------------------------------------------------
        # Validate direction
        # ----------------------------------------------------

        direction = str(
            direction
        ).upper().strip()


        if direction not in (
            "UP",
            "DOWN"
        ):

            return {
                "success": False,
                "error": "Invalid direction."
            }


        # ----------------------------------------------------
        # Validate amount
        # ----------------------------------------------------

        try:

            amount = float(
                amount
            )

        except (
            TypeError,
            ValueError
        ):

            return {
                "success": False,
                "error": "Invalid trade amount."
            }


        if amount < MIN_TRADE_AMOUNT:

            return {
                "success": False,
                "error":
                    f"Minimum trade amount is "
                    f"${MIN_TRADE_AMOUNT:.2f}."
            }


        if amount > MAX_TRADE_AMOUNT:

            return {
                "success": False,
                "error":
                    f"Maximum trade amount is "
                    f"${MAX_TRADE_AMOUNT:.2f}."
            }


        # ----------------------------------------------------
        # Get authoritative market state
        # ----------------------------------------------------

        market_state = (
            market.get_current_market_state()
        )


        entry_price = (
            market_state["price"]
        )


        entry_market_time = (
            market_state["price_time"]
        )


        if entry_price is None:

            return {
                "success": False,
                "error":
                    "Market price is unavailable."
            }


        if not market_state["connected"]:

            return {
                "success": False,
                "error":
                    "Market connection is unavailable."
            }


        # ----------------------------------------------------
        # Use Binance's latest trade timestamp
        #
        # This keeps our expiry timeline tied to
        # authoritative market data.
        # ----------------------------------------------------

        if entry_market_time is None:

            return {
                "success": False,
                "error":
                    "Waiting for live market data."
            }


        entry_time = int(
            entry_market_time
        )


        expiry_time = (

            entry_time +

            (
                TRADE_DURATION_SECONDS
                * 1000
            )

        )


        created_at = (
            self._utc_now()
        )


        # ----------------------------------------------------
        # Database transaction
        # ----------------------------------------------------

        with self.lock:

            connection = (
                self._get_connection()
            )


            try:

                # IMMEDIATE prevents another write transaction
                # from modifying the same balance concurrently.

                connection.execute(
                    "BEGIN IMMEDIATE"
                )


                cursor = (
                    connection.cursor()
                )


                # --------------------------------------------
                # Load user
                # --------------------------------------------

                cursor.execute(
                    """
                    SELECT
                        id,
                        demo_balance

                    FROM users

                    WHERE id = ?
                    """,
                    (
                        user_id,
                    )
                )


                user = (
                    cursor.fetchone()
                )


                if user is None:

                    connection.rollback()

                    return {
                        "success": False,
                        "error":
                            "User not found."
                    }


                balance = float(
                    user["demo_balance"]
                )


                # --------------------------------------------
                # Check balance
                # --------------------------------------------

                if balance < amount:

                    connection.rollback()

                    return {
                        "success": False,
                        "error":
                            "Insufficient demo balance."
                    }


                # --------------------------------------------
                # Prototype rule:
                #
                # ONE open trade per user.
                # --------------------------------------------

                cursor.execute(
                    """
                    SELECT id

                    FROM demo_trades

                    WHERE
                        user_id = ?
                        AND status = 'OPEN'

                    LIMIT 1
                    """,
                    (
                        user_id,
                    )
                )


                existing_trade = (
                    cursor.fetchone()
                )


                if existing_trade:

                    connection.rollback()

                    return {
                        "success": False,
                        "error":
                            "You already have an open trade."
                    }


                # --------------------------------------------
                # Deduct stake
                # --------------------------------------------

                new_balance = (
                    balance - amount
                )


                cursor.execute(
                    """
                    UPDATE users

                    SET
                        demo_balance = ?,
                        updated_at = ?

                    WHERE id = ?
                    """,
                    (
                        new_balance,
                        created_at,
                        user_id
                    )
                )


                # --------------------------------------------
                # Create trade
                # --------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO demo_trades
                    (
                        user_id,
                        direction,
                        amount,
                        entry_price,
                        exit_price,
                        entry_time,
                        expiry_time,
                        status,
                        result,
                        profit,
                        created_at
                    )

                    VALUES
                    (
                        ?, ?, ?, ?,
                        NULL,
                        ?, ?,
                        'OPEN',
                        NULL,
                        0,
                        ?
                    )
                    """,
                    (
                        user_id,
                        direction,
                        amount,
                        float(entry_price),
                        entry_time,
                        expiry_time,
                        created_at
                    )
                )


                trade_id = (
                    cursor.lastrowid
                )


                connection.commit()


            except Exception as error:

                connection.rollback()

                print(
                    "Open trade database error:",
                    error
                )

                return {
                    "success": False,
                    "error":
                        "Unable to create trade."
                }


            finally:

                connection.close()


        # ----------------------------------------------------
        # Trade successfully opened
        # ----------------------------------------------------

        trade = {

            "id":
                trade_id,

            "user_id":
                user_id,

            "direction":
                direction,

            "amount":
                amount,

            "entry_price":
                float(entry_price),

            "entry_time":
                entry_time,

            "expiry_time":
                expiry_time,

            "duration":
                TRADE_DURATION_SECONDS,

            "status":
                "OPEN",

            "balance":
                new_balance

        }


        self._notify_listeners({

            "type":
                "trade_opened",

            "user_id":
                user_id,

            "trade":
                trade

        })


        return {
            "success": True,
            "trade": trade
        }


    # ========================================================
    # GET OPEN TRADE
    # ========================================================

    def get_open_trade(
        self,
        user_id
    ):

        connection = (
            self._get_connection()
        )

        cursor = (
            connection.cursor()
        )


        cursor.execute(
            """
            SELECT *

            FROM demo_trades

            WHERE
                user_id = ?
                AND status = 'OPEN'

            ORDER BY id DESC

            LIMIT 1
            """,
            (
                user_id,
            )
        )


        row = (
            cursor.fetchone()
        )


        connection.close()


        if row is None:

            return None


        return dict(
            row
        )


    # ========================================================
    # GET TRADE
    # ========================================================

    def get_trade(
        self,
        trade_id
    ):

        connection = (
            self._get_connection()
        )

        cursor = (
            connection.cursor()
        )


        cursor.execute(
            """
            SELECT *

            FROM demo_trades

            WHERE id = ?
            """,
            (
                trade_id,
            )
        )


        row = (
            cursor.fetchone()
        )


        connection.close()


        if row is None:

            return None


        return dict(
            row
        )


    # ========================================================
    # GET USER TRADE HISTORY
    # ========================================================

    def get_trade_history(
        self,
        user_id,
        limit=20
    ):

        try:

            limit = int(
                limit
            )

        except (
            TypeError,
            ValueError
        ):

            limit = 20


        limit = max(
            1,
            min(
                limit,
                100
            )
        )


        connection = (
            self._get_connection()
        )

        cursor = (
            connection.cursor()
        )


        cursor.execute(
            """
            SELECT *

            FROM demo_trades

            WHERE user_id = ?

            ORDER BY id DESC

            LIMIT ?
            """,
            (
                user_id,
                limit
            )
        )


        rows = (
            cursor.fetchall()
        )


        connection.close()


        return [
            dict(row)
            for row in rows
        ]


    # ========================================================
    # DETERMINE RESULT
    # ========================================================

    def _determine_result(
        self,
        direction,
        entry_price,
        exit_price
    ):

        entry_price = float(
            entry_price
        )

        exit_price = float(
            exit_price
        )


        # ----------------------------------------------------
        # Exact same price
        # ----------------------------------------------------

        if exit_price == entry_price:

            return "DRAW"


        # ----------------------------------------------------
        # UP
        # ----------------------------------------------------

        if direction == "UP":

            if exit_price > entry_price:

                return "WIN"

            return "LOSS"


        # ----------------------------------------------------
        # DOWN
        # ----------------------------------------------------

        if direction == "DOWN":

            if exit_price < entry_price:

                return "WIN"

            return "LOSS"


        raise ValueError(
            "Unknown trade direction."
        )


    # ========================================================
    # SETTLE ONE TRADE
    # ========================================================

    def settle_trade(
        self,
        trade_id
    ):

        """
        Settlement rule:

        Exit price = first Binance trade whose
        Binance trade timestamp is >= expiry_time.
        """

        with self.lock:

            # ------------------------------------------------
            # Load trade
            # ------------------------------------------------

            trade = (
                self.get_trade(
                    trade_id
                )
            )


            if trade is None:

                return {
                    "success": False,
                    "error":
                        "Trade not found."
                }


            if trade["status"] != "OPEN":

                return {
                    "success": True,
                    "already_settled": True,
                    "trade": trade
                }


            expiry_time = int(
                trade["expiry_time"]
            )


            # ------------------------------------------------
            # Ask market.py for FIRST Binance
            # trade at or after expiry.
            # ------------------------------------------------

            expiry_market_trade = (

                market
                .get_first_trade_at_or_after(
                    expiry_time
                )

            )


            # No Binance trade after expiry yet.
            #
            # Do NOT guess.
            # Worker will try again shortly.

            if expiry_market_trade is None:

                return {
                    "success": False,
                    "waiting_for_market": True
                }


            exit_price = float(
                expiry_market_trade["price"]
            )


            settlement_market_time = int(
                expiry_market_trade["time"]
            )


            entry_price = float(
                trade["entry_price"]
            )


            direction = (
                trade["direction"]
            )


            amount = float(
                trade["amount"]
            )


            result = (
                self._determine_result(
                    direction,
                    entry_price,
                    exit_price
                )
            )


            # ------------------------------------------------
            # Calculate payout
            # ------------------------------------------------

            if result == "WIN":

                profit = (
                    amount
                    * DEMO_PAYOUT
                )

                amount_to_credit = (
                    amount
                    + profit
                )


            elif result == "DRAW":

                profit = 0.0

                # Return stake.

                amount_to_credit = (
                    amount
                )


            else:

                # Stake was already deducted
                # when trade opened.

                profit = (
                    -amount
                )

                amount_to_credit = 0.0


            settled_at = (
                self._utc_now()
            )


            connection = (
                self._get_connection()
            )


            try:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )


                cursor = (
                    connection.cursor()
                )


                # --------------------------------------------
                # Re-check trade while holding DB write lock
                # --------------------------------------------

                cursor.execute(
                    """
                    SELECT status

                    FROM demo_trades

                    WHERE id = ?
                    """,
                    (
                        trade_id,
                    )
                )


                status_row = (
                    cursor.fetchone()
                )


                if status_row is None:

                    connection.rollback()

                    return {
                        "success": False,
                        "error":
                            "Trade disappeared."
                    }


                if (
                    status_row["status"]
                    != "OPEN"
                ):

                    connection.rollback()

                    return {
                        "success": True,
                        "already_settled": True
                    }


                # --------------------------------------------
                # Credit winnings/refund
                # --------------------------------------------

                if amount_to_credit > 0:

                    cursor.execute(
                        """
                        UPDATE users

                        SET
                            demo_balance =
                                demo_balance + ?,

                            updated_at = ?

                        WHERE id = ?
                        """,
                        (
                            amount_to_credit,
                            settled_at,
                            trade["user_id"]
                        )
                    )


                # --------------------------------------------
                # Close trade
                # --------------------------------------------

                cursor.execute(
                    """
                    UPDATE demo_trades

                    SET
                        exit_price = ?,
                        status = 'CLOSED',
                        result = ?,
                        profit = ?

                    WHERE
                        id = ?
                        AND status = 'OPEN'
                    """,
                    (
                        exit_price,
                        result,
                        profit,
                        trade_id
                    )
                )


                # --------------------------------------------
                # Get final balance
                # --------------------------------------------

                cursor.execute(
                    """
                    SELECT demo_balance

                    FROM users

                    WHERE id = ?
                    """,
                    (
                        trade["user_id"],
                    )
                )


                balance_row = (
                    cursor.fetchone()
                )


                final_balance = float(
                    balance_row["demo_balance"]
                )


                connection.commit()


            except Exception as error:

                connection.rollback()

                print(
                    "Settlement database error:",
                    error
                )

                return {
                    "success": False,
                    "error":
                        "Settlement failed."
                }


            finally:

                connection.close()


        # ----------------------------------------------------
        # Build result
        # ----------------------------------------------------

        settled_trade = {

            "id":
                trade_id,

            "user_id":
                trade["user_id"],

            "direction":
                direction,

            "amount":
                amount,

            "entry_price":
                entry_price,

            "exit_price":
                exit_price,

            "entry_time":
                trade["entry_time"],

            "expiry_time":
                expiry_time,

            "settlement_market_time":
                settlement_market_time,

            "status":
                "CLOSED",

            "result":
                result,

            "profit":
                profit,

            "balance":
                final_balance

        }


        print(
            f"Trade #{trade_id} settled:",
            result,
            "| Entry:",
            entry_price,
            "| Exit:",
            exit_price
        )


        # Later websocket.py will listen for this.

        self._notify_listeners({

            "type":
                "trade_settled",

            "user_id":
                trade["user_id"],

            "trade":
                settled_trade

        })


        return {
            "success": True,
            "trade": settled_trade
        }


    # ========================================================
    # GET ALL EXPIRED OPEN TRADES
    # ========================================================

    def _get_expired_trades(
        self
    ):

        # ----------------------------------------------------
        # IMPORTANT
        #
        # We compare against latest Binance market timestamp,
        # not browser Date.now().
        # ----------------------------------------------------

        market_state = (
            market.get_current_market_state()
        )


        market_time = (
            market_state["price_time"]
        )


        if market_time is None:

            return []


        connection = (
            self._get_connection()
        )

        cursor = (
            connection.cursor()
        )


        cursor.execute(
            """
            SELECT id

            FROM demo_trades

            WHERE
                status = 'OPEN'
                AND expiry_time <= ?

            ORDER BY expiry_time ASC
            """,
            (
                int(market_time),
            )
        )


        rows = (
            cursor.fetchall()
        )


        connection.close()


        return [
            row["id"]
            for row in rows
        ]


    # ========================================================
    # SETTLEMENT WORKER
    # ========================================================

    def _settlement_worker(
        self
    ):

        print(
            "Trade settlement engine started."
        )


        while self.running:

            try:

                expired_trade_ids = (
                    self._get_expired_trades()
                )


                for trade_id in (
                    expired_trade_ids
                ):

                    self.settle_trade(
                        trade_id
                    )


            except Exception as error:

                print(
                    "Settlement worker error:",
                    error
                )


            # This is NOT the trade timer.
            #
            # Expiry remains the exact stored
            # millisecond timestamp.
            #
            # This only controls how often we look
            # for newly expired trades.

            time.sleep(
                0.10
            )


    # ========================================================
    # START TRADING ENGINE
    # ========================================================

    def start(
        self
    ):

        if self.running:

            return


        self.running = True


        self.worker_thread = (
            threading.Thread(

                target=
                    self._settlement_worker,

                daemon=True,

                name=
                    "TradeSettlementThread"

            )
        )


        self.worker_thread.start()


    # ========================================================
    # STOP TRADING ENGINE
    # ========================================================

    def stop(
        self
    ):

        self.running = False


    # ========================================================
    # EVENT LISTENERS
    # ========================================================

    def add_listener(
        self,
        callback
    ):

        if callback not in self.listeners:

            self.listeners.append(
                callback
            )


    def remove_listener(
        self,
        callback
    ):

        try:

            self.listeners.remove(
                callback
            )

        except ValueError:

            pass


    def _notify_listeners(
        self,
        event
    ):

        for callback in list(
            self.listeners
        ):

            try:

                callback(
                    event
                )

            except Exception as error:

                print(
                    "Trading listener error:",
                    error
                )


# ============================================================
# GLOBAL TRADING INSTANCE
# ============================================================

trading = TradingService()