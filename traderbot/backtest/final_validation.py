"""
FINAL VALIDATION BACKTEST - Multi-Timeframe Strategy Suite
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

from traderbot.strategy.entry_signals import MathRiskV3Signals
from traderbot.strategy.rsi_strategy import RSIStrategy
from traderbot.config import SYMBOLS, SYMBOL_STRATEGIES

if not mt5.initialize():
    quit()

mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

TF_MAP = {
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1
}

STRATEGIES = {
    "math_risk_v3": MathRiskV3Signals(),
    "rsi": RSIStrategy()
}

def run_test(symbol, df, strat):
    balance = 50.0
    wins, losses = 0, 0
    pip_mult = 100 if any(x in symbol for x in ["XAU", "XAG", "JPY"]) else 10000
    
    for i in range(300, len(df)-20):
        row = df.iloc[i]
        if row['time'].hour not in [7,8,9,13,14,15]: continue
        
        lb = df.iloc[:i+1]
        direction, atr, atr_ratio, levels = strat.get_signal(lb)
        if not direction: continue
        
        sl_dist = levels["sl_distance"]
        tp_dist = levels["tp1"]
        risk = balance * 0.01
        lot = max(min(risk / (sl_dist * pip_mult), 1.0), 0.01)
        
        sl = lb['close'].iloc[-1] - sl_dist if direction == "BUY" else lb['close'].iloc[-1] + sl_dist
        tp = lb['close'].iloc[-1] + tp_dist if direction == "BUY" else lb['close'].iloc[-1] - tp_dist
        
        fut = df.iloc[i+1:i+21]
        sl_hit = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
        tp_hit = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)
        
        if tp_hit:
            wins += 1
            balance += tp_dist * pip_mult * lot
        elif sl_hit:
            losses += 1
            balance -= sl_dist * pip_mult * lot
            
    return {"wins": wins, "losses": losses, "final": balance}

print("="*60)
print("FINAL VALIDATION - MULTI-TIMEFRAME SUITE")
print("90 Days | Config: XAU(M30), EUR(M15), XAG(M15)")
print("="*60)

for symbol, info in SYMBOLS.items():
    tf_name = info['timeframe']
    tf_val = TF_MAP[tf_name]
    print(f"Testing {symbol} on {tf_name}...")
    
    h1 = mt5.copy_rates_range(symbol+"c", tf_val, 
                               datetime.now() - timedelta(days=90), datetime.now())
    if h1 is None: continue
    df = pd.DataFrame(h1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    strat_key = SYMBOL_STRATEGIES[symbol]
    res = run_test(symbol, df, STRATEGIES[strat_key])
    
    pnl = res['final'] - 50.0
    print(f"  Trades: {res['wins']+res['losses']} | Wins: {res['wins']} | PnL: ${pnl:+,.2f} | Final: ${res['final']:.2f}")

mt5.shutdown()
