"""
PARAMETER OPTIMIZATION - Find best parameters to reduce losses
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from itertools import product

class ParameterOptimizer:
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
        
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx, atr
    
    def calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
    
    def run_backtest(self, params, df, trade_hours):
        balance = self.initial_balance
        trades = []
        hard_lock_until = None
        
        adx_min = params['adx_min']
        atr_vol_threshold = params['atr_vol_threshold']
        sl_multiplier = params['sl_multiplier']
        tp1_r = params['tp1_r']
        tp2_r = params['tp2_r']
        risk_pct = params['risk_pct']
        
        for i in range(100, len(df) - 12):
            row = df.iloc[i]
            
            if row['time'].hour not in trade_hours:
                continue
            
            if hard_lock_until and row['time'] < hard_lock_until:
                continue
            
            lookback = df.iloc[:i+1].copy()
            adx, atr = self.calculate_adx(lookback)
            ema200 = self.calculate_ema(lookback['close'], 200)
            ema20 = self.calculate_ema(lookback['close'], 20)
            
            if pd.isna(adx.iloc[-1]) or pd.isna(atr.iloc[-1]):
                continue
            
            current_adx = adx.iloc[-1]
            current_price = lookback['close'].iloc[-1]
            current_ema200 = ema200.iloc[-1]
            current_ema20 = ema20.iloc[-1]
            current_atr = atr.iloc[-1]
            
            mean_atr = atr.tail(20).mean()
            atr_ratio = current_atr / mean_atr if mean_atr > 0 else 1
            
            if atr_ratio > atr_vol_threshold:
                continue
            
            if current_adx <= adx_min:
                continue
            
            if current_price <= current_ema200 and current_price >= current_ema200:
                continue
            
            direction = "LONG" if current_price > current_ema200 else "SHORT"
            
            prev_close = lookback['close'].iloc[-2]
            prev_ema20 = ema20.iloc[-2]
            
            if direction == "LONG":
                if not (prev_close < prev_ema20 and current_price > current_ema20):
                    continue
            else:
                if not (prev_close > prev_ema20 and current_price < current_ema20):
                    continue
            
            entry = row['close']
            sl_distance = current_atr * sl_multiplier
            risk_dollars = sl_distance * 100 * 3.5
            
            if risk_dollars <= 0:
                continue
            
            lot_size = min(max((balance * risk_pct) / risk_dollars, 0.01), 1.0)
            
            if direction == "LONG":
                sl = entry - sl_distance
                tp1 = entry + sl_distance * tp1_r
                tp2 = entry + sl_distance * tp2_r
            else:
                sl = entry + sl_distance
                tp1 = entry - sl_distance * tp1_r
                tp2 = entry - sl_distance * tp2_r
            
            future = df.iloc[i:i+12]
            tp1_hit = False
            tp2_hit = False
            sl_hit = False
            current_sl = sl
            
            for f in future.itertuples():
                if direction == "LONG":
                    if f.low <= current_sl:
                        sl_hit = True
                        break
                    elif f.high >= tp1 and not tp1_hit:
                        tp1_hit = True
                        current_sl = entry
                    elif f.high >= tp2:
                        tp2_hit = True
                        break
                else:
                    if f.high >= current_sl:
                        sl_hit = True
                        break
                    elif f.low <= tp1 and not tp1_hit:
                        tp1_hit = True
                        current_sl = entry
                    elif f.low <= tp2:
                        tp2_hit = True
                        break
            
            if tp2_hit:
                result = "TP2"
                pnl = risk_dollars * tp2_r * lot_size
            elif tp1_hit:
                result = "TP1"
                pnl = risk_dollars * tp1_r * lot_size
            elif sl_hit:
                result = "SL"
                pnl = -risk_dollars * lot_size
            else:
                result = "OPEN"
                final_price = future.iloc[-1]['close']
                pnl = (final_price - entry) / 0.01 * 3.5 * lot_size if direction == "LONG" else (entry - final_price) / 0.01 * 3.5 * lot_size
            
            trades.append({"result": result, "pnl": pnl})
            balance += pnl
            
            if (self.initial_balance - balance) / self.initial_balance >= 0.03:
                hard_lock_until = row['time'] + timedelta(hours=24)
        
        wins = [t for t in trades if 'TP' in t['result']]
        losses = [t for t in trades if t['result'] == 'SL']
        closed = wins + losses
        
        win_rate = len(wins) / len(closed) * 100 if closed else 0
        total_wins = sum(t['pnl'] for t in wins) if wins else 0
        total_losses = abs(sum(t['pnl'] for t in losses)) if losses else 1
        pf = total_wins / total_losses if total_losses > 0 else 0
        net_pnl = balance - self.initial_balance
        
        return {
            'params': params,
            'trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'pf': pf,
            'net_pnl': net_pnl,
            'final_balance': balance
        }
    
    def optimize(self):
        print("Loading data...")
        symbol = "XAUUSDc"
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        
        h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, end)
        if h1_rates is None:
            print("Failed to load data")
            return
        
        df = pd.DataFrame(h1_rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"Loaded {len(df)} bars")
        
        param_grid = {
            'adx_min': [30, 35, 40],
            'atr_vol_threshold': [1.5, 2.0],
            'sl_multiplier': [2.0, 2.5, 3.0],
            'tp1_r': [1.0, 1.5],
            'tp2_r': [2.0, 2.5, 3.0],
            'risk_pct': [0.005, 0.01],
        }
        
        trade_hours_options = [
            [8, 10, 13, 15],
            [8, 13],
            list(range(7, 18)),
        ]
        
        keys = list(param_grid.keys())
        values = [param_grid[k] for k in keys]
        
        total_combinations = len(values[0]) * len(values[1]) * len(values[2]) * len(values[3]) * len(values[4]) * len(values[5])
        print(f"Testing {total_combinations * len(trade_hours_options)} combinations...")
        
        count = 0
        for combo in product(*values):
            for trade_hours in trade_hours_options:
                params = dict(zip(keys, combo))
                params['trade_hours'] = trade_hours
                
                result = self.run_backtest(params, df, trade_hours)
                self.results.append(result)
                count += 1
                
                if count % 50 == 0:
                    print(f"Progress: {count}/{total_combinations * len(trade_hours_options)}")
        
        self.print_top_results()
    
    def print_top_results(self):
        print("\n" + "="*80)
        print("TOP 20 RESULTS (by Net P&L)")
        print("="*80)
        
        sorted_results = sorted(self.results, key=lambda x: x['net_pnl'], reverse=True)
        
        for i, r in enumerate(sorted_results[:20], 1):
            p = r['params']
            print(f"\n#{i} | P&L: ${r['net_pnl']:+,.2f} | Balance: ${r['final_balance']:,.2f}")
            print(f"   ADX>{p['adx_min']} | ATRx<{p['atr_vol_threshold']} | SL:{p['sl_multiplier']}x | TP1:{p['tp1_r']}x | TP2:{p['tp2_r']}x | Risk:{p['risk_pct']*100}%")
            print(f"   Trades:{r['trades']} | WR:{r['win_rate']:.1f}% | PF:{r['pf']:.2f} | Wins:{r['wins']} Losses:{r['losses']}")
        
        print("\n" + "="*80)
        print("TOP 10 RESULTS (by Win Rate, min 50 trades)")
        print("="*80)
        
        filtered = [r for r in self.results if r['trades'] >= 50]
        sorted_by_wr = sorted(filtered, key=lambda x: x['win_rate'], reverse=True)
        
        for i, r in enumerate(sorted_by_wr[:10], 1):
            p = r['params']
            print(f"\n#{i} | WR:{r['win_rate']:.1f}% | P&L: ${r['net_pnl']:+,.2f}")
            print(f"   ADX>{p['adx_min']} | ATRx<{p['atr_vol_threshold']} | SL:{p['sl_multiplier']}x | TP1:{p['tp1_r']}x | TP2:{p['tp2_r']}x | Risk:{p['risk_pct']*100}%")
            print(f"   Trades:{r['trades']} | PF:{r['pf']:.2f} | Wins:{r['wins']} Losses:{r['losses']}")
        
        print("\n" + "="*80)
        print("TOP 10 RESULTS (by Profit Factor, min 50 trades)")
        print("="*80)
        
        sorted_by_pf = sorted(filtered, key=lambda x: x['pf'], reverse=True)
        
        for i, r in enumerate(sorted_by_pf[:10], 1):
            p = r['params']
            print(f"\n#{i} | PF:{r['pf']:.2f} | P&L: ${r['net_pnl']:+,.2f}")
            print(f"   ADX>{p['adx_min']} | ATRx<{p['atr_vol_threshold']} | SL:{p['sl_multiplier']}x | TP1:{p['tp1_r']}x | TP2:{p['tp2_r']}x | Risk:{p['risk_pct']*100}%")
            print(f"   Trades:{r['trades']} | WR:{r['win_rate']:.1f}% | Wins:{r['wins']} Losses:{r['losses']}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    optimizer = ParameterOptimizer()
    optimizer.optimize()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()
