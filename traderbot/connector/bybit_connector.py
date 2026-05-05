from pybit.unified_trading import HTTP
import pandas as pd
import logging
import time
from datetime import datetime, timezone
import sys
import os

# Adjust path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BYBIT_CONFIG

logger = logging.getLogger(__name__)

class BybitConnector:
    def __init__(self):
        self.api_key = BYBIT_CONFIG.get("api_key")
        self.api_secret = BYBIT_CONFIG.get("api_secret")
        self.testnet = BYBIT_CONFIG.get("testnet", True)
        self.category = BYBIT_CONFIG.get("category", "linear")
        self.session = None
        self.connected = False

    def connect(self):
        try:
            self.session = HTTP(
                testnet=self.testnet,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            # Test connection by getting account info
            res = self.session.get_wallet_balance(accountType="UNIFIED")
            if res['retCode'] == 0:
                self.connected = True
                logger.info("Successfully connected to Bybit")
                return True
            else:
                logger.error(f"Bybit connection failed: {res['retMsg']}")
                return False
        except Exception as e:
            logger.error(f"Bybit connection error: {e}")
            return False

    def get_symbol_name(self, base_symbol):
        # Bybit uses symbols like BTCUSDT
        if "USD" in base_symbol and "USDT" not in base_symbol:
            return base_symbol.replace("USD", "USDT")
        return base_symbol

    def get_current_price(self, symbol):
        try:
            res = self.session.get_tickers(category=self.category, symbol=symbol)
            if res['retCode'] == 0:
                ticker = res['result']['list'][0]
                return {
                    "bid": float(ticker['bid1Price']),
                    "ask": float(ticker['ask1Price']),
                    "last": float(ticker['lastPrice']),
                    "time": int(time.time())
                }
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
        return None

    def get_historical_data(self, symbol, timeframe, count=500):
        # Bybit timeframes: 1 3 5 15 30 60 120 240 360 720 D W M
        # Map MT5-like timeframes if needed
        tf_map = {
            "M1": "1", "M5": "5", "M15": "15", "M30": "30",
            "H1": "60", "H4": "240", "D1": "D"
        }
        bybit_tf = tf_map.get(timeframe, str(timeframe))
        
        try:
            res = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=bybit_tf,
                limit=count
            )
            if res['retCode'] == 0:
                data = res['result']['list']
                # Bybit returns: [start_time, open, high, low, close, volume, turnover]
                df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df['time'] = pd.to_datetime(df['time'].astype(float), unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                # Bybit returns data from newest to oldest, reverse it for strategy
                return df.iloc[::-1].reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
        return None

    def place_order(self, symbol, order_type, lot, sl_pips=None, tp_pips=None, comment=""):
        # lot here is quantity in base currency (e.g. 0.01 BTC)
        side = "Buy" if order_type.upper() == "BUY" else "Sell"
        
        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": "Market",
                "qty": str(lot),
                "timeInForce": "GTC",
            }
            
            # Handling SL/TP is slightly different in Bybit (can be done on order placement)
            # However, pips to price conversion is needed
            current_price = self.get_current_price(symbol)
            if current_price:
                price = current_price['ask'] if side == "Buy" else current_price['bid']
                # Rough pip calculation for crypto (depends on symbol tick size)
                # For simplicity, we'll assume 1 pip = 0.1 for Gold/BTC or use a better mapping
                pip_size = 0.1 # Placeholder
                
                if sl_pips:
                    sl_price = price - (sl_pips * pip_size) if side == "Buy" else price + (sl_pips * pip_size)
                    params["stopLoss"] = str(round(sl_price, 4))
                if tp_pips:
                    tp_price = price + (tp_pips * pip_size) if side == "Buy" else price - (tp_pips * pip_size)
                    params["takeProfit"] = str(round(tp_price, 4))

            res = self.session.place_order(**params)
            if res['retCode'] == 0:
                return res['result']['orderId']
            else:
                logger.error(f"Order placement failed: {res['retMsg']}")
        except Exception as e:
            logger.error(f"Error placing order on Bybit: {e}")
        return None

    def close_position(self, symbol, side, qty):
        # To close a position in Linear Perpetual, place an opposite order
        close_side = "Sell" if side == "Buy" else "Buy"
        try:
            res = self.session.place_order(
                category=self.category,
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=str(qty),
                reduceOnly=True
            )
            return res['retCode'] == 0
        except Exception as e:
            logger.error(f"Error closing position on Bybit: {e}")
        return False

    def get_open_positions(self):
        try:
            res = self.session.get_positions(category=self.category, settleCoin="USDT")
            if res['retCode'] == 0:
                # Filter out empty positions
                return [p for p in res['result']['list'] if float(p['size']) > 0]
        except Exception as e:
            logger.error(f"Error getting positions from Bybit: {e}")
        return []

    def get_balance(self):
        try:
            res = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if res['retCode'] == 0:
                return float(res['result']['list'][0]['coin'][0]['walletBalance'])
        except Exception as e:
            logger.error(f"Error getting Bybit balance: {e}")
        return 0

    def shutdown(self):
        self.connected = False
        logger.info("Bybit connection closed")

if __name__ == "__main__":
    connector = BybitConnector()
    if connector.connect():
        print(f"Balance: {connector.get_balance()}")
        connector.shutdown()
