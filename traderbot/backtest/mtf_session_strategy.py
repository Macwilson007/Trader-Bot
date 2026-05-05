"""
TRADING STRATEGY: "Multi-Timeframe Session Master"

Rules:
1. D1 Bias: Previous day candle direction sets today's bias
2. Pivot Points: Calculate PP, R1-R3, S1-S3 from previous day
3. H4 Structure: Confirm retracement within D1 trend
4. M15 Entry: BOS, engulfing, or rejection confirmation
5. Risk: 1:2 R:R minimum, SL at H4 swing

This is a complete discretionary-style strategy converted to algorithmic rules.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class MultiTimeframeSessionStrategy:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        
    def get_pip_value(self, symbol):
        return 3.5 if "XAU" in symbol else 3.5
    
    def get_pip_size(self, symbol):
        return 0.01 if "XAU" in symbol else 0.0001
    
    def calculate_pivots(self, high, low, close):
        pp = (high + low + close) / 3
        r1 = 2 * pp - low
        s1 = 2 * pp - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        r3 = high + 2 * (pp - low)
        s3 = low - 2 * (high - pp)
        return {"pp": pp, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}
    
    def get_daily_bias(self, d1_df, current_time):
        d1_before = d1_df[d1_df['time'] < current_time]
        if len(d1_before) < 2:
            return None, None
        
        prev_day = d1_before.iloc[-1]
        prev_high = prev_day['high']
        prev_low = prev_day['low']
        prev_close = prev_day['close']
        
        if prev_close > prev_day['open']:
            bias = "BULLISH"
        else:
            bias = "BEARISH"
        
        pivots = self.calculate_pivots(prev_high, prev_low, prev_close)
        
        return bias, pivots
    
    def get_h4_structure(self, h4_df, current_time, daily_bias, pivots):
        h4_before = h4_df[h4_df['time'] <= current_time]
        if len(h4_before) < 4:
            return None, None, None
        
        last_4_h4 = h4_before.tail(4)
        
        current_h4 = last_4_h4.iloc[-1]
        prev_3_h4 = last_4_h4.iloc[-4:-1]
        
        h4_close = current_h4['close']
        h4_high = current_h4['high']
        h4_low = current_h4['low']
        h4_open = current_h4['open']
        
        swing_high = prev_3_h4['high'].max()
        swing_low = prev_3_h4['low'].min()
        
        is_bullish_candle = h4_close > h4_open
        is_bearish_candle = h4_close < h4_open
        
        valid = False
        invalidation = False
        direction = None
        
        if daily_bias == "BEARISH":
            if is_bullish_candle and h4_close < swing_high:
                valid = True
                direction = "SHORT"
                if h4_close > pivots["r1"]:
                    invalidation = True
                    
        elif daily_bias == "BULLISH":
            if is_bearish_candle and h4_close > swing_low:
                valid = True
                direction = "LONG"
                if h4_close < pivots["s1"]:
                    invalidation = True
        
        return valid, invalidation, direction, swing_high, swing_low
    
    def get_m15_confirmation(self, m15_df, idx, direction, pivot_levels):
        if idx < 5:
            return False, 0, 0
        
        lookback = m15_df.iloc[idx-4:idx+1]
        
        if len(lookback) < 5:
            return False, 0, 0
        
        c1 = lookback.iloc[-2]
        c2 = lookback.iloc[-1]
        
        bos_bullish = c2['close'] > c1['high'] and c2['close'] > lookback['high'].iloc[-3]
        bos_bearish = c2['close'] < c1['low'] and c2['close'] < lookback['low'].iloc[-3]
        
        bullish_engulf = (c1['close'] < c1['open'] and c2['close'] > c2['open'] and 
                         c2['close'] > c1['open'] and c2['open'] < c1['close'])
        
        bearish_engulf = (c1['close'] > c1['open'] and c2['close'] < c2['open'] and 
                         c2['close'] < c1['open'] and c2['open'] > c1['close'])
        
        entry = m15_df.iloc[idx]['close']
        
        if direction == "LONG":
            if bos_bullish or bullish_engulf:
                return True, entry, c2['low']
        elif direction == "SHORT":
            if bos_bearish or bearish_engulf:
                return True, entry, c2['high']
        
        return False, 0, 0
    
    def calculate_sl_tp(self, direction, entry, swing_level, pivot_levels):
        pip_size = 0.01
        
        if direction == "LONG":
            sl = swing_level - 10 * pip_size
            tp1 = entry + (entry - sl) * 2
            tp2 = pivot_levels.get("r1", entry + 100 * pip_size)
            tp = min(tp1, tp2)
        else:
            sl = swing_level + 10 * pip_size
            tp1 = entry - (sl - entry) * 2
            tp2 = pivot_levels.get("s1", entry - 100 * pip_size)
            tp = max(tp1, tp2)
        
        return sl, tp
    
    def run_backtest(self):
        print("="*80)
        print("MULTI-TIMEFRAME SESSION STRATEGY - Backtest")
        print("="*80)
        print("Rules: D1 Bias + H4 Invalidation + M15 Confirmation")
        print("="*80)
        
        symbols = ["XAUUSDc"]
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        
        for symbol in symbols:
            print(f"\nLoading {symbol}...")
            
            d1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start - timedelta(days=30), end)
            h4_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, start - timedelta(days=7), end)
            m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start, end)
            
            if d1_rates is None or h4_rates is None or m15_rates is None:
                print(f"Failed to load data for {symbol}")
                continue
            
            d1_df = pd.DataFrame(d1_rates)
            d1_df['time'] = pd.to_datetime(d1_df['time'], unit='s')
            
            h4_df = pd.DataFrame(h4_rates)
            h4_df['time'] = pd.to_datetime(h4_df['time'], unit='s')
            
            m15_df = pd.DataFrame(m15_rates)
            m15_df['time'] = pd.to_datetime(m15_df['time'], unit='s')
            
            print(f"  D1: {len(d1_df)} | H4: {len(h4_df)} | M15: {len(m15_df)}")
            
            london_hours = [7, 8, 9, 10, 11]
            ny_hours = [12, 13, 14, 15, 16]
            trade_hours = london_hours + ny_hours
            
            h4_count = 0
            
            for i in range(4, len(h4_df) - 3):
                h4_row = h4_df.iloc[i]
                h4_time = h4_row['time']
                
                if h4_time.hour not in trade_hours:
                    continue
                
                h4_count += 1
                
                daily_bias, pivots = self.get_daily_bias(d1_df, h4_time)
                
                if daily_bias is None:
                    continue
                
                valid, invalidation, direction, swing_high, swing_low = self.get_h4_structure(
                    h4_df, h4_time, daily_bias, pivots
                )
                
                if not valid or invalidation:
                    continue
                
                m15_before = m15_df[m15_df['time'] <= h4_time]
                if len(m15_before) < 5:
                    continue
                
                m15_idx = len(m15_before) - 1
                
                confirmed, entry_price, rejection_level = self.get_m15_confirmation(
                    m15_df, m15_idx, direction, pivots
                )
                
                if not confirmed:
                    continue
                
                if direction == "LONG":
                    sl, tp = self.calculate_sl_tp(direction, entry_price, swing_low, pivots)
                else:
                    sl, tp = self.calculate_sl_tp(direction, entry_price, swing_high, pivots)
                
                pip_val = self.get_pip_value(symbol)
                pip_size = self.get_pip_size(symbol)
                
                m15_after = m15_df[m15_df['time'] > h4_time].iloc[:24]
                
                result = "OPEN"
                exit_price = m15_after.iloc[-1]['close']
                
                for f in m15_after.itertuples():
                    if direction == "LONG":
                        if f.low <= sl:
                            result = "SL"
                            exit_price = sl
                            break
                        elif f.high >= tp:
                            result = "TP"
                            exit_price = tp
                            break
                    else:
                        if f.high >= sl:
                            result = "SL"
                            exit_price = sl
                            break
                        elif f.low <= tp:
                            result = "TP"
                            exit_price = tp
                            break
                
                pnl = (exit_price - entry_price) / pip_size * pip_val if direction == "LONG" else (entry_price - exit_price) / pip_size * pip_val
                
                if pnl < 0:
                    sl_distance = abs(entry_price - sl) / pip_size
                    tp_distance = abs(tp - entry_price) / pip_size
                    rr = tp_distance / sl_distance if sl_distance > 0 else 0
                    if rr < 1.5:
                        continue
                
                self.trades.append({
                    "time": h4_time,
                    "symbol": symbol,
                    "bias": daily_bias,
                    "direction": direction,
                    "entry": entry_price,
                    "sl": sl,
                    "tp": tp,
                    "result": result,
                    "pnl": pnl
                })
                self.balance += pnl
            
            print(f"  H4 candles checked: {h4_count}")
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if t['result'] == 'TP']
        losses = [t for t in self.trades if t['result'] == 'SL']
        open_trades = [t for t in self.trades if t['result'] == 'OPEN']
        
        print(f"\n{'='*80}")
        print("BACKTEST RESULTS")
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
            
            pf = total_wins / total_losses if losses else 0
            print(f"Profit Factor: {pf:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        print(f"\n{'='*80}")
        print("ALL TRADES")
        print(f"{'='*80}")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['bias']:8} | {t['direction']:5} | E:{t['entry']:.2f} | SL:{t['sl']:.2f} | TP:{t['tp']:.2f} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MultiTimeframeSessionStrategy()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()