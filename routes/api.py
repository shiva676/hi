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
from services.telegram_auth import telegram_auth

api = Blueprint("api", __name__, url_prefix="/api")

# Production Mini App: browser/demo fallback is deliberately disabled.
DEV_MODE = False


def success_response(data=None, status=200):
    response = {"success": True}
    if data:
        response.update(data)
    return jsonify(response), status


def error_response(message, status=400):
    return jsonify({"success": False, "error": message}), status


def get_authenticated_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


@api.route("/auth", methods=["POST"])
def authenticate():
    data = request.get_json(silent=True) or {}
    init_data = data.get("init_data")

    if not init_data:
        session.clear()
        return error_response("Open this app from Telegram to continue.", 401)

    verification = telegram_auth.verify_init_data(init_data)
    if not verification["success"]:
        session.clear()
        return error_response(verification["error"], 401)

    telegram_user = verification["user"]
    user = create_or_update_user(
        telegram_id=telegram_user["telegram_id"],
        username=telegram_user.get("username"),
        first_name=telegram_user.get("first_name")
    )

    session.clear()
    session["user_id"] = user["id"]
    session["telegram_id"] = user["telegram_id"]

    return success_response({
        "mode": "telegram",
        "user": serialize_user(user)
    })


def serialize_user(user):
    return {
        "id": user["id"],
        "telegram_id": user["telegram_id"],
        "username": user["username"],
        "first_name": user["first_name"],
        "demo_balance": round(float(user["demo_balance"]), 2)
    }


@api.route("/me", methods=["GET"])
def me():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    return success_response({"user": serialize_user(user)})


@api.route("/time", methods=["GET"])
def server_time():
    return success_response({"server_time": int(time.time() * 1000)})


@api.route("/chart", methods=["GET"])
def chart_data():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    candles = market.get_candles()
    return jsonify(candles), 200


@api.route("/market", methods=["GET"])
def market_state():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    state = market.get_current_market_state()
    return success_response({
        "symbol": state["symbol"],
        "price": state["price"],
        "price_time": state.get("price_time"),
        "connected": state["connected"],
        "server_time": int(time.time() * 1000)
    })


@api.route("/trade", methods=["POST"])
def open_trade():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)

    data = request.get_json(silent=True) or {}
    direction = str(data.get("direction", "")).upper().strip()
    amount = data.get("amount")

    result = trading.open_trade(user_id=user["id"], direction=direction, amount=amount)
    if not result["success"]:
        return error_response(result["error"], 400)
    return success_response({"trade": result["trade"]}, 201)


@api.route("/trade/open", methods=["GET"])
def get_open_trade():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)

    # Kept for compatibility with the existing UI. It returns the latest open
    # position; all open positions still remain active in PostgreSQL.
    trade = trading.get_open_trade(user["id"])
    return success_response({"trade": trade})


@api.route("/trades", methods=["GET"])
def trade_history():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)

    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    trades = trading.get_trade_history(user["id"], limit=limit)
    return success_response({"trades": trades})


@api.route("/balance", methods=["GET"])
def balance():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    return success_response({"balance": round(float(user["demo_balance"]), 2)})
