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
    BINANCE_WS_URL,
)


class MarketService:
    def __init__(self):
        self.current_price = None
        self.current_price_time = None
        self.current_candle = None
        self.candles = []
        self.recent_trades = deque(maxlen=10000)
        self.lock = threading.RLock()
        self.listeners = []
        self.ws = None
        self.running = False
        self.socket_connected = False
        self.last_update_monotonic = 0.0
        self.http = requests.Session()
        self.ticker_url = "https://api.binance.com/api/v3/ticker/price"

    def _symbol_is_sol(self):
        return str(SYMBOL).upper() == "SOLUSDT"

    def _format_candle(self, row):
        return {
            "time": int(int(row[0]) / 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
        }

    def load_history(self):
        try:
            response = self.http.get(
                BINANCE_REST_URL,
                params={"symbol": SYMBOL, "interval": CANDLE_INTERVAL, "limit": HISTORY_LIMIT},
                timeout=8,
            )
            response.raise_for_status()
            candles = [self._format_candle(x) for x in response.json()]
            if not candles:
                return False
            with self.lock:
                self.candles = candles[-HISTORY_LIMIT:]
                self.current_candle = candles[-1].copy()
                self.current_price = self.current_candle["close"]
                self.current_price_time = int(time.time() * 1000)
                self.last_update_monotonic = time.monotonic()
                self.recent_trades.append({"price": self.current_price, "time": self.current_price_time})
            print("Market history loaded:", len(candles), self.current_price, flush=True)
            return True
        except Exception as e:
            print("Market history error:", repr(e), flush=True)
            return False

    def _apply_price(self, price, timestamp_ms):
        price = float(price)
        timestamp_ms = int(timestamp_ms)
        minute = (timestamp_ms // 1000 // 60) * 60
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
            with self.lock:
                self.recent_trades.append({"price": price, "time": timestamp_ms})
            return

        with self.lock:
            if self.candles and self.candles[-1]["time"] == candle["time"]:
                self.candles[-1] = candle.copy()
            elif not self.candles or candle["time"] > self.candles[-1]["time"]:
                self.candles.append(candle.copy())
                self.candles = self.candles[-500:]
            self.current_candle = candle.copy()
            self.current_price = price
            self.current_price_time = timestamp_ms
            self.last_update_monotonic = time.monotonic()
            self.recent_trades.append({"price": price, "time": timestamp_ms})
            event = {
                "type": "market",
                "symbol": SYMBOL,
                "price": price,
                "price_time": timestamp_ms,
                "candle": candle.copy(),
            }
        self._notify_listeners(event)

    def process_trade(self, price, trade_time_ms):
        self._apply_price(price, trade_time_ms)

    def _on_open(self, ws):
        with self.lock:
            self.socket_connected = True
        print("Binance WebSocket connected.", flush=True)

    def _on_message(self, ws, message):
        try:
            d = json.loads(message)
            self._apply_price(float(d["p"]), int(d["T"]))
        except Exception as e:
            print("Market WS message error:", repr(e), flush=True)

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
            except Exception as e:
                print("Market WebSocket worker error:", repr(e), flush=True)
            with self.lock:
                self.socket_connected = False
            if self.running:
                time.sleep(2)

    def _rest_worker(self):
        # Keep the price moving even if the websocket is temporarily idle.
        while self.running:
            try:
                response = self.http.get(self.ticker_url, params={"symbol": SYMBOL}, timeout=5)
                response.raise_for_status()
                price = float(response.json()["price"])
                self._apply_price(price, int(time.time() * 1000))
                time.sleep(0.5 if self._symbol_is_sol() else 0.75)
            except Exception as e:
                print("Market REST ticker error:", repr(e), flush=True)
                try:
                    response = self.http.get(
                        BINANCE_REST_URL,
                        params={"symbol": SYMBOL, "interval": CANDLE_INTERVAL, "limit": 1},
                        timeout=5,
                    )
                    response.raise_for_status()
                    row = response.json()[-1]
                    self._apply_price(float(row[4]), int(time.time() * 1000))
                except Exception as e2:
                    print("Market REST kline fallback error:", repr(e2), flush=True)
                time.sleep(1)

    def start(self):
        if self.running:
            return
        self.load_history()
        self.running = True
        threading.Thread(target=self._websocket_worker, daemon=True, name="BinanceMarketThread").start()
        threading.Thread(target=self._rest_worker, daemon=True, name="BinanceRestTickerThread").start()
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
            return [x.copy() for x in self.candles[-HISTORY_LIMIT:]]

    def get_current_candle(self):
        with self.lock:
            return self.current_candle.copy() if self.current_candle else None

    def get_current_market_state(self):
        with self.lock:
            age = time.monotonic() - self.last_update_monotonic if self.last_update_monotonic else 999
            return {
                "symbol": SYMBOL,
                "price": self.current_price,
                "price_time": self.current_price_time,
                "connected": self.current_price is not None,
                "socket_connected": self.socket_connected,
                "age_seconds": age,
            }

    def get_first_trade_at_or_after(self, timestamp_ms):
        with self.lock:
            for trade in self.recent_trades:
                if int(trade["time"]) >= int(timestamp_ms):
                    return dict(trade)
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
            except Exception as e:
                print("Market listener error:", repr(e), flush=True)


market = MarketService()
