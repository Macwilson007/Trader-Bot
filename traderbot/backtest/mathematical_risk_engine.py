"""
TRADING STRATEGY: "Mathematical Risk Engine"

Rules:
A. Market Regime Filter:
   - ADX(14) > 25 AND Price > EMA(200) for bullish
   - Z-Score of ATR: If current_ATR > 2.0 * mean_ATR, block entries

B. Break of Structure:
   - Long: Close > max(High, 20)
   - Short: Close < min(Low, 20)

C. Position Sizing:
   - LotSize = (AccountBalance * 0.01) / (ATR(14) * 1.5)

D. Take Profit:
   - TP1 (50%): 1.5 × Risk, move SL to BE
   - TP2 (Full): 2.5 × Risk

E. Circuit Breaker:
   - If Daily Drawdown >= 3%, kill all trades, lock 24 hours
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class MathematicalRiskEngine:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.equity = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.hard_lock_until = None
        
    def get_pip_value(self):
        return 3.5
    
    def get_pip_size(self):
        return 0.01
    
    def calculate_adx(self, high, low, close, period=14):
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
    
    def calculate_ema(self, data, period):
        return data.ewm(span=period, adjust=False).mean()
    
    def calculate_atr_zscore(self, atr, period=20):
        mean_atr = atr.rolling(window=period).mean()
        std_atr = atr.rolling(window=period).std()
        zscore = (atr - mean_atr) / std_atr
        return zscore
    
    def check_regime_filter(self, df, idx):
        if idx < 50:
            return None, False
        
        lookback = df.iloc[:idx+1]
        
        adx, atr = self.calculate_adx(lookback['high'], lookback['low'], lookback['close'])
        
        if len(adx) < 25 or len(atr) < 15:
            return None, False
        
        current_adx = adx.iloc[-1]
        ema200 = self.calculate_ema(lookback['close'], 200)
        current_price = lookback['close'].iloc[-1]
        
        atr_zscore = self.calculate_atr_zscore(atr)
        current_zscore = atr_zscore.iloc[-1] if len(atr_zscore) > 0 else 0
        
        high_volatility = current_zscore > 2.0
        
        if current_adx > 25:
            if current_price > ema200.iloc[-1]:
                bias = "BULLISH"
            elif current_price < ema200.iloc[-1]:
                bias = "BEARISH"
            else:
                bias = None
        else:
            bias = None
        
        blocked = high_volatility
        
        return bias, blocked
    
    def check_bos(self, df, idx, direction):
        if idx < 21:
            return False
        
        lookback = df.iloc[idx-20:idx+1]
        
        swing_high = lookback['high'].max()
        swing_low = lookback['low'].min()
        
        current_close = df.iloc[idx]['close']
        
        if direction == "LONG":
            return current_close > swing_high
        elif direction == "SHORT":
            return current_close < swing_low
        
        return False
    
    def calculate_position_size(self, entry, sl, balance):
        atr = abs(entry - sl)
        if atr == 0:
            return 0.35
        
        risk_amount = balance * 0.01
        lot_size = risk_amount / (atr * 100)
        
        return min(max(lot_size, 0.01), 1.0)
    
    def run_backtest(self):
        print("="*80)
        print("MATHEMATICAL RISK ENGINE - Backtest")
        print("="*80)
        print("Filters: ADX>25, EMA200, ATR Z-Score<2.0")
        print("Risk: 1% per trade | TP1:1.5R, TP2:2.5R")
        print("="*80)
        
        symbol = "XAUUSDc"
        start = datetime.now() - timedelta(days=365)
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
        
        daily_trades = {}
        daily_start_equity = self.equity
        
        for i in range(100, len(df) - 24):
            row = df.iloc[i]
            trade_date = row['time'].date()
            
            if row['time'].hour not in trade_hours:
                continue
            
            if self.hard_lock_until and row['time'] < self.hard_lock_until:
                continue
            
            bias, blocked = self.check_regime_filter(df, i)
            
            if bias is None or blocked:
                continue
            
            if bias == "BULLISH":
                direction = "LONG"
            else:
                direction = "SHORT"
            
            if not self.check_bos(df, i, direction):
                continue
            
            entry = row['close']
            pip_size = self.get_pip_size()
            
            atr, _ = self.calculate_adx(df.iloc[:i+1]['high'], df.iloc[:i+1]['low'], df.iloc[:i+1]['close'])
            current_atr = atr.iloc[-1]
            
            sl_distance = current_atr * 1.5
            risk = sl_distance * 100
            
            if direction == "LONG":
                sl = entry - sl_distance
                tp1 = entry + risk * 1.5
                tp2 = entry + risk * 2.5
            else:
                sl = entry + sl_distance
                tp1 = entry - risk * 1.5
                tp2 = entry - risk * 2.5
            
            lot_size = self.calculate_position_size(entry, sl, self.balance)
            
            future = df.iloc[i:i+24]
            
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
                pnl = risk * 2.5 * lot_size
            elif tp1_hit:
                result = "TP1"
                pnl = risk * 1.5 * lot_size
            elif sl_hit:
                result = "SL"
                pnl = -risk * lot_size
            else:
                result = "OPEN"
                final_price = future.iloc[-1]['close']
                if direction == "LONG":
                    pnl = (final_price - entry) / pip_size * 3.5 * lot_size
                else:
                    pnl = (entry - final_price) / pip_size * 3.5 * lot_size
            
            self.trades.append({
                "time": row['time'],
                "date": trade_date,
                "bias": bias,
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "atr": current_atr,
                "risk": risk,
                "lot": lot_size,
                "result": result,
                "pnl": pnl
            })
            
            self.balance += pnl
            self.equity += pnl
            
            if trade_date not in daily_trades:
                daily_trades[trade_date] = []
            daily_trades[trade_date].append(pnl)
            
            if self.balance / daily_start_equity - 1 <= -0.03:
                self.hard_lock_until = row['time'] + timedelta(hours=24)
                print(f"\n!!! CIRCUIT BREAKER ACTIVATED !!!")
                print(f"    Date: {trade_date}")
                print(f"    Balance: ${self.balance:,.2f}")
                print(f"    Lock until: {self.hard_lock_until}")
            
            next_date = df.iloc[i+1]['time'].date() if i+1 < len(df) else None
            if next_date != trade_date:
                daily_pnl = sum(daily_trades[trade_date])
                daily_return = daily_pnl / daily_start_equity
                daily_start_equity = self.balance
                daily_trades = {}
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if 'TP' in t['result']]
        losses = [t for t in self.trades if t['result'] == 'SL']
        open_trades = [t for t in self.trades if t['result'] == 'OPEN']
        
        tp1_wins = [t for t in self.trades if t['result'] == 'TP1']
        tp2_wins = [t for t in self.trades if t['result'] == 'TP2']
        
        print(f"\n{'='*80}")
        print("RESULTS - Mathematical Risk Engine")
        print(f"{'='*80}")
        print(f"Total Trades: {len(self.trades)}")
        print(f"Closed: {len(wins) + len(losses)} | Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"TP1 Hits: {len(tp1_wins)} | TP2 Hits: {len(tp2_wins)}")
        print(f"Open: {len(open_trades)}")
        
        if wins or losses:
            closed = wins + losses
            win_rate = len(wins) / len(closed) * 100 if closed else 0
            print(f"\nWin Rate: {win_rate:.1f}%")
            
            if wins:
                total_wins = sum(t['pnl'] for t in wins)
                avg_win = total_wins / len(wins)
                print(f"Avg Win: ${avg_win:,.2f} | Total: ${total_wins:,.2f}")
            if losses:
                total_losses = abs(sum(t['pnl'] for t in losses))
                avg_loss = total_losses / len(losses)
                print(f"Avg Loss: ${avg_loss:,.2f} | Total: ${total_losses:,.2f}")
            
            total_wins = sum(t['pnl'] for t in wins) if wins else 0
            total_losses = abs(sum(t['pnl'] for t in losses)) if losses else 1
            pf = total_wins / total_losses if total_losses > 0 else 0
            print(f"Profit Factor: {pf:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        if self.hard_lock_until:
            print(f"\nCircuit Breaker was triggered!")
        
        print(f"\n{'='*80}")
        print("TRADE SUMMARY BY RESULT")
        print(f"{'='*80}")
        for result in ['TP2', 'TP1', 'SL', 'OPEN']:
            subset = [t for t in self.trades if t['result'] == result]
            if subset:
                pnl = sum(t['pnl'] for t in subset)
                print(f"{result}: {len(subset)} trades | ${pnl:+,.2f}")
        
        print(f"\n{'='*80}")
        print("ALL TRADES")
        print(f"{'='*80}")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['bias']:8} | {t['direction']:5} | "
                  f"ATR:{t['atr']:.2f} | Risk:${t['risk']:.2f} | Lot:{t['lot']:.3f} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MathematicalRiskEngine()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()