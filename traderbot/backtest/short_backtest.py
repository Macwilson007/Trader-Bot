"""
RE-RUN BACKTEST - Using Actual Production Strategy Logic
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add root and traderbot directories to path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
traderbot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(root_dir)
sys.path.append(traderbot_dir)

from traderbot.strategy.entry_signals import MathRiskV3Signals
from traderbot.strategy.rsi_strategy import RSIStrategy
from traderbot.strategy.ema_crossover import EMACrossoverStrategy

if not mt5.initialize():
    print("Initialize failed")
    quit()

mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

STRATEGIES = {
    "XAUUSD": MathRiskV3Signals(),
    "EURUSD": RSIStrategy(),
    "XAGUSD": MathRiskV3Signals()
}

SYMBOLS = ["XAUUSD", "EURUSD", "XAGUSD"]

def run_backtest_with_class(symbol, df, strategy, initial_balance=50.0):
    balance = initial_balance
    trades = []
    wins, losses = 0, 0
    
    # Pip multipliers for dollar conversions on standard lots (simulated)
    # On Cent accounts, these map to cents.
    # Correct pip multipliers for dollar conversions
    if any(x in symbol for x in ["XAU", "XAG", "JPY"]):
        pip_mult = 100
    else:
        pip_mult = 10000
    # For simulation, we assume 1.0 lot scale
    
    for i in range(250, len(df)-12):
        row = df.iloc[i]
        # Session Filter (Matches bot.py session manager logic generally)
        if row['time'].hour not in [7,8,9,13,14,15]: continue
        
        lb = df.iloc[:i+1]
        
        # USE THE ACTUAL CLASS METHOD
        direction, atr, atr_ratio, levels = strategy.get_signal(lb)
        
        if not direction: continue
        
        sl_dist = levels["sl_distance"]
        tp_dist = levels["tp1"] # Strategy classes usually provide tp1/tp2
        
        # Simulated Lot Size (1% Risk)
        # Risk = balance * 0.01
        # Lot = Risk / (SL_dist * Mult)
        risk_amount = balance * 0.01
        lot = risk_amount / (sl_dist * pip_mult)
        lot = max(min(lot, 1.0), 0.01) # Bounds
        
        sl = lb['close'].iloc[-1] - sl_dist if direction == "BUY" else lb['close'].iloc[-1] + sl_dist
        tp = lb['close'].iloc[-1] + tp_dist if direction == "BUY" else lb['close'].iloc[-1] - tp_dist
        
        # Look ahead 12 hours (H1 bars)
        fut = df.iloc[i+1:i+13]
        if len(fut) == 0: continue
        
        sl_hit = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
        tp_hit = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)
        
        if tp_hit:
            pnl = tp_dist * pip_mult * lot
            wins += 1
            balance += pnl
            res = "WIN"
        elif sl_hit:
            pnl = -sl_dist * pip_mult * lot
            losses += 1
            balance += pnl
            res = "LOSS"
        else:
            pnl = 0
            res = "EXPIRED"
            
        trades.append({"time": row['time'], "res": res, "pnl": pnl})
        
    return {"wins": wins, "losses": losses, "final": balance, "trades_list": trades}

print("="*60)
print("PRODUCTION BACKTEST - UPDATED STRATEGIES")
print("Data Range: Last 90 Days | Initial: $50.00")
print("="*60)

for symbol in SYMBOLS:
    print(f"\nEvaluating {symbol}...")
    full_symbol = symbol + "c" # Use cent data for more accurate bars
    h1 = mt5.copy_rates_range(full_symbol, mt5.TIMEFRAME_H1, 
                               datetime.now() - timedelta(days=90), datetime.now())
    if h1 is None or len(h1) == 0:
        print(f"Failed to load {symbol}")
        continue
    
    df = pd.DataFrame(h1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    strategy = STRATEGIES[symbol]
    res = run_backtest_with_class(symbol, df, strategy)
    
    wr = (res['wins'] / (res['wins'] + res['losses'])) * 100 if (res['wins'] + res['losses']) > 0 else 0
    pnl = res['final'] - 50.0
    
    print(f"  Trades: {len(res['trades_list'])} | Wins: {res['wins']} | Losses: {res['losses']}")
    print(f"  Win Rate: {wr:.1f}%")
    print(f"  PnL: ${pnl:+,.2f}")
    print(f"  Final Balance: ${res['final']:.2f}")

mt5.shutdown()
