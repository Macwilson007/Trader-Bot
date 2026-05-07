import os
import time
import logging
import sys
import threading
from datetime import datetime, timedelta
from threading import Lock
import pytz
from flask import Flask

sys.path.append('.')
from config import SYMBOLS, ACCOUNT_CONFIG, TRADING_SESSIONS, STRATEGY_CONFIG, SYMBOL_STRATEGIES, EXCHANGE
from connector.mt5_connector import MT5Connector
from connector.bybit_connector import BybitConnector
from core.session_manager import SessionManager
from strategy.entry_signals import MathRiskV3Signals, RiskCalculator
from strategy.rsi_strategy import RSIStrategy
from strategy.ema_crossover import EMACrossoverStrategy
from strategy.bb_squeeze import BBSqueezeStrategy
from strategy.rsi_divergence import RSIDivergenceStrategy
from execution.order_manager import OrderManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Initialize Flask app for Render Free Tier Keep-Alive
app = Flask(__name__)

@app.route('/')
def health_check():
    return {"status": "alive", "timestamp": datetime.now().isoformat()}, 200

def run_web_server():
    # Render provides a PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

class TradingBot:
    def __init__(self):
        if EXCHANGE == "MT5":
            self.connector = MT5Connector()
        else:
            self.connector = BybitConnector()
        self.session_manager = SessionManager()
        self.order_manager = OrderManager(self.connector)
        
        self.strategies = {
            "math_risk_v3":    MathRiskV3Signals(),
            "rsi":             RSIStrategy(),
            "ema_crossover":   EMACrossoverStrategy(),
            "bb_squeeze":      BBSqueezeStrategy(),
            "rsi_divergence":  RSIDivergenceStrategy(),
        }
        self.risk_calc = RiskCalculator(ACCOUNT_CONFIG["initial_balance"])
        
        self.initial_balance = ACCOUNT_CONFIG["initial_balance"]
        self.circuit_breaker_dd = ACCOUNT_CONFIG["circuit_breaker_dd"]
        self.circuit_breaker_lock_hours = ACCOUNT_CONFIG["circuit_breaker_lock_hours"]
        
        self.hard_lock_until = None
        self.trade_history = []
        self.daily_pnl = 0
        self.last_reset_date = None
        
        self.base_symbols = list(SYMBOLS.keys())
        self.last_session = None
        self.lock = Lock()
        
        self.tp1_positions = {}
        
        if EXCHANGE == "MT5":
            import MetaTrader5 as mt5
            self.tf_map = {
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4
            }
        else:
            self.tf_map = {
                "M15": "M15",
                "M30": "M30",
                "H1": "H1",
                "H4": "H4"
            }
        
        logger.info(f"Strategies loaded: {list(self.strategies.keys())}")
        for symbol, strategy_key in SYMBOL_STRATEGIES.items():
            tf_name = SYMBOLS[symbol].get("timeframe", "H1")
            logger.info(f"  {symbol} ({tf_name}) -> {strategy_key}")
    
    def start(self):
        logger.info("=" * 60)
        logger.info("TRADERBOT v2.0 - Mathematical Risk Engine v3")
        logger.info("=" * 60)
        
        if not self.connector.connect():
            logger.error(f"Failed to connect to {EXCHANGE}")
            return
        
        account_balance = self.connector.get_balance()
        if account_balance:
            self.initial_balance = account_balance
            self.risk_calc.update_balance(account_balance)
            logger.info(f"Balance: ${account_balance:,.2f}")
        
        logger.info(f"Symbols: {self.base_symbols}")
        logger.info(f"Strategy Assignments: {SYMBOL_STRATEGIES}")
        logger.info(f"Risk: {STRATEGY_CONFIG['risk_percent']*100}% per trade")
        logger.info(f"Circuit Breaker: {self.circuit_breaker_dd*100}% daily drawdown lock")
        
        try:
            self.run()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            self.connector.shutdown()
    
    def run(self):
        while True:
            try:
                current_time = datetime.now(pytz.timezone("GMT"))
                
                if self.last_reset_date != current_time.date():
                    self.reset_daily()
                
                if self.hard_lock_until and current_time < self.hard_lock_until:
                    remaining = (self.hard_lock_until - current_time).total_seconds() / 3600
                    if int(remaining) % 1 == 0:
                        logger.warning(f"CIRCUIT BREAKER ACTIVE - {remaining:.1f}h remaining")
                    time.sleep(60)
                    continue
                
                logger.info(f"[{current_time.strftime('%H:%M:%S')}] Checking...")
                
                should_trade, session = self.session_manager.should_trade()
                
                if should_trade and session:
                    logger.info(f"Session: {session['name']}")
                    self.open_all_pair_positions()
                    self.session_manager.mark_session_traded(session['name'])
                    self.last_session = session['name']
                
                self.manage_positions()
                
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(60)
    
    def open_all_pair_positions(self):
        for symbol in self.base_symbols:
            try:
                full_symbol = self.connector.get_symbol_name(symbol)
                
                strategy_key = SYMBOL_STRATEGIES.get(symbol, "math_risk_v3")
                strategy = self.strategies.get(strategy_key, self.strategies["math_risk_v3"])
                
                tf_name = SYMBOLS[symbol].get("timeframe", "H1")
                tf_val = self.tf_map.get(tf_name, "H1")
                
                h1_data = self.connector.get_historical_data(
                    full_symbol,
                    tf_val,
                    count=500 # Increased lookback for smaller TFs
                )
                
                if h1_data is None or len(h1_data) < 100:
                    logger.warning(f"No sufficient data for {symbol}")
                    continue
                
                direction, atr, atr_ratio, levels = strategy.get_signal(h1_data)
                
                if direction is None:
                    logger.info(f"{symbol}: No signal (ADX/EMA/ATR filters not met)")
                    continue
                
                current_price = h1_data['close'].iloc[-1]
                sl_distance = levels["sl_distance"]
                tp1_distance = levels["tp1"]
                tp2_distance = levels["tp2"]
                
                lot_size = self.risk_calc.calculate_lot_size(atr, sl_distance, symbol=symbol)
                
                # Safety guard: skip if minimum lot risks more than 3x intended (e.g. $10 account on BTC)
                actual_risk = lot_size * sl_distance
                intended_risk = self.risk_calc.get_risk_amount()
                if actual_risk > intended_risk * 3:
                    logger.warning(f"{symbol}: Skipping - min lot risks ${actual_risk:.2f} vs intended ${intended_risk:.2f} (account too small)")
                    continue
                
                if direction == "BUY":
                    sl = current_price - sl_distance
                    tp1 = current_price + tp1_distance
                    tp2 = current_price + tp2_distance
                else:
                    sl = current_price + sl_distance
                    tp1 = current_price - tp1_distance
                    tp2 = current_price - tp2_distance
                
                sl_pips = sl_distance * 100
                tp1_pips = tp1_distance * 100
                tp2_pips = tp2_distance * 100
                
                ticket = self.order_manager.open_position(
                    symbol=symbol,
                    order_type=direction,
                    lot_size=lot_size,
                    sl_pips=sl_pips,
                    tp_pips=tp2_pips,
                    comment=f"MRv3_{self.last_session}"
                )
                
                if ticket:
                    self.tp1_positions[ticket] = {
                        "entry": current_price,
                        "tp1": tp1,
                        "tp2": tp2,
                        "sl": sl,
                        "direction": direction,
                        "atr": atr
                    }
                    logger.info(f"✓ {direction} {symbol} | Lot:{lot_size:.3f} | SL:{sl:.2f} | TP1:{tp1:.2f} | TP2:{tp2:.2f} | ATRx:{atr_ratio:.1f}")
                else:
                    logger.warning(f"✗ Failed to open {symbol}")
                    
            except Exception as e:
                logger.error(f"Error opening {symbol}: {e}")
    
    def manage_positions(self):
        positions = self.order_manager.check_positions()
        
        if not positions:
            return
        
        logger.info(f"Managing {len(positions)} positions...")
        
        for pos in positions:
            ticket = pos["ticket"]
            symbol = pos["symbol"]
            profit = pos["profit"]
            pos_type = pos["type"]
            current_price = pos.get("price_current", pos["open_price"])
            
            tp1_info = self.tp1_positions.get(ticket)
            
            if tp1_info:
                if pos_type == "BUY":
                    if current_price >= tp1_info["tp1"] and profit > 0:
                        self.execute_partial_tp(pos, 0.5)
                        self.move_sl_to_breakeven(ticket, tp1_info["entry"])
                        logger.info(f"✓ {symbol} TP1 hit - 50% closed, SL→BE")
                        del self.tp1_positions[ticket]
                else:
                    if current_price <= tp1_info["tp1"] and profit > 0:
                        self.execute_partial_tp(pos, 0.5)
                        self.move_sl_to_breakeven(ticket, tp1_info["entry"])
                        logger.info(f"✓ {symbol} TP1 hit - 50% closed, SL→BE")
                        del self.tp1_positions[ticket]
            
            self.daily_pnl += profit
            
            logger.debug(f"{symbol} | Profit: ${profit:.2f} | TP: {pos['tp']} | SL: {pos['sl']}")
        
        self.check_circuit_breaker()
    
    def execute_partial_tp(self, pos, percent):
        volume_to_close = pos["volume"] * percent
        self.order_manager.close_partial(pos["ticket"], volume_to_close)
    
    def move_sl_to_breakeven(self, ticket, entry_price):
        self.order_manager.move_sl_to_breakeven(ticket, entry_price)
    
    def check_circuit_breaker(self):
        current_balance = self.initial_balance + self.daily_pnl
        drawdown = (self.initial_balance - current_balance) / self.initial_balance
        
        if drawdown >= self.circuit_breaker_dd:
            self.hard_lock_until = datetime.now(pytz.timezone("GMT")) + timedelta(hours=self.circuit_breaker_lock_hours)
            
            positions = self.order_manager.check_positions()
            for pos in positions:
                self.order_manager.close_partial(pos["ticket"], pos["volume"])
            
            logger.warning(f"CIRCUIT BREAKER TRIGGERED! Drawdown: {drawdown*100:.1f}%")
            logger.warning(f"All positions closed. Locked until {self.hard_lock_until}")
    
    def reset_daily(self):
        self.last_reset_date = datetime.now(pytz.timezone("GMT")).date()
        self.daily_pnl = 0
        self.tp1_positions = {}
        logger.info("Daily reset complete")
    
    def get_stats(self):
        return {
            "initial_balance": self.initial_balance,
            "daily_pnl": self.daily_pnl,
            "circuit_breaker_active": self.hard_lock_until is not None and datetime.now(pytz.timezone("GMT")) < self.hard_lock_until
        }


def main():
    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    bot = TradingBot()
    bot.start()


if __name__ == "__main__":
    main()
