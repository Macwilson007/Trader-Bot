"""
LOSS REDUCTION TEST - Wider stops, more trading hours
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

mt5.initialize()
mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

def calculate_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.rolling(period).mean(), atr

def test_params(df, adx_min, atr_thresh, sl_mult, tp_mult, hours):
    initial = 7157.31
    balance = initial
    wins, losses, open_trades = 0, 0, 0
    cb_count = 0
    hard_lock = None
    
    for i in range(100, len(df) - 12):
        row = df.iloc[i]
        if row['time'].hour not in hours:
            continue
        
        if hard_lock and row['time'] < hard_lock:
            continue
        
        lookback = df.iloc[:i+1]
        adx, atr = calculate_adx(lookback)
        
        if pd.isna(adx.iloc[-1]):
            continue
        
        atr_ratio = atr.iloc[-1] / atr.tail(20).mean()
        if atr_ratio > atr_thresh or adx.iloc[-1] <= adx_min:
            continue
        
        ema200 = lookback['close'].ewm(span=200).mean().iloc[-1]
        ema20_series = lookback['close'].ewm(span=20).mean()
        ema20 = ema20_series.iloc[-1]
        ema20_prev = ema20_series.iloc[-2]
        price = lookback['close'].iloc[-1]
        
        if price <= ema200:
            continue
        
        prev_close = lookback['close'].iloc[-2]
        if not (prev_close < ema20_prev and price > ema20):
            continue
        
        sl_dist = atr.iloc[-1] * sl_mult
        lot = min(max((balance * 0.01) / (sl_dist * 350), 0.01), 1.0)
        sl = price - sl_dist
        tp = price + sl_dist * tp_mult
        
        future = df.iloc[i+1:i+13]
        sl_hit = any(future['low'] <= sl)
        tp_hit = any(future['high'] >= tp)
        
        if tp_hit:
            wins += 1
            balance += sl_dist * tp_mult * 350 * lot
        elif sl_hit:
            losses += 1
            balance -= sl_dist * 350 * lot
        else:
            open_trades += 1
        
        if (initial - balance) / initial >= 0.03:
            hard_lock = row['time'] + timedelta(hours=24)
            cb_count += 1
    
    closed = wins + losses
    return {
        'adx': adx_min, 'atr': atr_thresh, 'sl': sl_mult, 'tp': tp_mult,
        'hours': hours, 'wins': wins, 'losses': losses, 'open': open_trades,
        'wr': wins/closed*100 if closed else 0,
        'pf': (wins * tp_mult) / losses if losses else 99,
        'pnl': balance - initial, 'bal': balance, 'cb': cb_count
    }

print("Loading data...")
h1 = mt5.copy_rates_range("XAUUSDc", mt5.TIMEFRAME_H1, datetime.now() - timedelta(days=365), datetime.now())
df = pd.DataFrame(h1)
df['time'] = pd.to_datetime(df['time'], unit='s')
print(f"Data: {len(df)} bars\n")

results = []

configs = [
    ((8, 13), 25, 2.5, 1.5, 2.5),
    ((8, 13), 25, 2.5, 2.0, 2.0),
    ((8, 10, 13, 15), 25, 2.5, 1.5, 2.5),
    ((8, 10, 13, 15), 25, 2.5, 2.0, 2.0),
    ((7, 8, 9, 13, 14, 15), 20, 2.5, 1.5, 2.0),
    ((7, 8, 9, 13, 14, 15), 20, 2.5, 2.0, 2.0),
    ((8, 10, 13, 15), 20, 2.5, 2.0, 2.0),
    ((8, 10, 13, 15), 25, 2.5, 2.5, 2.0),
    ((8, 10, 13, 15), 25, 2.5, 2.5, 1.5),
    ((8, 10, 13, 15), 25, 3.0, 2.0, 1.5),
]

print("Testing configs...\n")
for hours, adx, atr, sl, tp in configs:
    r = test_params(df, adx, atr, sl, tp, hours)
    results.append(r)
    h_str = ','.join(map(str, hours))
    print(f"H:{h_str} ADX>{adx} ATRx<{atr} SL:{sl}x TP:{tp}x | WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} | W:{r['wins']} L:{r['losses']} O:{r['open']} | ${r['pnl']:+,.0f}")

print("\n" + "="*70)
print("SORTED BY P&L")
print("="*70)
for r in sorted(results, key=lambda x: x['pnl'], reverse=True):
    h_str = ','.join(map(str, r['hours']))
    print(f"H:{h_str} ADX>{r['adx']} ATRx<{r['atr']} SL:{r['sl']}x TP:{r['tp']}x | "
          f"WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} | W:{r['wins']} L:{r['losses']} | ${r['pnl']:+,.0f}")

print("\n" + "="*70)
print("SORTED BY FEWEST CIRCUIT BREAKERS")
print("="*70)
for r in sorted(results, key=lambda x: (x['cb'], -x['pnl'])):
    h_str = ','.join(map(str, r['hours']))
    print(f"H:{h_str} ADX>{r['adx']} ATRx<{r['atr']} SL:{r['sl']}x TP:{r['tp']}x | "
          f"WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} | W:{r['wins']} L:{r['losses']} | ${r['pnl']:+,.0f}")

mt5.shutdown()
