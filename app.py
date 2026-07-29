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


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(
    __name__
)


# ============================================================
# SECURITY / SESSION
# ============================================================

app.secret_key = (
    SECRET_KEY
)


app.config.update(

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SAMESITE="Lax"

)


# ============================================================
# WEBSOCKET
# ============================================================

sock = Sock(
    app
)


register_websocket(
    sock
)


# ============================================================
# API ROUTES
# ============================================================

app.register_blueprint(
    api
)


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    market_state = (
        market.get_current_market_state()
    )


    return {

        "status":
            "ok",

        "market_connected":
            market_state[
                "connected"
            ],

        "market_price":
            market_state[
                "price"
            ]

    }


# ============================================================
# START BACKEND SERVICES
# ============================================================

def start_services():

    print()
    print(
        "======================================"
    )

    print(
        " Trading Prototype"
    )

    print(
        "======================================"
    )


    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    init_database()


    # --------------------------------------------------------
    # Binance
    # --------------------------------------------------------

    market.start()


    # --------------------------------------------------------
    # Trading settlement engine
    # --------------------------------------------------------

    trading.start()


    print(
        "Backend services started."
    )

    print(
        "======================================"
    )

    print()


# ============================================================
# STOP SERVICES
# ============================================================

def stop_services():

    print(
        "Stopping backend services..."
    )


    trading.stop()

    market.stop()


atexit.register(
    stop_services
)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    start_services()


    app.run(

        host=HOST,

        port=PORT,

        debug=DEBUG,

        # Important because Flask debug reloader
        # would otherwise start our Binance service twice.

        use_reloader=False,

        threaded=True

    )