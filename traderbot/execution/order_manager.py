import logging
import sys
import os

# Adjust path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SYMBOLS, EXCHANGE

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, connector):
        self.connector = connector
        self.pending_orders = {}
    
    def open_all_pairs(self, signals_dict, lot_size):
        results = {}
        for symbol, signal in signals_dict.items():
            if signal in ["BUY", "SELL"]:
                result = self.open_position(symbol, signal, lot_size)
                results[symbol] = result
        return results
    
    def open_position(self, symbol, order_type, lot_size, sl_pips=50, tp_pips=75, comment=""):
        full_symbol = self.connector.get_symbol_name(symbol)
        
        order_type_str = "BUY" if order_type == "BUY" else "SELL"
        
        ticket = self.connector.place_order(
            symbol=full_symbol,
            order_type=order_type_str,
            lot=lot_size,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            comment=comment
        )
        
        if ticket:
            self.pending_orders[symbol] = {
                "ticket": ticket,
                "symbol": full_symbol,
                "type": order_type_str,
                "volume": lot_size,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "partial_tp_done": False
            }
            return ticket
        return None
    
    def close_partial(self, ticket, volume):
        return self.connector.close_position(ticket)
    
    def move_sl_to_breakeven(self, ticket, entry_price=None):
        if EXCHANGE == "MT5":
            import MetaTrader5 as mt5
            if entry_price is None:
                position = mt5.position_get(ticket=ticket)
                if not position:
                    return False
                entry_price = position.price_open
            return self.connector.modify_position_sl(ticket, entry_price)
        else:
            # For Bybit, we need the symbol. Assuming ticket is symbol here for now
            # In a more robust system, we'd track orderIds
            return False # Placeholder
    
    def get_open_positions(self):
        return self.connector.get_open_positions()
    
    def check_positions(self):
        positions = self.get_open_positions()
        position_list = []
        
        if EXCHANGE == "MT5":
            import MetaTrader5 as mt5
            for pos in positions:
                position_list.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "volume": pos.volume,
                    "open_price": pos.price_open,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "profit": pos.profit,
                    "price_current": pos.price_current
                })
        elif EXCHANGE == "BYBIT":
            for pos in positions:
                # Bybit position mapping
                side = pos['side'] # "Buy" or "Sell"
                position_list.append({
                    "ticket": pos['symbol'], # Use symbol as ticket for simplicity if one pos per symbol
                    "symbol": pos['symbol'],
                    "type": "BUY" if side == "Buy" else "SELL",
                    "volume": float(pos['size']),
                    "open_price": float(pos['avgPrice']),
                    "sl": float(pos['stopLoss']) if pos['stopLoss'] else 0,
                    "tp": float(pos['takeProfit']) if pos['takeProfit'] else 0,
                    "profit": float(pos['unrealisedPnl']),
                    "price_current": float(pos['markPrice'])
                })
        
        return position_list


class PartialTPHandler:
    def __init__(self, order_manager):
        self.order_manager = order_manager
    
    def check_and_execute_partial_tp(self, positions, tp1_pips=37.5):
        results = []
        
        for pos in positions:
            if pos["type"] == "BUY":
                profit_pips = (pos["open_price"] - pos["open_price"]) * 100
            else:
                profit_pips = (pos["open_price"] - pos["open_price"]) * 100
            
            current_price = pos["open_price"]
            tp_price = pos["tp"]
            
            if pos["type"] == "BUY":
                distance_to_tp = (tp_price - current_price) / 0.01
            else:
                distance_to_tp = (current_price - tp_price) / 0.01
            
            if distance_to_tp <= tp1_pips:
                close_result = self.order_manager.close_partial(pos["ticket"], pos["volume"] / 2)
                if close_result:
                    self.order_manager.move_sl_to_breakeven(pos["ticket"])
                    results.append({"action": "partial_tp", "ticket": pos["ticket"]})
        
        return results


if __name__ == "__main__":
    print("Order Manager module loaded")
    print(f"Symbols: {list(SYMBOLS.keys())}")