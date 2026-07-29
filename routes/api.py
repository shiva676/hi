import time

from flask import (
    Blueprint,
    jsonify,
    request,
    session
)

from database.db import (
    create_or_update_user,
    get_user_by_id
)

from services.market import market
from services.trading import trading
from services.telegram_auth import (
    telegram_auth
)


# ============================================================
# BLUEPRINT
# ============================================================

api = Blueprint(
    "api",
    __name__,
    url_prefix="/api"
)


# ============================================================
# DEVELOPMENT MODE
# ============================================================

# IMPORTANT:
#
# True  = browser testing without Telegram
# False = Telegram authentication required
#
# Change this to False before real deployment.

DEV_MODE = True


DEV_USER = {
    "telegram_id": 999999999,
    "username": "demo_user",
    "first_name": "Demo"
}


# ============================================================
# RESPONSE HELPERS
# ============================================================

def success_response(
    data=None,
    status=200
):

    response = {
        "success": True
    }


    if data:

        response.update(
            data
        )


    return jsonify(
        response
    ), status


def error_response(
    message,
    status=400
):

    return jsonify({

        "success": False,

        "error":
            message

    }), status


# ============================================================
# GET AUTHENTICATED USER
# ============================================================

def get_authenticated_user():

    user_id = session.get(
        "user_id"
    )


    # --------------------------------------------------------
    # Already authenticated
    # --------------------------------------------------------

    if user_id:

        user = get_user_by_id(
            user_id
        )


        if user:

            return user


    # --------------------------------------------------------
    # Development browser mode
    # --------------------------------------------------------

    if DEV_MODE:

        user = create_or_update_user(

            telegram_id=
                DEV_USER["telegram_id"],

            username=
                DEV_USER["username"],

            first_name=
                DEV_USER["first_name"]

        )


        session["user_id"] = (
            user["id"]
        )


        session["telegram_id"] = (
            user["telegram_id"]
        )


        return user


    return None


# ============================================================
# TELEGRAM AUTH
# ============================================================

@api.route(
    "/auth",
    methods=["POST"]
)
def authenticate():

    data = request.get_json(
        silent=True
    ) or {}


    init_data = data.get(
        "init_data"
    )


    # --------------------------------------------------------
    # Development login
    # --------------------------------------------------------

    if (
        DEV_MODE
        and not init_data
    ):

        user = create_or_update_user(

            telegram_id=
                DEV_USER["telegram_id"],

            username=
                DEV_USER["username"],

            first_name=
                DEV_USER["first_name"]

        )


        session["user_id"] = (
            user["id"]
        )


        session["telegram_id"] = (
            user["telegram_id"]
        )


        return success_response({

            "mode":
                "development",

            "user":
                serialize_user(
                    user
                )

        })


    # --------------------------------------------------------
    # Real Telegram authentication
    # --------------------------------------------------------

    verification = (
        telegram_auth.verify_init_data(
            init_data
        )
    )


    if not verification["success"]:

        return error_response(
            verification["error"],
            401
        )


    telegram_user = (
        verification["user"]
    )


    # --------------------------------------------------------
    # Create/update database user
    # --------------------------------------------------------

    user = create_or_update_user(

        telegram_id=
            telegram_user[
                "telegram_id"
            ],

        username=
            telegram_user.get(
                "username"
            ),

        first_name=
            telegram_user.get(
                "first_name"
            )

    )


    # --------------------------------------------------------
    # Create server session
    # --------------------------------------------------------

    session.clear()


    session["user_id"] = (
        user["id"]
    )


    session["telegram_id"] = (
        user["telegram_id"]
    )


    return success_response({

        "mode":
            "telegram",

        "user":
            serialize_user(
                user
            )

    })


# ============================================================
# SERIALIZE USER
# ============================================================

def serialize_user(
    user
):

    return {

        "id":
            user["id"],

        "telegram_id":
            user["telegram_id"],

        "username":
            user["username"],

        "first_name":
            user["first_name"],

        "demo_balance":
            round(
                float(
                    user["demo_balance"]
                ),
                2
            )

    }


# ============================================================
# CURRENT USER
# ============================================================

@api.route(
    "/me",
    methods=["GET"]
)
def current_user():

    user = (
        get_authenticated_user()
    )


    if not user:

        return error_response(
            "Authentication required.",
            401
        )


    return success_response({

        "user":
            serialize_user(
                user
            )

    })


# ============================================================
# SERVER TIME
# ============================================================

@api.route(
    "/time",
    methods=["GET"]
)
def server_time():

    return success_response({

        # milliseconds

        "server_time":
            int(
                time.time()
                * 1000
            )

    })


# ============================================================
# MARKET STATE
# ============================================================

@api.route(
    "/market",
    methods=["GET"]
)
def market_state():

    state = (
        market.get_current_market_state()
    )


    return success_response({

        "symbol":
            "BTCUSDT",

        "price":
            state["price"],

        "market_time":
            state["price_time"],

        "connected":
            state["connected"]

    })


# ============================================================
# CHART HISTORY
# ============================================================

@api.route(
    "/chart",
    methods=["GET"]
)
def chart():

    candles = (
        market.get_candles()
    )


    # IMPORTANT:
    #
    # Our existing chart.js expects a raw array.
    #
    # Therefore this route intentionally does NOT
    # use success_response().

    return jsonify(
        candles
    )


# ============================================================
# OPEN NEW DEMO TRADE
# ============================================================

@api.route(
    "/trade",
    methods=["POST"]
)
def create_trade():

    user = (
        get_authenticated_user()
    )


    if not user:

        return error_response(
            "Authentication required.",
            401
        )


    data = request.get_json(
        silent=True
    ) or {}


    direction = (
        data.get(
            "direction"
        )
    )


    amount = (
        data.get(
            "amount"
        )
    )


    # --------------------------------------------------------
    # Notice what we DO NOT accept:
    #
    # entry_price
    # exit_price
    # expiry_time
    # result
    # profit
    # balance
    #
    # Backend creates all of them.
    # --------------------------------------------------------

    result = (
        trading.open_trade(

            user_id=
                user["id"],

            direction=
                direction,

            amount=
                amount

        )
    )


    if not result["success"]:

        return error_response(
            result["error"],
            400
        )


    return success_response({

        "trade":
            result["trade"]

    }, 201)


# ============================================================
# CURRENT OPEN TRADE
# ============================================================

@api.route(
    "/trade/open",
    methods=["GET"]
)
def open_trade():

    user = (
        get_authenticated_user()
    )


    if not user:

        return error_response(
            "Authentication required.",
            401
        )


    trade = (
        trading.get_open_trade(
            user["id"]
        )
    )


    # --------------------------------------------------------
    # Include server time.
    #
    # Frontend uses this only to DISPLAY countdown.
    #
    # Backend remains authoritative.
    # --------------------------------------------------------

    return success_response({

        "server_time":
            int(
                time.time()
                * 1000
            ),

        "trade":
            trade

    })


# ============================================================
# TRADE HISTORY
# ============================================================

@api.route(
    "/trades",
    methods=["GET"]
)
def trade_history():

    user = (
        get_authenticated_user()
    )


    if not user:

        return error_response(
            "Authentication required.",
            401
        )


    limit = request.args.get(
        "limit",
        20
    )


    trades = (
        trading.get_trade_history(

            user_id=
                user["id"],

            limit=
                limit

        )
    )


    return success_response({

        "trades":
            trades

    })