import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta
import logging
import sys

sys.path.append('..')
from config import MT5_CONFIG, SYMBOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5Connector:
    def __init__(self):
        self.connected = False
        self.account_info = None
        self.symbols_map = {}
    
    def connect(self):
        if not mt5.initialize():
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False
        
        login_result = mt5.login(
            login=MT5_CONFIG["login"],
            password=MT5_CONFIG["password"],
            server=MT5_CONFIG["server"]
        )
        
        if not login_result:
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        self.account_info = mt5.account_info()
        self.connected = True
        logger.info(f"Connected to {MT5_CONFIG['server']} | Balance: {self.account_info.balance} {self.account_info.currency}")
        
        self._detect_symbols()
        return True
    
    def _detect_symbols(self):
        all_symbols = mt5.symbols_get()
        available = [s.name for s in all_symbols]
        
        for base_symbol, info in SYMBOLS.items():
            suffix = info["suffix"]
            full_symbol = f"{base_symbol}{suffix}"
            
            if full_symbol in available:
                self.symbols_map[base_symbol] = full_symbol
                logger.info(f"Found: {full_symbol}")
            else:
                if base_symbol in available:
                    self.symbols_map[base_symbol] = base_symbol
                    logger.info(f"Found (no suffix): {base_symbol}")
                else:
                    logger.warning(f"Symbol not found: {base_symbol} or {full_symbol}")
    
    def get_symbol_name(self, base_symbol):
        return self.symbols_map.get(base_symbol, base_symbol)
    
    def get_current_price(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return {"bid": tick.bid, "ask": tick.ask, "time": tick.time}
        return None
    
    def get_historical_data(self, symbol, timeframe, count=500):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    def get_ohlc(self, symbol, timeframe, start, end):
        rates = mt5.copy_rates_range(symbol, timeframe, start, end)
        if rates is None:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    def place_order(self, symbol, order_type, lot, sl_pips, tp_pips, comment=""):
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            return None
        
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
        
        point = symbol_info.point
        digits = symbol_info.digits
        
        if order_type == "BUY":
            price = symbol_info.ask
            sl = price - sl_pips * point
            tp = price + tp_pips * point
            order_type_enum = mt5.ORDER_TYPE_BUY
        else:
            price = symbol_info.bid
            sl = price + sl_pips * point
            tp = price - tp_pips * point
            order_type_enum = mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type_enum,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.comment}")
            return None
        
        return result.order
    
    def close_position(self, ticket):
        position = mt5.position_get(ticket=ticket)
        if not position:
            return False
        
        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info(position.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info(position.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "comment": "Close by bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    def modify_position_sl(self, ticket, new_sl):
        position = mt5.position_get(ticket=ticket)
        if not position:
            return False
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": new_sl,
            "tp": position.tp
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    def get_open_positions(self):
        positions = mt5.positions_get()
        return list(positions) if positions else []
    
    def get_balance(self):
        if self.account_info:
            return self.account_info.balance
        return 0
    
    def shutdown(self):
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection closed")


if __name__ == "__main__":
    connector = MT5Connector()
    if connector.connect():
        print(f"Balance: {connector.get_balance()}")
        for base, full in connector.symbols_map.items():
            print(f"{base} -> {full}")
        connector.shutdown()