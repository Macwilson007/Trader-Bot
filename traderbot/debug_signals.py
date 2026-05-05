import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from config import SYMBOLS, SYMBOL_STRATEGIES, EXCHANGE
from connector.mt5_connector import MT5Connector
from connector.bybit_connector import BybitConnector
from strategy.rsi_strategy import RSIStrategy
from strategy.ema_crossover import EMACrossoverStrategy
from strategy.entry_signals import MathRiskV3Signals

def get_data(connector, symbol, count=300):
    full_symbol = connector.get_symbol_name(symbol)
    return connector.get_historical_data(full_symbol, "H1", count=count)

def main():
    if EXCHANGE == "MT5":
        connector = MT5Connector()
    else:
        connector = BybitConnector()
        
    if not connector.connect():
        print(f"{EXCHANGE} connection failed")
        return
    
    strategies = {
        "math_risk_v3": MathRiskV3Signals(),
        "rsi": RSIStrategy(),
        "ema_crossover": EMACrossoverStrategy()
    }
    
    print("="*60)
    print(f"STRATEGY SIGNAL DEBUG ({EXCHANGE})")
    print("="*60)
    
    for symbol in SYMBOLS.keys():
        strategy_key = SYMBOL_STRATEGIES.get(symbol, "math_risk_v3")
        strategy = strategies.get(strategy_key)
        
        print(f"\n{symbol} ({strategy_key}):")
        
        df = get_data(connector, symbol)
        if df is None or len(df) < 50:
            print(f"  ERROR: No data")
            continue
        
        direction, atr, atr_ratio, levels = strategy.get_signal(df)
        
        if direction:
            print(f"  SIGNAL: {direction}")
            print(f"  ATR: {atr:.5f}")
            print(f"  SL Distance: {levels['sl_distance']:.5f}")
            print(f"  TP Distance: {levels['tp2']:.5f}")
        else:
            print(f"  NO SIGNAL (filters not met)")
        
        if strategy_key == "rsi":
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta).where(delta < 0, 0).rolling(14).mean()
            # Handle division by zero
            rs = gain / loss.replace(0, 0.0001)
            rsi = 100 - (100 / (1 + rs))
            print(f"  RSI Value: {rsi.iloc[-1]:.2f}")
        
        elif strategy_key == "ema_crossover":
            ema20 = df['close'].ewm(span=20).mean()
            ema50 = df['close'].ewm(span=50).mean()
            print(f"  EMA20: {ema20.iloc[-1]:.5f}")
            print(f"  EMA50: {ema50.iloc[-1]:.5f}")
            print(f"  Price: {df['close'].iloc[-1]:.5f}")
    
    connector.shutdown()

if __name__ == "__main__":
    main()
