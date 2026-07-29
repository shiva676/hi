import json
import threading
import time

from services.market import market
from services.trading import trading


# ============================================================
# CONNECTED BROWSERS
# ============================================================

clients = []

clients_lock = threading.RLock()


# ============================================================
# ADD CLIENT
# ============================================================

def add_client(ws):

    with clients_lock:

        if ws not in clients:
            clients.append(ws)


# ============================================================
# REMOVE CLIENT
# ============================================================

def remove_client(ws):

    with clients_lock:

        try:
            clients.remove(ws)

        except ValueError:
            pass


# ============================================================
# BROADCAST EVENT
# ============================================================

def broadcast(event):

    try:

        message = json.dumps(
            event
        )

    except Exception as error:

        print(
            "WebSocket serialization error:",
            error
        )

        return


    dead_clients = []


    with clients_lock:

        current_clients = list(
            clients
        )


    for ws in current_clients:

        try:

            ws.send(
                message
            )

        except Exception:

            dead_clients.append(
                ws
            )


    # Remove disconnected sockets.

    if dead_clients:

        with clients_lock:

            for ws in dead_clients:

                try:
                    clients.remove(ws)

                except ValueError:
                    pass


# ============================================================
# MARKET EVENT
# ============================================================

def handle_market_event(event):

    # market.py already produces:
    #
    # {
    #     "type": "market",
    #     "symbol": "BTCUSDT",
    #     "price": ...,
    #     "price_time": ...,
    #     "candle": {...}
    # }

    broadcast(
        event
    )


# ============================================================
# TRADING EVENT
# ============================================================

def handle_trading_event(event):

    # For the prototype we broadcast trade events.
    #
    # IMPORTANT:
    # Later, when multiple real Telegram users are connected,
    # private trade events should be sent ONLY to the
    # authenticated owner instead of broadcasting them.

    broadcast(
        event
    )


# ============================================================
# REGISTER EVENT LISTENERS
# ============================================================

market.add_listener(
    handle_market_event
)


trading.add_listener(
    handle_trading_event
)


# ============================================================
# REGISTER WEBSOCKET ROUTE
# ============================================================

def register_websocket(
    sock
):

    @sock.route("/ws")
    def browser_websocket(ws):

        print(
            "Browser WebSocket connected."
        )


        add_client(
            ws
        )


        # ----------------------------------------------------
        # Send initial market state
        # ----------------------------------------------------

        try:

            market_state = (
                market.get_current_market_state()
            )


            candle = (
                market.get_current_candle()
            )


            ws.send(
                json.dumps({

                    "type":
                        "connected",

                    "market": {

                        "price":
                            market_state[
                                "price"
                            ],

                        "price_time":
                            market_state[
                                "price_time"
                            ],

                        "connected":
                            market_state[
                                "connected"
                            ],

                        "candle":
                            candle

                    }

                })
            )

        except Exception as error:

            print(
                "Initial WebSocket message error:",
                error
            )


        # ----------------------------------------------------
        # Keep connection alive
        # ----------------------------------------------------

        try:

            while True:

                # flask-sock / simple-websocket blocks here
                # waiting for a client message.
                #
                # We don't actually need commands from the
                # browser yet.

                message = ws.receive(
                    timeout=30
                )


                # ------------------------------------------------
                # Connection closed
                # ------------------------------------------------

                if message is None:

                    break


                # ------------------------------------------------
                # Optional browser ping
                # ------------------------------------------------

                if message == "ping":

                    ws.send(
                        json.dumps({
                            "type": "pong",
                            "server_time":
                                int(
                                    time.time()
                                    * 1000
                                )
                        })
                    )


        except Exception:

            # Timeout/disconnection is normal.
            pass


        finally:

            remove_client(
                ws
            )


            print(
                "Browser WebSocket disconnected."
            )