import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

from config import ACCOUNT_CONFIG
from strategy.rsi_strategy import RSIStrategy
from strategy.ema_crossover import EMACrossoverStrategy
from strategy.entry_signals import MathRiskV3Signals


class Backtester:
    def __init__(self, initial_balance=10000, risk_percent=0.01):
        self.initial_balance = initial_balance
        self.risk_percent = risk_percent
        self.pip_value = 10
        
    def connect(self):
        if not mt5.initialize():
            print("MT5 connection failed")
            return False
        print(f"Connected to {mt5.account_info().server}")
        return True
    
    def get_data(self, symbol, timeframe=mt5.TIMEFRAME_H1, years=2):
        suffixes = ["c", "", ".c", "m", ".m"]
        symbol_full = None
        
        for suffix in suffixes:
            test_symbol = symbol + suffix
            if mt5.symbol_select(test_symbol):
                symbol_full = test_symbol
                print(f"  Using symbol: {symbol_full}")
                break
        
        if symbol_full is None:
            available = [s.name for s in mt5.symbols_get() if symbol in s.name]
            print(f"  Available matches: {available}")
            return None
            
        utc_from = datetime.now() - timedelta(days=365 * years)
        rates = mt5.copy_rates_from_pos(symbol_full, timeframe, 0, 5000)
        
        if rates is None:
            print(f"Failed to get data for {symbol_full}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df
    
    def run_backtest(self, df, strategy, name, symbol):
        print(f"\n{'='*60}")
        print(f"BACKTEST: {name} on {symbol}")
        print(f"{'='*60}")
        
        balance = self.initial_balance
        trades = []
        wins = 0
        losses = 0
        equity_curve = []
        
        position = None
        
        for i in range(200, len(df)):
            current_bar = df.iloc[:i+1].copy()
            
            if position is None:
                direction, atr, atr_ratio, levels = strategy.get_signal(current_bar)
                
                if direction:
                    entry_price = current_bar['close'].iloc[-1]
                    sl_distance = levels["sl_distance"]
                    tp_distance = levels["tp2"]
                    
                    lot_size = self.calculate_lot_size(sl_distance)
                    
                    position = {
                        "type": direction,
                        "entry": entry_price,
                        "sl": entry_price - sl_distance if direction == "BUY" else entry_price + sl_distance,
                        "tp": entry_price + tp_distance if direction == "BUY" else entry_price - tp_distance,
                        "lot": lot_size,
                        "atr": atr
                    }
            
            else:
                current_price = current_bar['close'].iloc[-1]
                pos = position
                
                hit_sl = (pos["type"] == "BUY" and current_price <= pos["sl"]) or \
                         (pos["type"] == "SELL" and current_price >= pos["sl"])
                hit_tp = (pos["type"] == "BUY" and current_price >= pos["tp"]) or \
                         (pos["type"] == "SELL" and current_price <= pos["tp"])
                
                if hit_sl:
                    pnl = -self.risk_percent * balance
                    balance += pnl
                    trades.append({"result": "LOSS", "pnl": pnl})
                    losses += 1
                    position = None
                    
                elif hit_tp:
                    pnl = self.risk_percent * balance * 2
                    balance += pnl
                    trades.append({"result": "WIN", "pnl": pnl})
                    wins += 1
                    position = None
            
            equity_curve.append(balance)
        
        if position:
            final_pnl = self.risk_percent * balance
            balance += final_pnl
            trades.append({"result": "CLOSED", "pnl": final_pnl})
        
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = abs(sum(t['pnl'] for t in trades if t['pnl'] > 0) / 
                           sum(t['pnl'] for t in trades if t['pnl'] < 0)) if losses > 0 else 0
        
        print(f"\n{'='*40}")
        print(f"RESULTS")
        print(f"{'='*40}")
        print(f"Total Trades:    {total_trades}")
        print(f"Wins:            {wins}")
        print(f"Losses:          {losses}")
        print(f"Win Rate:        {win_rate:.1f}%")
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance:   ${balance:,.2f}")
        print(f"Net Profit:      ${balance - self.initial_balance:,.2f}")
        print(f"Profit Factor:   {profit_factor:.2f}")
        print(f"Max Drawdown:     {(1 - min(equity_curve)/self.initial_balance)*100:.1f}%")
        print(f"{'='*40}")
        
        return {
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "final_balance": balance,
            "net_profit": balance - self.initial_balance,
            "profit_factor": profit_factor
        }
    
    def calculate_lot_size(self, sl_distance):
        risk_amount = self.initial_balance * self.risk_percent
        sl_dollars = sl_distance * 10000 * 0.0001 * self.pip_value
        
        if sl_dollars <= 0:
            return 0.01
        
        lot_size = risk_amount / sl_dollars
        return max(min(lot_size, 1.0), 0.01)


def main():
    initial_balance = ACCOUNT_CONFIG["initial_balance"]
    backtester = Backtester(initial_balance=initial_balance)
    
    if not backtester.connect():
        return
    
    print(f"\n{'#'*60}")
    print(f"# FOREX STRATEGY BACKTEST")
    print(f"# Initial Balance: ${initial_balance:,.2f}")
    print(f"# Timeframe: H1 | Period: 2 Years")
    print(f"{'#'*60}")
    
    symbols = {
        "EURUSD": ("RSI Strategy", RSIStrategy()),
        "GBPUSD": ("EMA Cross Strategy", EMACrossoverStrategy()),
        "XAUUSD": ("MathRiskV3 (Reference)", MathRiskV3Signals())
    }
    
    results = {}
    
    for symbol, (strategy_name, strategy) in symbols.items():
        df = backtester.get_data(symbol, years=1)
        if df is not None:
            results[symbol] = backtester.run_backtest(df, strategy, strategy_name, symbol)
    
    print("\n" + "#"*60)
    print("# SUMMARY COMPARISON")
    print("#"*60)
    print(f"{'Symbol':<12} {'Strategy':<18} {'Trades':<8} {'Win%':<8} {'Profit':<12} {'PF':<6}")
    print("-" * 60)
    
    for symbol, result in results.items():
        print(f"{symbol:<12} {symbols[symbol][0]:<18} {result['trades']:<8} {result['win_rate']:<8.1f} ${result['net_profit']:<11,.2f} {result['profit_factor']:<6.2f}")
    
    mt5.shutdown()


if __name__ == "__main__":
    main()
