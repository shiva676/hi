import atexit

from flask import (
    Flask,
    render_template
)

from flask_sock import Sock

from config import (
    DEBUG,
    HOST,
    PORT,
    SECRET_KEY
)

from database.db import (
    init_database
)

from routes.api import api

from routes.websocket import (
    register_websocket
)

from services.market import market
from services.trading import trading
from services.multi_trade import install_multi_trade_support

# Enable multiple simultaneous positions before API requests are handled.
install_multi_trade_support(trading)


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(
    __name__
)


# ============================================================
# SECURITY / SESSION
# ============================================================

app.secret_key = SECRET_KEY

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not DEBUG
)


# ============================================================
# WEBSOCKET
# ============================================================

sock = Sock(app)
register_websocket(sock)


# ============================================================
# API ROUTES
# ============================================================

app.register_blueprint(api)


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    market_state = market.get_current_market_state()
    return {
        "status": "ok",
        "market_connected": market_state["connected"],
        "market_price": market_state["price"]
    }


# ============================================================
# SERVICE STATE
# ============================================================

services_started = False


# ============================================================
# START BACKEND SERVICES
# ============================================================

def start_services():
    global services_started

    if services_started:
        return

    services_started = True

    print()
    print("======================================")
    print(" Trading Prototype")
    print("======================================")

    print("Initializing PostgreSQL...")
    init_database()

    print("Starting Binance market service...")
    market.start()

    print("Starting trading settlement engine...")
    trading.start()

    print("Backend services started.")
    print("======================================")
    print()


# ============================================================
# STOP SERVICES
# ============================================================

def stop_services():
    global services_started

    if not services_started:
        return

    print("Stopping backend services...")

    try:
        trading.stop()
    except Exception as error:
        print("Trading service stop error:", error)

    try:
        market.stop()
    except Exception as error:
        print("Market service stop error:", error)

    services_started = False


atexit.register(stop_services)

# Gunicorn imports app:app, so services must start on module import.
start_services()


if __name__ == "__main__":
    app.run(
        host=HOST,
        port=PORT,
        debug=DEBUG,
        use_reloader=False,
        threaded=True
    )
