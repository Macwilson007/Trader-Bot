"""
MTF SESSION MASTER v4 - Extended Holding Period

Key changes:
- Hold trades until H4 candle closes in opposite direction OR TP/SL hit
- This gives trades room to breathe
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


class MTFSessionV4:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.sl_pips = 80
        self.tp_pips = 160
        
    def get_pip_value(self):
        return 3.5
    
    def get_pip_size(self):
        return 0.01
    
    def calculate_pivots(self, high, low, close):
        pp = (high + low + close) / 3
        r1 = 2 * pp - low
        s1 = 2 * pp - high
        return {"pp": pp, "r1": r1, "s1": s1}
    
    def get_daily_bias_and_pivots(self, d1_df, current_time):
        d1_before = d1_df[d1_df['time'] < current_time]
        if len(d1_before) < 2:
            return None, None
        
        prev_day = d1_before.iloc[-1]
        bias = "BULLISH" if prev_day['close'] > prev_day['open'] else "BEARISH"
        pivots = self.calculate_pivots(prev_day['high'], prev_day['low'], prev_day['close'])
        
        return bias, pivots
    
    def get_h4_structure(self, h4_df, current_time, daily_bias, pivots):
        h4_before = h4_df[h4_df['time'] <= current_time]
        if len(h4_before) < 5:
            return None, None, None
        
        last_4_h4 = h4_before.tail(4)
        current_h4 = last_4_h4.iloc[-1]
        prev_3_h4 = last_4_h4.iloc[-4:-1]
        
        swing_high = prev_3_h4['high'].max()
        swing_low = prev_3_h4['low'].min()
        
        h4_close = current_h4['close']
        h4_open = current_h4['open']
        
        is_bullish = h4_close > h4_open
        is_bearish = h4_close < h4_open
        
        valid = False
        invalidation = False
        direction = None
        
        if daily_bias == "BEARISH":
            if is_bullish and h4_close < swing_high:
                valid = True
                direction = "SHORT"
                if h4_close > pivots["r1"]:
                    invalidation = True
                    
        elif daily_bias == "BULLISH":
            if is_bearish and h4_close > swing_low:
                valid = True
                direction = "LONG"
                if h4_close < pivots["s1"]:
                    invalidation = True
        
        return valid, invalidation, direction, swing_high, swing_low
    
    def get_m15_entry(self, m15_df, idx, direction):
        if idx < 2:
            return False, 0
        
        lookback = m15_df.iloc[idx-1:idx+1]
        if len(lookback) < 2:
            return False, 0
        
        c1 = lookback.iloc[-2]
        c2 = lookback.iloc[-1]
        
        bullish_engulf = (c1['close'] < c1['open'] and c2['close'] > c2['open'] and 
                         c2['close'] > c1['open'] and c2['open'] < c1['close'])
        
        bearish_engulf = (c1['close'] > c1['open'] and c2['close'] < c2['open'] and 
                         c2['close'] < c1['open'] and c2['open'] > c1['close'])
        
        entry = m15_df.iloc[idx]['close']
        
        if direction == "LONG" and (bullish_engulf or c2['close'] > c2['open']):
            return True, entry
        elif direction == "SHORT" and (bearish_engulf or c2['close'] < c2['open']):
            return True, entry
        
        return False, 0
    
    def run_backtest(self):
        print("="*80)
        print("MTF SESSION MASTER v4 - Extended Holding (Until H4 Close)")
        print(f"SL: {self.sl_pips}p | TP: {self.tp_pips}p (1:2)")
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
        
        for i in range(5, len(h4_df) - 10):
            h4_row = h4_df.iloc[i]
            h4_time = h4_row['time']
            
            if h4_time.hour not in trade_hours:
                continue
            
            daily_bias, pivots = self.get_daily_bias_and_pivots(d1_df, h4_time)
            if daily_bias is None:
                continue
            
            valid, invalidation, direction, swing_high, swing_low = self.get_h4_structure(
                h4_df, h4_time, daily_bias, pivots
            )
            
            if not valid or invalidation:
                continue
            
            m15_before = m15_df[m15_df['time'] <= h4_time]
            if len(m15_before) < 2:
                continue
            
            m15_idx = len(m15_before) - 1
            
            confirmed, entry_price = self.get_m15_entry(m15_df, m15_idx, direction)
            
            if not confirmed:
                continue
            
            pip_size = self.get_pip_size()
            
            if direction == "LONG":
                sl = entry_price - self.sl_pips * pip_size
                tp = entry_price + self.tp_pips * pip_size
            else:
                sl = entry_price + self.sl_pips * pip_size
                tp = entry_price - self.tp_pips * pip_size
            
            m15_after = m15_df[m15_df['time'] > h4_time].iloc[:96]
            
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
            
            pip_val = self.get_pip_value()
            pnl = (exit_price - entry_price) / pip_size * pip_val if direction == "LONG" else (entry_price - exit_price) / pip_size * pip_val
            
            self.trades.append({
                "time": h4_time,
                "bias": daily_bias,
                "direction": direction,
                "entry": entry_price,
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
        print("RESULTS - MTF Session Master v4")
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
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        print(f"\n{'='*80}")
        print("ALL TRADES")
        print(f"{'='*80}")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['bias']:8} | {t['direction']:5} | "
                  f"E:{t['entry']:.2f} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MTFSessionV4()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()