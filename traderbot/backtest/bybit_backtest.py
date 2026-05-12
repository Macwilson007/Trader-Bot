import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import time

# Add root and traderbot directories to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from traderbot.connector.bybit_connector import BybitConnector
from traderbot.strategy.entry_signals import MathRiskV3Signals
from traderbot.strategy.rsi_strategy import RSIStrategy
from traderbot.strategy.ema_crossover import EMACrossoverStrategy
from traderbot.strategy.rsi_divergence import RSIDivergenceStrategy
from traderbot.strategy.bb_squeeze import BBSqueezeStrategy
from config import SYMBOLS, SYMBOL_STRATEGIES

class BybitBacktester:
    def __init__(self, initial_balance=1000.0):
        self.connector = BybitConnector()
        self.initial_balance = initial_balance
        self.strategies = {
            "math_risk_v3": MathRiskV3Signals(),
            "rsi": RSIStrategy(),
            "ema_crossover": EMACrossoverStrategy(),
            "rsi_divergence": RSIDivergenceStrategy(),
            "bb_squeeze": BBSqueezeStrategy()
        }

    def run(self, symbols=None, days=30):
        if not self.connector.connect():
            print("Failed to connect to Bybit for data.")
            return

        test_symbols = symbols if symbols else list(SYMBOLS.keys())
        test_symbols = [s for s in test_symbols if "USDT" in s]
        
        print("="*60)
        print(f"BYBIT CRYPTO BACKTEST - Last {days} Days")
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Watchlist: {test_symbols}")
        print("="*60)

        for symbol in test_symbols:
            print(f"\nAnalyzing {symbol}...")
            
            df = self.connector.get_historical_data(symbol, "60", count=days*24)
            
            if df is None:
                print(f"  Failed to fetch data for {symbol}")
                continue
            if len(df) < 100:
                print(f"  Insufficient data for {symbol} ({len(df)} bars)")
                continue
            
            print(f"  Data loaded: {len(df)} bars")

            strategy_key = SYMBOL_STRATEGIES.get(symbol, "math_risk_v3")
            strategy = self.strategies.get(strategy_key)
            
            if not strategy:
                print(f"  Error: Strategy {strategy_key} not found.")
                continue

            results = self.backtest_logic(symbol, df, strategy)
            self.print_results(symbol, results)

    def backtest_logic(self, symbol, df, strategy):
        balance = self.initial_balance
        trades = []
        wins, losses = 0, 0
        
        # Crypto logic: profit = (exit_price - entry_price) * qty
        # lot_size calculation (1% risk)
        # Risk_Amt = balance * 0.01
        # Qty = Risk_Amt / SL_Distance
        
        for i in range(100, len(df) - 12):
            lb = df.iloc[:i+1]
            direction, atr, atr_ratio, levels = strategy.get_signal(lb)
            
            if not direction:
                continue
            
            entry_price = lb['close'].iloc[-1]
            sl_dist = levels["sl_distance"]
            tp_dist = levels["tp2"] # Using TP2 for full backtest
            
            # Calculate quantity based on 1% risk
            risk_amount = balance * 0.01
            qty = risk_amount / sl_dist
            
            # Simple slippage / fee simulation (0.1% total)
            fee = entry_price * qty * 0.001
            balance -= fee
            
            sl = entry_price - sl_dist if direction == "BUY" else entry_price + sl_dist
            tp = entry_price + tp_dist if direction == "BUY" else entry_price - tp_dist
            
            # Look ahead (12 hours)
            fut = df.iloc[i+1 : i+13]
            if len(fut) == 0: continue
            
            hit_sl = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
            hit_tp = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)
            
            if hit_sl and hit_tp:
                # Conservative: if both hit in the same window, assume SL hit first
                hit_tp = False 

            if hit_tp:
                pnl = tp_dist * qty
                balance += pnl
                wins += 1
                trades.append({"time": lb['time'].iloc[-1], "res": "WIN", "pnl": pnl})
            elif hit_sl:
                pnl = -sl_dist * qty
                balance += pnl
                losses += 1
                trades.append({"time": lb['time'].iloc[-1], "res": "LOSS", "pnl": pnl})
            else:
                # Expired / Open
                exit_price = fut['close'].iloc[-1]
                pnl = (exit_price - entry_price) * qty if direction == "BUY" else (entry_price - exit_price) * qty
                balance += pnl
                trades.append({"time": lb['time'].iloc[-1], "res": "EXPIRED", "pnl": pnl})

        return {
            "wins": wins,
            "losses": losses,
            "final": balance,
            "trades": trades
        }

    def print_results(self, symbol, res):
        total = res['wins'] + res['losses']
        wr = (res['wins'] / total * 100) if total > 0 else 0
        pnl = res['final'] - self.initial_balance
        pnl_pct = (pnl / self.initial_balance) * 100
        
        print(f"  Strategy: {SYMBOL_STRATEGIES.get(symbol)}")
        print(f"  Total Trades: {len(res['trades'])} (Wins: {res['wins']}, Losses: {res['losses']})")
        print(f"  Win Rate: {wr:.1f}%")
        print(f"  Net PnL: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
        print(f"  Final Balance: ${res['final']:.2f}")

if __name__ == "__main__":
    backtester = BybitBacktester(initial_balance=1000.0)
    coins_to_test = [
        "BTCUSDT", "ETHUSDT", "XRPUSDT", 
        "SOLUSDT", "DOGEUSDT", "ADAUSDT", 
        "BNBUSDT", "LINKUSDT", "DOTUSDT", 
        "AVAXUSDT"
    ]
    backtester.run(symbols=coins_to_test, days=40)
