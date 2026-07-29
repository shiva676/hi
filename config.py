import os


# =========================================================
# APPLICATION
# =========================================================

DEBUG = True

HOST = "0.0.0.0"
PORT = 5000


# =========================================================
# TELEGRAM
# =========================================================

# Set BOT_TOKEN as an environment variable in production.
BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
)
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')

# =========================================================
# MARKET
# =========================================================

SYMBOL = "BTCUSDT"

CANDLE_INTERVAL = "1m"

HISTORY_LIMIT = 150


# Binance public market-data endpoints
BINANCE_REST_URL = (
    "https://api.binance.com/api/v3/klines"
)

BINANCE_WS_URL = (
    "wss://stream.binance.com:9443/ws/"
    "btcusdt@trade"
)


# =========================================================
# DEMO TRADING
# =========================================================

DEMO_STARTING_BALANCE = 10000.00

TRADE_DURATION_SECONDS = 60

# 80% profit on a winning demo trade
DEMO_PAYOUT = 0.80

MIN_TRADE_AMOUNT = 1.00

MAX_TRADE_AMOUNT = 1000.00


# =========================================================
# DATABASE
# =========================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL"
)