import json
import threading
import time
from collections import deque

import requests
import websocket

from config import SYMBOL, CANDLE_INTERVAL, HISTORY_LIMIT, BINANCE_REST_URL, BINANCE_WS_URL


class MarketService:
    """Live Binance market feed with an automatic REST fallback.

    Binance WebSocket is the primary feed.  A small watchdog refreshes the
    latest 1m candle through REST whenever the socket is stale, which keeps the
    Render deployment usable even when an outbound WebSocket is interrupted.
    """

    def __init__(self):
        self.current_price = None
        self.current_price_time = None
        self.current_candle = None
        self.candles = []
        self.recent_trades = deque(maxlen=10000)

        self.lock = threading.RLock()
        self.listeners = []
        self.ws = None
        self.worker_thread = None
        self.fallback_thread = None
        self.running = False
        self.socket_connected = False
        self.last_update_monotonic = 0.0
        self.http = requests.Session()

    def _format_candle(self, row):
        return {
            "time": int(int(row[0]) / 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
        }

    def load_history(self):
        print(f"Loading {SYMBOL} market history...", flush=True)
        try:
            response = self.http.get(
                BINANCE_REST_URL,
                params={"symbol": SYMBOL, "interval": CANDLE_INTERVAL, "limit": HISTORY_LIMIT},
                timeout=8,
            )
            response.raise_for_status()
            formatted = [self._format_candle(row) for row in response.json()]
            if not formatted:
                raise RuntimeError("Binance returned no candles")

            now_ms = int(time.time() * 1000)
            with self.lock:
                self.candles = formatted[-HISTORY_LIMIT:]
                self.current_candle = formatted[-1].copy()
                self.current_price = float(self.current_candle["close"])
                self.current_price_time = now_ms
                self.last_update_monotonic = time.monotonic()
                self.recent_trades.append({"price": self.current_price, "time": now_ms})

            print(f"Loaded {len(formatted)} candles. Initial price: {self.current_price}", flush=True)
            return True
        except Exception as error:
            print("Failed to load market history:", repr(error), flush=True)
            return False

    def _apply_candle(self, candle, price_time_ms=None):
        now_ms = int(price_time_ms or time.time() * 1000)
        candle = {
            "time": int(candle["time"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
        }

        with self.lock:
            if self.candles and self.candles[-1]["time"] == candle["time"]:
                self.candles[-1] = candle.copy()
            elif not self.candles or candle["time"] > self.candles[-1]["time"]:
                self.candles.append(candle.copy())
                self.candles = self.candles[-500:]

            self.current_candle = candle.copy()
            self.current_price = candle["close"]
            self.current_price_time = now_ms
            self.last_update_monotonic = time.monotonic()
            self.recent_trades.append({"price": self.current_price, "time": now_ms})
            event = {
                "type": "market",
                "symbol": SYMBOL,
                "price": self.current_price,
                "price_time": self.current_price_time,
                "candle": self.current_candle.copy(),
            }

        self._notify_listeners(event)

    def process_trade(self, price, trade_time_ms):
        price = float(price)
        trade_time_ms = int(trade_time_ms)
        minute = (trade_time_ms // 1000 // 60) * 60

        with self.lock:
            current = self.current_candle.copy() if self.current_candle else None

        if current is None or minute > current["time"]:
            candle = {"time": minute, "open": price, "high": price, "low": price, "close": price}
        elif minute == current["time"]:
            candle = {
                "time": minute,
                "open": current["open"],
                "high": max(current["high"], price),
                "low": min(current["low"], price),
                "close": price,
            }
        else:
            # Old trade: keep it for settlement but do not move the chart back.
            with self.lock:
                self.recent_trades.append({"price": price, "time": trade_time_ms})
            return

        self._apply_candle(candle, trade_time_ms)

    def _on_open(self, ws):
        with self.lock:
            self.socket_connected = True
        print("Binance WebSocket connected.", flush=True)

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            self.process_trade(float(data["p"]), int(data["T"]))
        except Exception as error:
            print("Market message error:", repr(error), flush=True)

    def _on_error(self, ws, error):
        print("Binance WebSocket error:", repr(error), flush=True)

    def _on_close(self, ws, code, message):
        with self.lock:
            self.socket_connected = False
        print("Binance WebSocket disconnected:", code, message, flush=True)

    def _websocket_worker(self):
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    BINANCE_WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as error:
                print("Market WebSocket worker error:", repr(error), flush=True)
            with self.lock:
                self.socket_connected = False
            if self.running:
                time.sleep(2)

    def _refresh_latest_candle_rest(self):
        response = self.http.get(
            BINANCE_REST_URL,
            params={"symbol": SYMBOL, "interval": CANDLE_INTERVAL, "limit": 2},
            timeout=6,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return
        self._apply_candle(self._format_candle(rows[-1]), int(time.time() * 1000))

    def _fallback_worker(self):
        while self.running:
            try:
                with self.lock:
                    age = time.monotonic() - self.last_update_monotonic if self.last_update_monotonic else 999
                # REST also acts as a periodic watchdog.  During a healthy WS
                # connection it is intentionally infrequent.
                if age > 3:
                    self._refresh_latest_candle_rest()
                    time.sleep(1)
                else:
                    time.sleep(2)
            except Exception as error:
                print("Market REST fallback error:", repr(error), flush=True)
                time.sleep(2)

    def start(self):
        if self.running:
            return
        self.load_history()
        self.running = True
        self.worker_thread = threading.Thread(target=self._websocket_worker, daemon=True, name="BinanceMarketThread")
        self.fallback_thread = threading.Thread(target=self._fallback_worker, daemon=True, name="BinanceRestFallbackThread")
        self.worker_thread.start()
        self.fallback_thread.start()
        print("Market service started.", flush=True)

    def stop(self):
        self.running = False
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def get_candles(self):
        with self.lock:
            candles = [c.copy() for c in self.candles]
            current = self.current_candle.copy() if self.current_candle else None
        if current:
            if candles and candles[-1]["time"] == current["time"]:
                candles[-1] = current
            elif not candles or current["time"] > candles[-1]["time"]:
                candles.append(current)
        return candles[-HISTORY_LIMIT:]

    def get_current_candle(self):
        with self.lock:
            return self.current_candle.copy() if self.current_candle else None

    def get_current_market_state(self):
        with self.lock:
            age = time.monotonic() - self.last_update_monotonic if self.last_update_monotonic else 999
            # A fresh REST fallback is valid live market data too; do not mark
            # the whole app unavailable merely because the Binance WS dropped.
            connected = self.current_price is not None and age < 10
            return {
                "symbol": SYMBOL,
                "price": self.current_price,
                "price_time": self.current_price_time,
                "connected": connected,
                "socket_connected": self.socket_connected,
            }

    def get_first_trade_at_or_after(self, timestamp_ms):
        timestamp_ms = int(timestamp_ms)
        with self.lock:
            for trade in self.recent_trades:
                if int(trade["time"]) >= timestamp_ms:
                    return dict(trade)
            # REST fallback updates are also stored in recent_trades, so an
            # expired trade can settle even after a socket interruption.
        return None

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
                print("Market listener error:", repr(error), flush=True)


market = MarketService()
