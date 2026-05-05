"""
FAST PARAMETER OPTIMIZATION - Focus on loss reduction
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from itertools import product

class FastOptimizer:
    def __init__(self):
        self.initial_balance = 7157.31
        self.results = []
    
    def calculate_adx(self, df, period=14):
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx, atr
    
    def calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
    
    def run_test(self, adx_min, atr_thresh, sl_mult, tp2_r, df):
        balance = self.initial_balance
        wins, losses, open_trades = 0, 0, 0
        cb_count = 0
        hard_lock = None
        
        for i in range(100, len(df) - 12):
            row = df.iloc[i]
            hour = row['time'].hour
            
            if hour not in [8, 10, 13, 15]:
                continue
            
            if hard_lock and row['time'] < hard_lock:
                continue
            
            lookback = df.iloc[:i+1].copy()
            adx, atr = self.calculate_adx(lookback)
            ema200 = self.calculate_ema(lookback['close'], 200)
            ema20 = self.calculate_ema(lookback['close'], 20)
            
            if pd.isna(adx.iloc[-1]):
                continue
            
            current_atr = atr.iloc[-1]
            atr_ratio = current_atr / atr.tail(20).mean()
            
            if atr_ratio > atr_thresh or adx.iloc[-1] <= adx_min:
                continue
            
            price = lookback['close'].iloc[-1]
            if price <= ema200.iloc[-1]:
                continue
            
            prev_close = lookback['close'].iloc[-2]
            if not (prev_close < ema20.iloc[-2] and price > ema20.iloc[-1]):
                continue
            
            entry = row['close']
            sl_dist = current_atr * sl_mult
            
            lot_size = min(max((balance * 0.01) / (sl_dist * 100 * 3.5), 0.01), 1.0)
            sl = entry - sl_dist
            tp2 = entry + sl_dist * tp2_r
            
            future = df.iloc[i:i+12]
            sl_hit = False
            tp_hit = False
            
            for f in future.itertuples():
                if f.low <= sl:
                    sl_hit = True
                    break
                elif f.high >= tp2:
                    tp_hit = True
                    break
            
            if tp_hit:
                wins += 1
                balance += sl_dist * tp2_r * 100 * 3.5 * lot_size
            elif sl_hit:
                losses += 1
                balance -= sl_dist * 100 * 3.5 * lot_size
            else:
                open_trades += 1
            
            if (self.initial_balance - balance) / self.initial_balance >= 0.03:
                hard_lock = row['time'] + timedelta(hours=24)
                cb_count += 1
        
        closed = wins + losses
        wr = wins / closed * 100 if closed else 0
        pf = (wins * tp2_r) / losses if losses else float('inf')
        
        return {
            'adx_min': adx_min, 'atr_thresh': atr_thresh, 'sl_mult': sl_mult, 'tp2_r': tp2_r,
            'trades': closed, 'wins': wins, 'losses': losses, 'open': open_trades,
            'wr': wr, 'pf': pf, 'cb': cb_count, 'pnl': balance - self.initial_balance
        }
    
    def optimize(self):
        print("Loading data...")
        h1 = mt5.copy_rates_range("XAUUSDc", mt5.TIMEFRAME_H1, datetime.now() - timedelta(days=365), datetime.now())
        df = pd.DataFrame(h1)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"Loaded {len(df)} bars\n")
        
        params = list(product([30, 35, 40], [1.5, 2.0], [2.0, 2.5, 3.0], [2.0, 2.5, 3.0]))
        
        for adx, atr, sl, tp in params:
            r = self.run_test(adx, atr, sl, tp, df)
            self.results.append(r)
            print(f"ADX>{adx} ATRx<{atr} SL:{sl}x TP:{tp}x | WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} P&L:${r['pnl']:+,.0f}")
        
        self.print_summary()
    
    def print_summary(self):
        print("\n" + "="*70)
        print("TOP 10 BY P&L")
        print("="*70)
        for r in sorted(self.results, key=lambda x: x['pnl'], reverse=True)[:10]:
            print(f"ADX>{r['adx_min']} ATRx<{r['atr_thresh']} SL:{r['sl_mult']}x TP:{r['tp2_r']}x | "
                  f"WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} | ${r['pnl']:+,.0f}")
        
        print("\n" + "="*70)
        print("TOP 10 BY PROFIT FACTOR (min 50 trades)")
        print("="*70)
        filtered = [r for r in self.results if r['trades'] >= 50]
        for r in sorted(filtered, key=lambda x: x['pf'], reverse=True)[:10]:
            print(f"ADX>{r['adx_min']} ATRx<{r['atr_thresh']} SL:{r['sl_mult']}x TP:{r['tp2_r']}x | "
                  f"WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} | ${r['pnl']:+,.0f}")
        
        print("\n" + "="*70)
        print("LOWEST CIRCUIT BREAKERS (min 50 trades)")
        print("="*70)
        for r in sorted(filtered, key=lambda x: (x['cb'], -x['pnl']))[:10]:
            print(f"ADX>{r['adx_min']} ATRx<{r['atr_thresh']} SL:{r['sl_mult']}x TP:{r['tp2_r']}x | "
                  f"WR:{r['wr']:.0f}% PF:{r['pf']:.1f} CB:{r['cb']} | ${r['pnl']:+,.0f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    FastOptimizer().optimize()
    mt5.shutdown()

if __name__ == "__main__":
    main()
