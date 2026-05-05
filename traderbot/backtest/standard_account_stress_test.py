"""
STANDARD ACCOUNT STRESS TEST - Why $50 is dangerous on Standard
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

TF_MAP = {"M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30}
STRATEGIES = {"math_risk_v3": MathRiskV3Signals(), "rsi": RSIStrategy()}

def run_stress_test(symbol, df, strat):
    balance = 50.0 # $50 Standard
    wins, losses = 0, 0
    blown = False
    
    # FOR STANDARD ACCOUNT 0.01 Lot:
    # Gold: $1/point
    # Forex: $0.10/pip
    if "XAU" in symbol or "XAG" in symbol:
        pip_mult = 100
        lot_val = 0.01 # $0.01 per point per 0.01 lot? No.
        # Constant: 0.01 lot Gold -> $1 per $1.00 move. 
        # In my logic: pnl = dist * pip_mult * lot_size
        # For Gold: pnl = 1.00 * 100 * 0.01 = $1.00. Correct.
    else:
        pip_mult = 10000
        # For Forex: pnl = 0.0001 * 10000 * 0.01 = $0.01? 
        # No, 0.01 lot EURUSD is $0.10 per pip.
        # My logic: pnl = 0.0001 * 10000 * 0.01 = 0.01 USD. 
        # Wait, 1 pip = 0.0001. So pnl = 0.0001 * 10000 * 0.10? No.
        # Let's fix it: pnl = dist * 10000 * 0.10 (for 0.01 lot)
        pass

    for i in range(300, len(df)-20):
        if balance <= 0:
            blown = True
            break
            
        row = df.iloc[i]
        if row['time'].hour not in [7,8,9,13,14,15]: continue
        
        lb = df.iloc[:i+1]
        direction, atr, atr_ratio, levels = strat.get_signal(lb)
        if not direction: continue
        
        sl_dist = levels["sl_distance"]
        tp_dist = levels["tp1"]
        
        # ON STANDARD ACCOUNT, MIN LOT IS 0.01
        lot = 0.01 
        
        # Calculate PnL for 0.01 lot
        if "XAU" in symbol or "XAG" in symbol:
            pnl_per_win = tp_dist * 100 * lot # $1 per $1 move
            pnl_per_loss = -sl_dist * 100 * lot
        else:
            pnl_per_win = tp_dist * 10000 * lot * 10 # $0.10 per pip
            pnl_per_loss = -sl_dist * 10000 * lot * 10
            
        sl = lb['close'].iloc[-1] - sl_dist if direction == "BUY" else lb['close'].iloc[-1] + sl_dist
        tp = lb['close'].iloc[-1] + tp_dist if direction == "BUY" else lb['close'].iloc[-1] - tp_dist
        
        fut = df.iloc[i+1:i+21]
        sl_hit = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
        tp_hit = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)
        
        if tp_hit:
            wins += 1
            balance += pnl_per_win
        elif sl_hit:
            losses += 1
            balance += pnl_per_loss
            
    return {"wins": wins, "losses": losses, "final": balance, "blown": blown}

print("="*60)
print("STANDARD ACCOUNT STRESS TEST ($50.00 Initial)")
print("Logic: Forced 0.01 Minimum Lot (Standard)")
print("="*60)

for symbol, info in SYMBOLS.items():
    tf_name = info['timeframe']
    print(f"Testing {symbol} ({tf_name})...")
    
    h1 = mt5.copy_rates_range(symbol+"c", TF_MAP[tf_name], 
                               datetime.now() - timedelta(days=90), datetime.now())
    if h1 is None: continue
    df = pd.DataFrame(h1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    res = run_stress_test(symbol, df, STRATEGIES[SYMBOL_STRATEGIES[symbol]])
    
    status = "BLOWN! 💀" if res['blown'] or res['final'] <= 0 else "SURVIVED"
    print(f"  Trades: {res['wins']+res['losses']} | Wins: {res['wins']} | Final: ${res['final']:.2f} | Status: {status}")

mt5.shutdown()
