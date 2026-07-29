import json
import threading
import time
from collections import deque

import requests
import websocket

from config import (
    SYMBOL,
    CANDLE_INTERVAL,
    HISTORY_LIMIT,
    BINANCE_REST_URL,
    BINANCE_WS_URL
)


# ============================================================
# MARKET SERVICE
# ============================================================

class MarketService:

    def __init__(self):

        # ----------------------------------------------------
        # Market state
        # ----------------------------------------------------

        self.current_price = None

        self.current_price_time = None

        self.current_candle = None

        self.candles = []


        # ----------------------------------------------------
        # Recent trades
        #
        # Stores:
        #
        # {
        #     "price": 118250.50,
        #     "time": 1785315337250
        # }
        #
        # Needed later for accurate settlement.
        # ----------------------------------------------------

        self.recent_trades = deque(
            maxlen=10000
        )


        # ----------------------------------------------------
        # Thread safety
        # ----------------------------------------------------

        self.lock = threading.RLock()


        # ----------------------------------------------------
        # WebSocket state
        # ----------------------------------------------------

        self.ws = None

        self.worker_thread = None

        self.running = False

        self.connected = False


        # ----------------------------------------------------
        # Event listeners
        #
        # Other parts of our backend can subscribe to
        # realtime market updates.
        # ----------------------------------------------------

        self.listeners = []


    # ========================================================
    # LOAD HISTORICAL CANDLES
    # ========================================================

    def load_history(self):

        print(
            f"Loading {SYMBOL} market history..."
        )

        try:

            response = requests.get(
                BINANCE_REST_URL,
                params={
                    "symbol": SYMBOL,
                    "interval": CANDLE_INTERVAL,
                    "limit": HISTORY_LIMIT
                },
                timeout=10
            )

            response.raise_for_status()

            raw_candles = response.json()


            formatted = []


            for candle in raw_candles:

                formatted.append({

                    # Binance gives milliseconds.
                    # Lightweight Charts uses seconds.
                    "time":
                        int(candle[0] / 1000),

                    "open":
                        float(candle[1]),

                    "high":
                        float(candle[2]),

                    "low":
                        float(candle[3]),

                    "close":
                        float(candle[4])

                })


            if not formatted:

                raise RuntimeError(
                    "Binance returned no candles."
                )


            with self.lock:

                self.candles = formatted


                # Latest Binance REST candle is normally
                # the currently active candle.

                self.current_candle = (
                    formatted[-1].copy()
                )


                self.current_price = float(
                    self.current_candle["close"]
                )


            print(
                f"Loaded {len(formatted)} candles."
            )

            print(
                f"Initial price: {self.current_price}"
            )


            return True


        except Exception as error:

            print(
                "Failed to load market history:",
                error
            )

            return False


    # ========================================================
    # PROCESS REAL BINANCE TRADE
    # ========================================================

    def process_trade(
        self,
        price,
        trade_time_ms
    ):

        price = float(price)

        trade_time_ms = int(
            trade_time_ms
        )


        # Binance timestamp:
        #
        # 1785315337250 milliseconds
        #
        # Convert to seconds for chart.

        timestamp_seconds = (
            trade_time_ms // 1000
        )


        # Beginning of the corresponding minute.
        #
        # Example:
        #
        # 14:32:47
        #
        # becomes:
        #
        # 14:32:00

        minute_timestamp = (
            timestamp_seconds // 60
        ) * 60


        with self.lock:

            # ------------------------------------------------
            # Store authoritative latest price
            # ------------------------------------------------

            self.current_price = price

            self.current_price_time = (
                trade_time_ms
            )


            # ------------------------------------------------
            # Save timestamped Binance trade
            # ------------------------------------------------

            self.recent_trades.append({

                "price": price,

                "time": trade_time_ms

            })


            # ------------------------------------------------
            # No candle yet
            # ------------------------------------------------

            if self.current_candle is None:

                self.current_candle = {

                    "time":
                        minute_timestamp,

                    "open":
                        price,

                    "high":
                        price,

                    "low":
                        price,

                    "close":
                        price

                }


            # ------------------------------------------------
            # SAME MINUTE
            # ------------------------------------------------

            elif (
                self.current_candle["time"]
                == minute_timestamp
            ):

                self.current_candle["high"] = max(

                    self.current_candle["high"],

                    price

                )


                self.current_candle["low"] = min(

                    self.current_candle["low"],

                    price

                )


                self.current_candle["close"] = (
                    price
                )


            # ------------------------------------------------
            # NEW MINUTE
            # ------------------------------------------------

            elif (
                minute_timestamp >
                self.current_candle["time"]
            ):

                previous_candle = (
                    self.current_candle.copy()
                )


                # --------------------------------------------
                # Store completed previous candle
                # --------------------------------------------

                if self.candles:

                    if (
                        self.candles[-1]["time"]
                        == previous_candle["time"]
                    ):

                        self.candles[-1] = (
                            previous_candle
                        )

                    else:

                        self.candles.append(
                            previous_candle
                        )

                else:

                    self.candles.append(
                        previous_candle
                    )


                # Keep memory controlled.

                self.candles = (
                    self.candles[-500:]
                )


                # --------------------------------------------
                # Start new candle
                # --------------------------------------------

                self.current_candle = {

                    "time":
                        minute_timestamp,

                    "open":
                        price,

                    "high":
                        price,

                    "low":
                        price,

                    "close":
                        price

                }


            # ------------------------------------------------
            # Ignore an old/out-of-order trade for candle
            #
            # We still keep it in recent_trades.
            # ------------------------------------------------

            else:

                return


            market_event = {

                "type":
                    "market",

                "symbol":
                    SYMBOL,

                "price":
                    self.current_price,

                "price_time":
                    self.current_price_time,

                "candle":
                    self.current_candle.copy()

            }


        # ----------------------------------------------------
        # Notify listeners OUTSIDE lock
        # ----------------------------------------------------

        self._notify_listeners(
            market_event
        )


    # ========================================================
    # BINANCE MESSAGE
    # ========================================================

    def _on_message(
        self,
        ws,
        message
    ):

        try:

            data = json.loads(
                message
            )


            # Binance trade stream:
            #
            # p = price
            # T = trade time

            price = float(
                data["p"]
            )


            trade_time = int(
                data["T"]
            )


            self.process_trade(
                price,
                trade_time
            )


        except Exception as error:

            print(
                "Market message error:",
                error
            )


    # ========================================================
    # BINANCE CONNECTED
    # ========================================================

    def _on_open(
        self,
        ws
    ):

        with self.lock:
            self.connected = True

        print(
            "Binance WebSocket connected.",
            flush=True
        )


    # ========================================================
    # BINANCE ERROR
    # ========================================================

    def _on_error(
        self,
        ws,
        error
    ):

        print(
            "Binance WebSocket error:",
            error
        )


    # ========================================================
    # BINANCE CLOSED
    # ========================================================

    def _on_close(
        self,
        ws,
        close_status_code,
        close_message
    ):

        with self.lock:
            self.connected = False

        print(
            "Binance WebSocket disconnected.",
            "Code:",
            close_status_code,
            "Message:",
            close_message,
            flush=True
        )


    # ========================================================
    # BINANCE WORKER
    # ========================================================

    def _websocket_worker(self):

        while self.running:

            try:

                print(
                    "Connecting to Binance WebSocket:",
                    BINANCE_WS_URL,
                    flush=True
                )

                self.ws = websocket.WebSocketApp(
                    BINANCE_WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )

                print(
                    "Calling WebSocket run_forever()...",
                    flush=True
                )

                self.ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10
                )

                print(
                    "WebSocket run_forever() returned.",
                    flush=True
                )

            except Exception as error:

                with self.lock:
                    self.connected = False

                print(
                    "WebSocket worker exception:",
                    repr(error),
                    flush=True
                )

            if self.running:

                print(
                    "Reconnecting Binance in 3 seconds...",
                    flush=True
                )

                time.sleep(3)


    # ========================================================
    # START MARKET SERVICE
    # ========================================================

    def start(
        self
    ):

        if self.running:

            return


        # ----------------------------------------------------
        # Load historical candles first
        # ----------------------------------------------------

        history_loaded = (
            self.load_history()
        )


        if not history_loaded:

            print(
                "Warning: starting WebSocket "
                "without historical candles."
            )


        self.running = True


        self.worker_thread = threading.Thread(

            target=
                self._websocket_worker,

            daemon=True,

            name="BinanceMarketThread"

        )


        self.worker_thread.start()


        print(
            "Market service started."
        )


    # ========================================================
    # STOP MARKET SERVICE
    # ========================================================

    def stop(
        self
    ):

        self.running = False


        if self.ws:

            try:

                self.ws.close()

            except Exception:

                pass


        print(
            "Market service stopped."
        )


    # ========================================================
    # GET CURRENT PRICE
    # ========================================================

    def get_current_price(
        self
    ):

        with self.lock:

            return self.current_price


    # ========================================================
    # GET CURRENT PRICE + BINANCE TIMESTAMP
    # ========================================================

    def get_current_market_state(
        self
    ):

        with self.lock:

            return {

                "price":
                    self.current_price,

                "price_time":
                    self.current_price_time,

                "connected":
                    self.connected

            }


    # ========================================================
    # GET CURRENT CANDLE
    # ========================================================

    def get_current_candle(
        self
    ):

        with self.lock:

            if (
                self.current_candle
                is None
            ):

                return None


            return (
                self.current_candle.copy()
            )


    # ========================================================
    # GET CHART HISTORY
    # ========================================================

    def get_candles(
        self
    ):

        with self.lock:

            result = [

                candle.copy()

                for candle
                in self.candles

            ]


            # Make sure latest active candle
            # appears correctly.

            if self.current_candle:

                if (
                    result and

                    result[-1]["time"]
                    ==
                    self.current_candle["time"]
                ):

                    result[-1] = (
                        self.current_candle.copy()
                    )

                else:

                    result.append(
                        self.current_candle.copy()
                    )


            return result


    # ========================================================
    # FIND EXPIRY PRICE
    # ========================================================

    def get_first_trade_at_or_after(
        self,
        timestamp_ms
    ):

        """

        Finds the first Binance trade whose
        Binance trade timestamp is >= timestamp_ms.

        Example:

        expiry:
            14:33:17.250

        Binance trades:

            14:33:17.238   $100
            14:33:17.271   $101

        Returns:

            $101 @ 14:33:17.271

        """

        timestamp_ms = int(
            timestamp_ms
        )


        with self.lock:

            for trade in self.recent_trades:

                if (
                    trade["time"]
                    >= timestamp_ms
                ):

                    return (
                        trade.copy()
                    )


        return None


    # ========================================================
    # ADD EVENT LISTENER
    # ========================================================

    def add_listener(
        self,
        callback
    ):

        if callback not in self.listeners:

            self.listeners.append(
                callback
            )


    # ========================================================
    # REMOVE EVENT LISTENER
    # ========================================================

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


    # ========================================================
    # NOTIFY EVENT LISTENERS
    # ========================================================

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
                    "Market listener error:",
                    error
                )


# ============================================================
# GLOBAL MARKET INSTANCE
# ============================================================

market = MarketService()


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    market.start()


    print()
    print(
        "Watching BTCUSDT..."
    )

    print(
        "Press CTRL+C to stop."
    )
    print()


    try:

        while True:

            state = (
                market.get_current_market_state()
            )


            print(

                "Price:",

                state["price"],

                "| Binance time:",

                state["price_time"],

                "| Connected:",

                state["connected"]

            )


            time.sleep(2)


    except KeyboardInterrupt:

        market.stop()
