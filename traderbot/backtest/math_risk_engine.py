"""
MATHEMATICAL RISK ENGINE - Simplified & Fixed
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class MathRiskEngine:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.hard_lock_until = None
        
    def get_pip_value(self):
        return 3.5
    
    def get_pip_size(self):
        return 0.01
    
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
    
    def check_regime(self, df, idx):
        if idx < 50:
            return None, False
        
        lookback = df.iloc[:idx+1].copy()
        
        adx, atr = self.calculate_adx(lookback)
        ema200 = self.calculate_ema(lookback['close'], 200)
        
        current_adx = adx.iloc[-1]
        current_price = lookback['close'].iloc[-1]
        current_ema200 = ema200.iloc[-1]
        current_atr = atr.iloc[-1]
        
        mean_atr = atr.tail(20).mean()
        atr_ratio = current_atr / mean_atr if mean_atr > 0 else 1
        
        high_volatility = atr_ratio > 2.0
        
        if current_adx > 25:
            if current_price > current_ema200:
                bias = "BULLISH"
            elif current_price < current_ema200:
                bias = "BEARISH"
            else:
                bias = None
        else:
            bias = None
        
        blocked = high_volatility
        
        return bias, blocked, current_adx, atr_ratio
    
    def check_bos(self, df, idx, direction):
        if idx < 20:
            return False
        
        lookback = df.iloc[idx-19:idx+1]
        
        swing_high = lookback['high'].max()
        swing_low = lookback['low'].min()
        
        current_high = df.iloc[idx]['high']
        current_low = df.iloc[idx]['low']
        current_close = df.iloc[idx]['close']
        
        if direction == "LONG":
            return current_close > swing_high
        elif direction == "SHORT":
            return current_close < swing_low
        
        return False
    
    def run_backtest(self):
        print("="*80)
        print("MATHEMATICAL RISK ENGINE - Simplified")
        print("="*80)
        
        symbol = "XAUUSDc"
        start = datetime.now() - timedelta(days=180)
        end = datetime.now()
        
        print(f"\nLoading {symbol}...")
        
        h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, end)
        
        if h1_rates is None:
            print("Failed to load data")
            return
        
        df = pd.DataFrame(h1_rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        print(f"  H1: {len(df)} bars")
        
        trade_hours = list(range(7, 18))
        
        regime_checks = {"bullish": 0, "bearish": 0, "blocked": 0, "bos": 0}
        
        for i in range(100, len(df) - 12):
            row = df.iloc[i]
            
            if row['time'].hour not in trade_hours:
                continue
            
            if self.hard_lock_until and row['time'] < self.hard_lock_until:
                continue
            
            bias, blocked, adx_val, atr_ratio = self.check_regime(df, i)
            
            if bias is None:
                continue
            
            if bias == "BULLISH":
                regime_checks["bullish"] += 1
            else:
                regime_checks["bearish"] += 1
            
            if blocked:
                regime_checks["blocked"] += 1
                continue
            
            direction = bias
            
            if not self.check_bos(df, i, direction):
                continue
            
            regime_checks["bos"] += 1
            
            entry = row['close']
            pip_size = self.get_pip_size()
            
            adx, atr = self.calculate_adx(df.iloc[:i+1])
            current_atr = atr.iloc[-1]
            
            sl_distance = current_atr * 1.5
            risk_dollars = sl_distance * 100 * self.get_pip_value()
            
            if direction == "LONG":
                sl = entry - sl_distance
                tp1 = entry + sl_distance * 1.5
                tp2 = entry + sl_distance * 2.5
            else:
                sl = entry + sl_distance
                tp1 = entry - sl_distance * 1.5
                tp2 = entry - sl_distance * 2.5
            
            lot_size = min(max((self.balance * 0.01) / risk_dollars, 0.01), 1.0)
            
            future = df.iloc[i:i+12]
            
            tp1_hit = False
            tp2_hit = False
            sl_hit = False
            current_sl = sl
            
            for f in future.itertuples():
                low = f.low
                high = f.high
                
                if direction == "LONG":
                    if low <= current_sl:
                        sl_hit = True
                        break
                    elif high >= tp1 and not tp1_hit:
                        tp1_hit = True
                        current_sl = entry
                    elif high >= tp2:
                        tp2_hit = True
                        break
                else:
                    if high >= current_sl:
                        sl_hit = True
                        break
                    elif low <= tp1 and not tp1_hit:
                        tp1_hit = True
                        current_sl = entry
                    elif low <= tp2:
                        tp2_hit = True
                        break
            
            if tp2_hit:
                result = "TP2"
                pnl = risk_dollars * 2.5 * lot_size
            elif tp1_hit:
                result = "TP1"
                pnl = risk_dollars * 1.5 * lot_size
            elif sl_hit:
                result = "SL"
                pnl = -risk_dollars * lot_size
            else:
                result = "OPEN"
                final_price = future.iloc[-1]['close']
                if direction == "LONG":
                    pnl = (final_price - entry) / pip_size * 3.5 * lot_size
                else:
                    pnl = (entry - final_price) / pip_size * 3.5 * lot_size
            
            self.trades.append({
                "time": row['time'],
                "bias": bias,
                "direction": direction,
                "entry": entry,
                "atr": current_atr,
                "adx": adx_val,
                "atr_ratio": atr_ratio,
                "lot": lot_size,
                "result": result,
                "pnl": pnl
            })
            
            self.balance += pnl
            
            daily_drawdown = (self.initial_balance - self.balance) / self.initial_balance
            if daily_drawdown >= 0.03:
                self.hard_lock_until = row['time'] + timedelta(hours=24)
                print(f"\n!!! CIRCUIT BREAKER: {row['time']} !!!")
        
        self.print_results()
        print(f"\nRegime Checks: {regime_checks}")
    
    def print_results(self):
        wins = [t for t in self.trades if 'TP' in t['result']]
        losses = [t for t in self.trades if t['result'] == 'SL']
        open_trades = [t for t in self.trades if t['result'] == 'OPEN']
        
        tp1_wins = [t for t in self.trades if t['result'] == 'TP1']
        tp2_wins = [t for t in self.trades if t['result'] == 'TP2']
        
        print(f"\n{'='*80}")
        print("RESULTS")
        print(f"{'='*80}")
        print(f"Total Trades: {len(self.trades)}")
        print(f"Wins: {len(wins)} | Losses: {len(losses)} | Open: {len(open_trades)}")
        print(f"TP1: {len(tp1_wins)} | TP2: {len(tp2_wins)}")
        
        if wins or losses:
            closed = wins + losses
            win_rate = len(wins) / len(closed) * 100 if closed else 0
            print(f"\nWin Rate: {win_rate:.1f}%")
            
            total_wins = sum(t['pnl'] for t in wins) if wins else 0
            total_losses = abs(sum(t['pnl'] for t in losses)) if losses else 1
            print(f"Wins: ${total_wins:,.2f} | Losses: ${total_losses:,.2f}")
            
            pf = total_wins / total_losses if total_losses > 0 else 0
            print(f"Profit Factor: {pf:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        print(f"\n{'='*80}")
        print("SAMPLE TRADES")
        print(f"{'='*80}")
        for t in self.trades[:20]:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['direction']:5} | "
                  f"ATR:{t['atr']:.2f} ADX:{t['adx']:.1f} ATRx:{t['atr_ratio']:.1f} | "
                  f"Lot:{t['lot']:.3f} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MathRiskEngine()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()