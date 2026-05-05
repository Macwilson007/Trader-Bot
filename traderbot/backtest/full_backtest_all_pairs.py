"""
FULL BACKTEST - All Currency Pairs with Optimized Parameters
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

mt5.initialize()
mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")

SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD"]

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

def run_backtest(symbol, df, initial_balance=7157.31):
    balance = initial_balance
    trades = []
    wins, losses, cb = 0, 0, 0
    hard_lock = None
    
    pip_val = 3.5 if "XAU" in symbol else 0.00001 if "EUR" in symbol or "GBP" in symbol else 0.00001
    pip_mult = 100 if "XAU" in symbol else 10000
    
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
        risk_dollars = sl_dist * pip_mult * pip_val
        if risk_dollars <= 0: continue
        
        lot = min(max((balance * 0.01) / risk_dollars, 0.01), 1.0)
        sl = price - sl_dist
        tp = price + sl_dist * 2.0
        
        fut = df.iloc[i+1:i+13]
        sl_hit = any(fut['low'] <= sl)
        tp_hit = any(fut['high'] >= tp)
        
        if tp_hit:
            result = "WIN"
            pnl = sl_dist * 2.0 * pip_mult * pip_val * lot
            wins += 1
            balance += pnl
        elif sl_hit:
            result = "LOSS"
            pnl = -sl_dist * pip_mult * pip_val * lot
            losses += 1
            balance += pnl
        else:
            result = "OPEN"
            pnl = 0
        
        trades.append({
            "time": row['time'],
            "entry": price,
            "sl": sl,
            "tp": tp,
            "result": result,
            "pnl": pnl
        })
        
        if (initial_balance - balance) / initial_balance >= 0.03:
            hard_lock = row['time'] + timedelta(hours=24)
            cb += 1
    
    closed = wins + losses
    wr = wins / closed * 100 if closed else 0
    pf = (wins * 2.0) / losses if losses else 99
    net_pnl = balance - initial_balance
    
    return {
        "symbol": symbol,
        "trades": len(trades),
        "closed": closed,
        "wins": wins,
        "losses": losses,
        "open": len(trades) - closed,
        "win_rate": wr,
        "pf": pf,
        "cb": cb,
        "net_pnl": net_pnl,
        "final": balance,
        "trades_list": trades
    }

print("="*70)
print("FULL BACKTEST - OPTIMIZED PARAMETERS")
print("Config: ADX>20, ATRx<3.0, SL:1.5x, TP:2.0x, Hours:[7,8,9,13,14,15]")
print("="*70)

results = []

for symbol in SYMBOLS:
    print(f"\nLoading {symbol}...")
    full_symbol = symbol + "c"
    h1 = mt5.copy_rates_range(full_symbol, mt5.TIMEFRAME_H1, 
                               datetime.now() - timedelta(days=365), datetime.now())
    if h1 is None or len(h1) == 0:
        print(f"  Failed to load {symbol}")
        continue
    
    df = pd.DataFrame(h1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    print(f"  Loaded {len(df)} bars")
    
    result = run_backtest(symbol, df)
    results.append(result)
    
    print(f"\n{'='*70}")
    print(f"{symbol} RESULTS")
    print(f"{'='*70}")
    print(f"Total Opportunities: {result['trades']}")
    print(f"Closed Trades: {result['closed']} | Wins: {result['wins']} | Losses: {result['losses']} | Open: {result['open']}")
    print(f"Win Rate: {result['win_rate']:.1f}%")
    print(f"Profit Factor: {result['pf']:.2f}")
    print(f"Circuit Breakers: {result['cb']}")
    print(f"Net P&L: ${result['net_pnl']:+,.2f}")
    print(f"Final Balance: ${result['final']:,.2f}")
    
    print(f"\nAll Trades:")
    print(f"{'='*70}")
    print(f"{'Time':<20} {'Entry':<12} {'SL':<12} {'TP':<12} {'Result':<8} {'P&L':<12}")
    print(f"{'-'*70}")
    for t in result['trades_list']:
        print(f"{t['time'].strftime('%Y-%m-%d %H:%M'):<20} {t['entry']:<12.5f} {t['sl']:<12.5f} {t['tp']:<12.5f} {t['result']:<8} ${t['pnl']:+,.2f}")

# Summary
print("\n" + "="*70)
print("SUMMARY - ALL PAIRS")
print("="*70)
print(f"{'Symbol':<12} {'Trades':<8} {'Wins':<6} {'Losses':<8} {'WR%':<8} {'PF':<8} {'CB':<4} {'P&L':<12}")
print("-"*70)
total_pnl = 0
for r in results:
    print(f"{r['symbol']:<12} {r['trades']:<8} {r['wins']:<6} {r['losses']:<8} {r['win_rate']:<8.1f} {r['pf']:<8.2f} {r['cb']:<4} ${r['net_pnl']:+,.2f}")
    total_pnl += r['net_pnl']

print("-"*70)
print(f"{'TOTAL':<12} {sum(r['trades'] for r in results):<8} {sum(r['wins'] for r in results):<6} {sum(r['losses'] for r in results):<8} "
      f"{sum(r['wins'] for r in results)/max(sum(r['closed'] for r in results),1)*100:<8.1f} "
      f"{sum(r['wins'] for r in results)*2.0/max(sum(r['losses'] for r in results),1):<8.2f} "
      f"{sum(r['cb'] for r in results):<4} ${total_pnl:+,.2f}")

mt5.shutdown()
