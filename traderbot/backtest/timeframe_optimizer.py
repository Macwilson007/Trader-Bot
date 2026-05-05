"""
TIMEFRAME OPTIMIZER - Finding the best execution frequency
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

if not mt5.initialize():
    quit()

mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4
}

SYMBOLS = {
    "XAUUSD": MathRiskV3Signals(),
    "EURUSD": RSIStrategy(),
    "XAGUSD": MathRiskV3Signals()
}

HOURS = [7, 8, 9, 13, 14, 15] # Peak London & NY

def run_test(symbol, df, strat, timeframe_name):
    balance = 50.0
    wins, losses = 0, 0
    trades_by_day = {}
    
    if any(x in symbol for x in ["XAU", "XAG", "JPY"]):
        pip_mult = 100
    else:
        pip_mult = 10000

    # Minimum lookback adjusted for timeframe
    min_lookback = 300
    if len(df) < min_lookback + 50: return None
    
    for i in range(min_lookback, len(df)-20):
        row = df.iloc[i]
        if row['time'].hour not in HOURS: continue
        
        lb = df.iloc[:i+1]
        direction, atr, atr_ratio, levels = strat.get_signal(lb)
        if not direction: continue
        
        day = row['time'].date()
        trades_by_day[day] = trades_by_day.get(day, 0) + 1
        
        sl_dist = levels["sl_distance"]
        tp_dist = levels["tp1"]
        risk = balance * 0.01
        lot = risk / (sl_dist * pip_mult)
        lot = max(min(lot, 1.0), 0.01)
        
        sl = lb['close'].iloc[-1] - sl_dist if direction == "BUY" else lb['close'].iloc[-1] + sl_dist
        tp = lb['close'].iloc[-1] + tp_dist if direction == "BUY" else lb['close'].iloc[-1] - tp_dist
        
        # Look ahead 20 bars of the CURRENT timeframe
        fut = df.iloc[i+1:i+21]
        sl_hit = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
        tp_hit = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)
        
        if tp_hit:
            wins += 1
            balance += tp_dist * pip_mult * lot
        elif sl_hit:
            losses += 1
            balance -= sl_dist * pip_mult * lot
            
    total_trades = wins + losses
    avg_per_day = total_trades / 65 if total_trades > 0 else 0 # Approx 65 trading days in 90 cal days
    
    return {
        "pnl": balance - 50.0,
        "trades": total_trades,
        "avg_daily": avg_per_day,
        "wr": (wins/total_trades*100) if total_trades > 0 else 0
    }

print("="*80)
print(f"{'TF':<6} {'Symbol':<12} {'PnL':<12} {'Trades':<10} {'Avg/Day':<10} {'WR%':<8}")
print("="*80)

results = []
for tf_name, tf_val in TIMEFRAMES.items():
    for symbol, strat in SYMBOLS.items():
        h1 = mt5.copy_rates_range(symbol+"c", tf_val, 
                                   datetime.now() - timedelta(days=90), datetime.now())
        if h1 is None: continue
        df = pd.DataFrame(h1)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        res = run_test(symbol, df, strat, tf_name)
        if res:
            print(f"{tf_name:<6} {symbol:<12} ${res['pnl']:<11.2f} {res['trades']:<10} {res['avg_daily']:<10.2f} {res['wr']:<8.1f}")
            results.append({"tf": tf_name, "symbol": symbol, **res})

mt5.shutdown()
