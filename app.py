import atexit

from flask import Flask, render_template

from config import DEBUG, HOST, PORT, SECRET_KEY, MARKET_NAME, SYMBOL, CURRENCY_SYMBOL, PRICE_DECIMALS
from database.db import init_database
from routes.api import api
from services.market import market
from services.trading import trading

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not DEBUG,
)
app.register_blueprint(api)


@app.context_processor
def inject_ui_constants():
    return {
        "MARKET_NAME": MARKET_NAME,
        "SYMBOL": SYMBOL,
        "CURRENCY_SYMBOL": CURRENCY_SYMBOL,
        "PRICE_DECIMALS": PRICE_DECIMALS,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    state = market.get_current_market_state()
    return {
        "status": "ok",
        "market_connected": state["connected"],
        "market_socket_connected": state.get("socket_connected", False),
        "market_price": state["price"],
        "market_price_time": state.get("price_time"),
        "market_symbol": SYMBOL,
        "market_name": MARKET_NAME,
    }


services_started = False


def start_services():
    global services_started
    if services_started:
        return
    services_started = True
    print("Initializing PostgreSQL...", flush=True)
    init_database()
    print("Starting Binance market service...", flush=True)
    market.start()
    print("Starting trading settlement engine...", flush=True)
    trading.start()
    print("Backend services started.", flush=True)


def stop_services():
    global services_started
    if not services_started:
        return
    try:
        trading.stop()
    except Exception as error:
        print("Trading stop error:", error, flush=True)
    try:
        market.stop()
    except Exception as error:
        print("Market stop error:", error, flush=True)
    services_started = False


atexit.register(stop_services)
start_services()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False, threaded=True)
