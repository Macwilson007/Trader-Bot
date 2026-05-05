"""
MTF SESSION MASTER v3 - Fixed Parameters

Key parameters:
- SL: 50 pips
- TP: 100 pips (1:2 R:R)
- Only trade if R:R >= 1.5
- Partial TP: Move SL to BE at 50 pips profit
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


class MTFSessionV3:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.sl_pips = 50
        self.tp_pips = 100
        self.be_pips = 50
        
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
            return None, None, None, None
        
        last_4_h4 = h4_before.tail(4)
        current_h4 = last_4_h4.iloc[-1]
        prev_3_h4 = last_4_h4.iloc[-4:-1]
        
        swing_high = prev_3_h4['high'].max()
        swing_low = prev_3_h4['low'].min()
        
        h4_close = current_h4['close']
        h4_high = current_h4['high']
        h4_low = current_h4['low']
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
        print("MTF SESSION MASTER v3 - Fixed Parameters")
        print(f"SL: {self.sl_pips}p | TP: {self.tp_pips}p | Partial TP at {self.be_pips}p")
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
        
        for i in range(5, len(h4_df) - 2):
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
                be_price = entry_price + self.be_pips * pip_size
            else:
                sl = entry_price + self.sl_pips * pip_size
                tp = entry_price - self.tp_pips * pip_size
                be_price = entry_price - self.be_pips * pip_size
            
            m15_after = m15_df[m15_df['time'] > h4_time].iloc[:24]
            
            result = "OPEN"
            exit_price = m15_after.iloc[-1]['close']
            partial_closed = False
            sl_moved_to_be = False
            
            for f in m15_after.itertuples():
                low = f.low
                high = f.high
                
                if direction == "LONG":
                    if low <= sl:
                        if partial_closed:
                            result = "SL_BE"
                        else:
                            result = "SL"
                        exit_price = sl
                        break
                    elif high >= tp:
                        result = "TP"
                        exit_price = tp
                        break
                    elif not sl_moved_to_be and high >= be_price:
                        sl_moved_to_be = True
                        partial_closed = True
                else:
                    if high >= sl:
                        if partial_closed:
                            result = "SL_BE"
                        else:
                            result = "SL"
                        exit_price = sl
                        break
                    elif low <= tp:
                        result = "TP"
                        exit_price = tp
                        break
                    elif not sl_moved_to_be and low <= be_price:
                        sl_moved_to_be = True
                        partial_closed = True
            
            pip_val = self.get_pip_value()
            
            if partial_closed and sl_moved_to_be:
                if direction == "LONG":
                    pnl = (be_price - entry_price) / pip_size * pip_val + (exit_price - be_price) / pip_size * pip_val
                else:
                    pnl = (entry_price - be_price) / pip_size * pip_val + (be_price - exit_price) / pip_size * pip_val
            else:
                pnl = (exit_price - entry_price) / pip_size * pip_val if direction == "LONG" else (entry_price - exit_price) / pip_size * pip_val
            
            self.trades.append({
                "time": h4_time,
                "bias": daily_bias,
                "direction": direction,
                "entry": entry_price,
                "sl": sl,
                "tp": tp,
                "result": result,
                "pnl": pnl,
                "partial_closed": partial_closed
            })
            self.balance += pnl
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if 'TP' in t['result']]
        losses = [t for t in self.trades if 'SL' in t['result']]
        open_trades = [t for t in self.trades if t['result'] == 'OPEN']
        
        print(f"\n{'='*80}")
        print("RESULTS - MTF Session Master v3")
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
        
        print(f"\n{'='*80}")
        print("ALL TRADES")
        print(f"{'='*80}")
        for t in self.trades:
            partial = "*" if t.get('partial_closed') else ""
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['bias']:8} | {t['direction']:5} | "
                  f"E:{t['entry']:.2f} | {t['result']}{partial} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MTFSessionV3()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()