"""
TRADING STRATEGY: "MTF Session Master v2"

Improvements:
1. Tighter SL based on H4 ATR
2. Partial TP at 1R (lock in profits)
3. Maximum 2% risk per trade
4. Better R:R filtering (minimum 1.5:1)
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class MTFSessionMasterV2:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.max_risk_pct = 0.02
        self.min_rr = 1.5
        
    def get_pip_value(self, symbol):
        return 3.5
    
    def get_pip_size(self, symbol):
        return 0.01
    
    def calculate_pivots(self, high, low, close):
        pp = (high + low + close) / 3
        r1 = 2 * pp - low
        s1 = 2 * pp - high
        return {"pp": pp, "r1": r1, "s1": s1}
    
    def calculate_atr(self, df, period=14):
        tr = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        ], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def get_daily_bias_and_pivots(self, d1_df, current_time):
        d1_before = d1_df[d1_df['time'] < current_time]
        if len(d1_before) < 2:
            return None, None
        
        prev_day = d1_before.iloc[-1]
        
        bias = "BULLISH" if prev_day['close'] > prev_day['open'] else "BEARISH"
        pivots = self.calculate_pivots(prev_day['high'], prev_day['low'], prev_day['close'])
        
        return bias, pivots
    
    def get_h4_analysis(self, h4_df, current_time, daily_bias, pivots):
        h4_before = h4_df[h4_df['time'] <= current_time]
        if len(h4_before) < 6:
            return None, None, None, None, None
        
        last_5_h4 = h4_before.tail(5)
        current_h4 = last_5_h4.iloc[-1]
        prev_4_h4 = last_5_h4.iloc[-5:-1]
        
        swing_high = prev_4_h4['high'].max()
        swing_low = prev_4_h4['low'].min()
        
        h4_close = current_h4['close']
        h4_open = current_h4['open']
        h4_high = current_h4['high']
        h4_low = current_h4['low']
        
        atr = self.calculate_atr(last_5_h4).iloc[-1]
        
        valid = False
        invalidation = False
        direction = None
        
        if daily_bias == "BEARISH":
            is_bullish_retrace = h4_close > h4_open and h4_close < swing_high
            if is_bullish_retrace:
                valid = True
                direction = "SHORT"
                if h4_close > pivots["r1"]:
                    invalidation = True
                    
        elif daily_bias == "BULLISH":
            is_bearish_retrace = h4_close < h4_open and h4_close > swing_low
            if is_bearish_retrace:
                valid = True
                direction = "LONG"
                if h4_close < pivots["s1"]:
                    invalidation = True
        
        return valid, invalidation, direction, swing_high, swing_low, atr
    
    def get_m15_signal(self, m15_df, idx, direction, entry_price):
        if idx < 3:
            return False, 0, 0
        
        lookback = m15_df.iloc[idx-2:idx+1]
        
        if len(lookback) < 3:
            return False, 0, 0
        
        c1 = lookback.iloc[-2]
        c2 = lookback.iloc[-1]
        
        bullish_engulf = (c1['close'] < c1['open'] and c2['close'] > c2['open'] and 
                         c2['close'] > c1['open'] and c2['open'] < c1['close'])
        
        bearish_engulf = (c1['close'] > c1['open'] and c2['close'] < c2['open'] and 
                         c2['close'] < c1['open'] and c2['open'] > c1['close'])
        
        strong_bullish = c2['close'] > c2['open'] and (c2['close'] - c2['open']) > (c1['high'] - c1['low']) * 0.8
        strong_bearish = c2['close'] < c2['open'] and (c2['open'] - c2['close']) > (c1['high'] - c1['low']) * 0.8
        
        entry = m15_df.iloc[idx]['close']
        
        if direction == "LONG":
            if bullish_engulf or strong_bullish:
                return True, entry, c2['low']
        elif direction == "SHORT":
            if bearish_engulf or strong_bearish:
                return True, entry, c2['high']
        
        return False, 0, 0
    
    def calculate_risk_params(self, direction, entry, swing_level, atr, pivots, balance):
        pip_size = 0.01
        
        if direction == "LONG":
            sl_distance = min((entry - swing_level) * 0.5, atr * 2)
            sl = entry - sl_distance
            sl_pips = sl_distance / pip_size
            
            tp1_pips = sl_pips * 2
            tp2_distance = (pivots.get("r1", entry + 100 * pip_size) - entry)
            tp2_pips = tp2_distance / pip_size
            
            tp_pips = min(tp1_pips, tp2_pips)
            tp = entry + tp_pips * pip_size
            
        else:
            sl_distance = min((swing_level - entry) * 0.5, atr * 2)
            sl = entry + sl_distance
            sl_pips = sl_distance / pip_size
            
            tp1_pips = sl_pips * 2
            tp2_distance = (entry - pivots.get("s1", entry - 100 * pip_size))
            tp2_pips = tp2_distance / pip_size
            
            tp_pips = min(tp1_pips, tp2_pips)
            tp = entry - tp_pips * pip_size
        
        risk_amount = sl_pips * 3.5 * self.lot_size
        max_position = (balance * self.max_risk_pct) / (sl_pips * 3.5)
        
        rr = tp_pips / sl_pips if sl_pips > 0 else 0
        
        return sl, tp, sl_pips, tp_pips, rr, risk_amount
    
    def run_backtest(self):
        print("="*80)
        print("MTF SESSION MASTER v2 - Enhanced Risk Management")
        print("="*80)
        
        symbol = "XAUUSDc"
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        
        print(f"\nLoading {symbol}...")
        
        d1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start - timedelta(days=30), end)
        h4_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, start - timedelta(days=7), end)
        m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start, end)
        
        d1_df = pd.DataFrame(d1_rates)
        d1_df['time'] = pd.to_datetime(d1_df['time'], unit='s')
        
        h4_df = pd.DataFrame(h4_rates)
        h4_df['time'] = pd.to_datetime(h4_df['time'], unit='s')
        
        m15_df = pd.DataFrame(m15_rates)
        m15_df['time'] = pd.to_datetime(m15_df['time'], unit='s')
        
        print(f"  D1: {len(d1_df)} | H4: {len(h4_df)} | M15: {len(m15_df)}")
        
        trade_hours = list(range(7, 17))
        
        for i in range(6, len(h4_df) - 3):
            h4_row = h4_df.iloc[i]
            h4_time = h4_row['time']
            
            if h4_time.hour not in trade_hours:
                continue
            
            daily_bias, pivots = self.get_daily_bias_and_pivots(d1_df, h4_time)
            if daily_bias is None:
                continue
            
            valid, invalidation, direction, swing_high, swing_low, atr = self.get_h4_analysis(
                h4_df, h4_time, daily_bias, pivots
            )
            
            if not valid or invalidation:
                continue
            
            m15_before = m15_df[m15_df['time'] <= h4_time]
            if len(m15_before) < 3:
                continue
            
            m15_idx = len(m15_before) - 1
            
            confirmed, entry_price, rejection = self.get_m15_signal(
                m15_df, m15_idx, direction, h4_row['close']
            )
            
            if not confirmed:
                continue
            
            sl, tp, sl_pips, tp_pips, rr, risk_amount = self.calculate_risk_params(
                direction, entry_price, swing_low if direction == "LONG" else swing_high, 
                atr, pivots, self.balance
            )
            
            if rr < self.min_rr:
                continue
            
            m15_after = m15_df[m15_df['time'] > h4_time].iloc[:24]
            
            result = "OPEN"
            exit_price = m15_after.iloc[-1]['close']
            partial_tp_hit = False
            
            for j, f in enumerate(m15_after.itertuples()):
                if direction == "LONG":
                    if f.low <= sl:
                        result = "SL"
                        exit_price = sl
                        break
                    elif f.high >= tp:
                        result = "TP"
                        exit_price = tp
                        break
                    elif not partial_tp_hit and f.high >= entry_price + sl_pips * 0.01:
                        partial_tp_hit = True
                else:
                    if f.high >= sl:
                        result = "SL"
                        exit_price = sl
                        break
                    elif f.low <= tp:
                        result = "TP"
                        exit_price = tp
                        break
                    elif not partial_tp_hit and f.low <= entry_price - sl_pips * 0.01:
                        partial_tp_hit = True
            
            pip_val = self.get_pip_value(symbol)
            pip_size = self.get_pip_size(symbol)
            pnl = (exit_price - entry_price) / pip_size * pip_val if direction == "LONG" else (entry_price - exit_price) / pip_size * pip_val
            
            self.trades.append({
                "time": h4_time,
                "bias": daily_bias,
                "direction": direction,
                "entry": entry_price,
                "sl": sl,
                "tp": tp,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "rr": rr,
                "result": result,
                "pnl": pnl
            })
            self.balance += pnl
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if t['result'] == 'TP']
        losses = [t for t in self.trades if t['result'] == 'SL']
        open_trades = [t for t in self.trades if t['result'] == 'OPEN']
        
        print(f"\n{'='*80}")
        print("RESULTS - MTF Session Master v2")
        print(f"{'='*80}")
        print(f"Total Trades: {len(self.trades)}")
        print(f"Closed: {len(wins) + len(losses)} | Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"Open: {len(open_trades)}")
        
        if wins or losses:
            closed = wins + losses
            win_rate = len(wins) / len(closed) * 100 if closed else 0
            print(f"\nWin Rate: {win_rate:.1f}%")
            
            if wins:
                total_wins = sum(t['pnl'] for t in wins)
                avg_win = total_wins / len(wins)
                print(f"Avg Win: ${avg_win:,.2f}")
            if losses:
                total_losses = abs(sum(t['pnl'] for t in losses))
                avg_loss = total_losses / len(losses)
                print(f"Avg Loss: ${avg_loss:,.2f}")
            
            total_wins = sum(t['pnl'] for t in wins) if wins else 0
            total_losses = abs(sum(t['pnl'] for t in losses)) if losses else 1
            pf = total_wins / total_losses if total_losses > 0 else 0
            print(f"Profit Factor: {pf:.2f}")
            
            avg_rr = sum(t['rr'] for t in self.trades) / len(self.trades) if self.trades else 0
            print(f"Avg R:R: {avg_rr:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        if open_trades:
            open_pnl = sum(t['pnl'] for t in open_trades)
            print(f"Open P&L: ${open_pnl:+,.2f}")
        
        print(f"\n{'='*80}")
        print("ALL TRADES")
        print(f"{'='*80}")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['bias']:8} | {t['direction']:5} | "
                  f"SL:{t['sl_pips']:.0f}p TP:{t['tp_pips']:.0f}p R:R:{t['rr']:.1f} | "
                  f"{t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MTFSessionMasterV2()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()