import time

from flask import Blueprint, jsonify, request, session

from config import CURRENCY_SYMBOL, MARKET_NAME, PRICE_DECIMALS, SYMBOL
from database.db import create_or_update_user, get_user_by_id
from services.market import market
from services.trading import trading
from services.telegram_auth import telegram_auth

api = Blueprint("api", __name__, url_prefix="/api")


def success_response(data=None, status=200):
    response = {"success": True}
    if data:
        response.update(data)
    return jsonify(response), status


def error_response(message, status=400):
    return jsonify({"success": False, "error": message}), status


def get_authenticated_user():
    user_id = session.get("user_id")
    return get_user_by_id(user_id) if user_id else None


def serialize_user(user):
    return {
        "id": user["id"],
        "telegram_id": user["telegram_id"],
        "username": user["username"],
        "first_name": user["first_name"],
        "demo_balance": round(float(user["demo_balance"]), PRICE_DECIMALS),
    }


def serialize_market_state(state):
    price = state.get("price")
    candle = market.get_current_candle()
    return {
        "symbol": state.get("symbol", SYMBOL),
        "market_name": MARKET_NAME,
        "currency_symbol": CURRENCY_SYMBOL,
        "price_decimals": PRICE_DECIMALS,
        "price": round(float(price), PRICE_DECIMALS) if price is not None else None,
        "price_time": state.get("price_time"),
        "connected": bool(state.get("connected")),
        "socket_connected": bool(state.get("socket_connected", False)),
        "candle": candle,
        "server_time": int(time.time() * 1000),
    }


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

    tg = verification["user"]
    user = create_or_update_user(
        telegram_id=tg["telegram_id"],
        username=tg.get("username"),
        first_name=tg.get("first_name"),
    )
    session.clear()
    session["user_id"] = user["id"]
    session["telegram_id"] = user["telegram_id"]
    return success_response({"mode": "telegram", "user": serialize_user(user)})


@api.route("/me")
def me():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    return success_response({"user": serialize_user(user)})


@api.route("/time")
def server_time():
    return success_response({"server_time": int(time.time() * 1000)})


@api.route("/chart")
def chart_data():
    if not get_authenticated_user():
        return error_response("Telegram authentication required.", 401)
    candles = market.get_candles()
    return jsonify(candles), 200


@api.route("/market")
def market_state():
    if not get_authenticated_user():
        return error_response("Telegram authentication required.", 401)
    return success_response(serialize_market_state(market.get_current_market_state()))


@api.route("/trade", methods=["POST"])
def open_trade():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    data = request.get_json(silent=True) or {}
    result = trading.open_trade(user["id"], str(data.get("direction", "")).upper().strip(), data.get("amount"))
    if not result["success"]:
        return error_response(result.get("error", "Unable to open trade."), 400)
    trade = result["trade"]
    trade["entry_price"] = round(float(trade["entry_price"]), PRICE_DECIMALS)
    return success_response({"trade": trade}, 201)


@api.route("/trade/open")
def get_open_trades():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    trades = trading.get_open_trades(user["id"])
    for trade in trades:
        trade["entry_price"] = round(float(trade["entry_price"]), PRICE_DECIMALS)
        trade["amount"] = round(float(trade["amount"]), PRICE_DECIMALS)
    return success_response({"trades": trades, "trade": trades[0] if trades else None, "server_time": int(time.time() * 1000)})


@api.route("/trades")
def trade_history():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except (TypeError, ValueError):
        limit = 20
    trades = trading.get_trade_history(user["id"], limit)
    for trade in trades:
        trade["entry_price"] = round(float(trade["entry_price"]), PRICE_DECIMALS)
        trade["amount"] = round(float(trade["amount"]), PRICE_DECIMALS)
        trade["profit"] = round(float(trade.get("profit", 0) or 0), PRICE_DECIMALS)
    return success_response({"trades": trades})


@api.route("/balance")
def balance():
    user = get_authenticated_user()
    if not user:
        return error_response("Telegram authentication required.", 401)
    return success_response({"balance": round(float(user["demo_balance"]), PRICE_DECIMALS)})
