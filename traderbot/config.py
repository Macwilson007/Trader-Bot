import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

MT5_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", "0")),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", ""),
    "path": r"C:\Program Files\MetaTrader 5\terminal64.exe"
}

BYBIT_CONFIG = {
    "api_key": os.getenv("BYBIT_API_KEY", ""),
    "api_secret": os.getenv("BYBIT_API_SECRET", ""),
    "testnet": os.getenv("BYBIT_TESTNET", "True").lower() == "true",
    "category": os.getenv("BYBIT_CATEGORY", "linear") # "linear" for USDT Perpetual, "spot" for Spot
}

EXCHANGE = os.getenv("EXCHANGE", "BYBIT") # Options: "MT5", "BYBIT"

ACCOUNT_CONFIG = {
    "initial_balance": 7157,
    "currency": "USC",
    "risk_per_trade": 0.01,
    "lot_size": 0.35,
    "max_daily_trades": 20,
    "max_consecutive_losses": 10,
    "circuit_breaker_dd": 0.03,
    "circuit_breaker_lock_hours": 24
}

SYMBOLS = {
    "BTCUSDT": {"suffix": "", "pip_value": 0.1, "min_lot": 0.001, "max_lot": 100, "timeframe": "H1"},
    "ETHUSDT": {"suffix": "", "pip_value": 0.01, "min_lot": 0.01, "max_lot": 1000, "timeframe": "H1"},
    "XRPUSDT": {"suffix": "", "pip_value": 0.0001, "min_lot": 1.0, "max_lot": 100000, "timeframe": "H1"}
}

SYMBOL_STRATEGIES = {
    "BTCUSDT": "math_risk_v3",
    "ETHUSDT": "ema_crossover",
    "XRPUSDT": "ema_crossover"
}

TRADING_SESSIONS = [
    {"name": "London Overlap", "hour": 7, "minute": 0},
    {"name": "London AM", "hour": 8, "minute": 0},
    {"name": "London PM", "hour": 12, "minute": 0},
    {"name": "NY AM", "hour": 13, "minute": 0},
    {"name": "NY PM", "hour": 14, "minute": 0}
]

STRATEGY_CONFIG = {
    "adx_period": 14,
    "adx_min": 15,
    "ema_trend": 200,
    "ema_entry": 20,
    "atr_period": 14,
    "atr_multiplier": 1.5,
    "atr_volatility_threshold": 3.0,
    "tp1_r": 1.5,
    "tp2_r": 5.0,
    "risk_percent": 0.01,
    "pip_value": 1.0,
    "trade_hours": [6, 7, 8, 12, 13, 14]
}

LOG_CONFIG = {
    "log_file": "logs/trading.log",
    "log_level": "INFO"
}
