"""
PAIR DISCOVERY BACKTEST - Finding a replacement for GBPUSD
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
traderbot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(root_dir)
sys.path.append(traderbot_dir)
from traderbot.strategy.ema_crossover import EMACrossoverStrategy
from traderbot.strategy.entry_signals import MathRiskV3Signals

if not mt5.initialize():
    quit()

mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

# Strategy to test (EMA Crossover is preferred for trending pairs)
strategy = EMACrossoverStrategy(fast_period=10, slow_period=30, tp_r=3.0)
# Also testing MathRiskV3 which works great on Gold
strategy_math = MathRiskV3Signals()

CANDIDATES = ["USDJPY", "AUDUSD", "XAGUSD", "USDCAD", "EURJPY"]

def run_test(symbol, df, strat):
    balance = 50.0
    wins, losses = 0, 0
    pip_mult = 100 if "JPY" in symbol or "XAU" in symbol or "XAG" in symbol else 10000
    
    for i in range(250, len(df)-12):
        row = df.iloc[i]
        if row['time'].hour not in [7,8,9,13,14,15]: continue
        
        lb = df.iloc[:i+1]
        direction, atr, atr_ratio, levels = strat.get_signal(lb)
        if not direction: continue
        
        sl_dist = levels["sl_distance"]
        tp_dist = levels["tp1"]
        risk = balance * 0.01
        lot = risk / (sl_dist * pip_mult)
        lot = max(min(lot, 1.0), 0.01)
        
        sl = lb['close'].iloc[-1] - sl_dist if direction == "BUY" else lb['close'].iloc[-1] + sl_dist
        tp = lb['close'].iloc[-1] + tp_dist if direction == "BUY" else lb['close'].iloc[-1] - tp_dist
        
        fut = df.iloc[i+1:i+13]
        sl_hit = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
        tp_hit = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)
        
        if tp_hit:
            wins += 1
            balance += tp_dist * pip_mult * lot
        elif sl_hit:
            losses += 1
            balance -= sl_dist * pip_mult * lot
            
    return {"wins": wins, "losses": losses, "pnl": balance - 50.0}

print("="*60)
print("PAIR DISCOVERY - 90 DAY BACKTEST")
print("="*60)

results = []
for symbol in CANDIDATES:
    print(f"Testing {symbol}...")
    full_symbol = symbol + "c"
    h1 = mt5.copy_rates_range(full_symbol, mt5.TIMEFRAME_H1, 
                               datetime.now() - timedelta(days=90), datetime.now())
    if h1 is None or len(h1) == 0:
        continue
    
    df = pd.DataFrame(h1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    res_ema = run_test(symbol, df, strategy)
    res_math = run_test(symbol, df, strategy_math)
    
    results.append({
        "symbol": symbol,
        "EMA_PnL": res_ema['pnl'], "EMA_Trades": res_ema['wins'] + res_ema['losses'],
        "Math_PnL": res_math['pnl'], "Math_Trades": res_math['wins'] + res_math['losses']
    })

print("\n" + "="*80)
print(f"{'Symbol':<12} {'EMA PnL':<15} {'EMA Trades':<12} {'Math PnL':<15} {'Math Trades':<12}")
print("-" * 80)
for r in results:
    print(f"{r['symbol']:<12} ${r['EMA_PnL']:<14.2f} {r['EMA_Trades']:<12} ${r['Math_PnL']:<14.2f} {r['Math_Trades']:<12}")

mt5.shutdown()
