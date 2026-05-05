"""
VERIFY OPTIMIZED CONFIG
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

mt5.initialize()
mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

def calc_adx(df, p=14):
    h, l, c = df['high'], df['low'], df['close']
    pdm = h.diff().clip(lower=0)
    mdm = (-l.diff()).clip(lower=0)
    tr = pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)
    a = tr.rolling(p).mean()
    di = 100*pdm.rolling(p).mean()/a
    mdi = 100*mdm.rolling(p).mean()/a
    dx = 100*abs(di-mdi)/(di+mdi)
    return dx.rolling(p).mean(), a

def run():
    h1 = mt5.copy_rates_range("XAUUSDc", mt5.TIMEFRAME_H1, datetime.now()-timedelta(days=365), datetime.now())
    df = pd.DataFrame(h1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    initial = 7157.31
    bal = initial
    wins, losses, cb = 0, 0, 0
    hard_lock = None
    
    for i in range(100, len(df)-12):
        row = df.iloc[i]
        if row['time'].hour not in [7,8,9,13,14,15]: continue
        if hard_lock and row['time'] < hard_lock: continue
        
        lb = df.iloc[:i+1]
        adx, atr = calc_adx(lb)
        if pd.isna(adx.iloc[-1]): continue
        
        if atr.iloc[-1]/atr.tail(20).mean() > 3.0 or adx.iloc[-1] <= 20: continue
        
        ema200 = lb['close'].ewm(span=200).mean().iloc[-1]
        ema20s = lb['close'].ewm(span=20).mean()
        ema20, ema20p = ema20s.iloc[-1], ema20s.iloc[-2]
        price = lb['close'].iloc[-1]
        if price <= ema200: continue
        if not (lb['close'].iloc[-2] < ema20p and price > ema20): continue
        
        sl_dist = atr.iloc[-1] * 1.5
        lot = min(max((bal*0.01)/(sl_dist*350), 0.01), 1.0)
        sl = price - sl_dist
        tp = price + sl_dist * 2.0
        
        fut = df.iloc[i+1:i+13]
        if any(fut['high'] >= tp): wins += 1; bal += sl_dist*2.0*350*lot
        elif any(fut['low'] <= sl): losses += 1; bal -= sl_dist*350*lot
        
        if (initial-bal)/initial >= 0.03:
            hard_lock = row['time'] + timedelta(hours=24); cb += 1
    
    closed = wins+losses
    wr = wins/closed*100 if closed else 0
    pf = (wins*2.0)/losses if losses else 99
    
    print("="*60)
    print("OPTIMIZED CONFIG BACKTEST")
    print("="*60)
    print(f"Parameters: ADX>20, ATRx<3.0, SL:1.5x, TP:2.0x")
    print(f"Hours: 7,8,9,13,14,15")
    print("="*60)
    print(f"Total Trades: {wins+losses}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {wr:.1f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Circuit Breakers: {cb}")
    print(f"Net P&L: ${bal-initial:+,.2f}")
    print(f"Final Balance: ${bal:,.2f}")
    print("="*60)

run()
mt5.shutdown()
