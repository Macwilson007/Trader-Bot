"""
STRATEGY V2: "Session Scalper"

Key changes:
1. Shorter TP (40 pips = 1:1 R:R with 40 pip SL)
2. Trade only XAUUSD and EURUSD
3. Only trade at session OPEN (first candle)
4. 6-hour holding period max
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


class SessionScalper:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.sl_pips = 40
        self.tp_pips = 40
        
    def get_pip_value(self, symbol):
        return 3.5
    
    def get_pip_size(self, symbol):
        return 0.01
    
    def get_daily_trend(self, d1_df, current_time):
        d1_before = d1_df[d1_df['time'] <= current_time].tail(20)
        if len(d1_before) < 10:
            return None
        return "BULLISH" if d1_before['close'].iloc[-1] > d1_before['close'].iloc[0] else "BEARISH"
    
    def get_h4_momentum(self, h4_df, current_time):
        h4_before = h4_df[h4_df['time'] <= current_time].tail(5)
        if len(h4_before) < 3:
            return None
        return "BULLISH" if h4_before['close'].iloc[-1] > h4_before['close'].iloc[0] else "BEARISH"
    
    def get_entry_signal(self, h1_df, idx, direction):
        if idx < 5:
            return False
        
        lookback = h1_df.iloc[idx-4:idx+1]
        closes = lookback['close'].values
        opens = lookback['open'].values
        
        if direction == "BUY":
            return closes[-1] > closes[0]
        else:
            return closes[-1] < closes[0]
    
    def run_backtest(self):
        print("="*70)
        print("SESSION SCALPER V2 - Tight SL/TP (1:1)")
        print("="*70)
        
        symbols = ["XAUUSDc"]
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        
        all_data = {}
        
        for symbol in symbols:
            print(f"\nLoading {symbol}...")
            d1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start - timedelta(days=60), end)
            h4_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, start - timedelta(days=14), end)
            h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, end)
            
            if d1_rates is not None and h4_rates is not None and h1_rates is not None:
                all_data[symbol] = {
                    "D1": pd.DataFrame(d1_rates),
                    "H4": pd.DataFrame(h4_rates),
                    "H1": pd.DataFrame(h1_rates)
                }
                for key in all_data[symbol]:
                    all_data[symbol][key]['time'] = pd.to_datetime(
                        all_data[symbol][key]['time'], unit='s'
                    )
                print(f"  Loaded successfully")
        
        if not all_data:
            print("No data loaded!")
            return
        
        sessions = [(8, 0), (13, 0)]
        
        for symbol, data in all_data.items():
            d1_df = data["D1"]
            h4_df = data["H4"]
            h1_df = data["H1"]
            
            print(f"\nBacktesting {symbol}...")
            
            for i in range(50, len(h1_df) - 4):
                row = h1_df.iloc[i]
                session_time = row['time']
                
                is_session = any(
                    session_time.hour == h and session_time.minute == m 
                    for h, m in sessions
                )
                
                if not is_session:
                    continue
                
                d1_trend = self.get_daily_trend(d1_df, session_time)
                h4_momentum = self.get_h4_momentum(h4_df, session_time)
                
                if d1_trend is None or h4_momentum is None:
                    continue
                
                if d1_trend == h4_momentum:
                    direction = d1_trend
                    
                    if self.get_entry_signal(h1_df, i, direction):
                        entry = h1_df.iloc[i]['close']
                        pip_val = self.get_pip_value(symbol)
                        pip_size = self.get_pip_size(symbol)
                        
                        if direction == "BUY":
                            sl = entry - self.sl_pips * pip_size
                            tp = entry + self.tp_pips * pip_size
                        else:
                            sl = entry + self.sl_pips * pip_size
                            tp = entry - self.tp_pips * pip_size
                        
                        future = h1_df.iloc[i:i+4]
                        result = "OPEN"
                        exit_price = future.iloc[-1]['close']
                        
                        for f in future.itertuples():
                            if direction == "BUY":
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
                        
                        pnl = (exit_price - entry) / pip_size * pip_val if direction == "BUY" else (entry - exit_price) / pip_size * pip_val
                        
                        self.trades.append({
                            "symbol": symbol,
                            "direction": direction,
                            "time": session_time,
                            "d1": d1_trend,
                            "h4": h4_momentum,
                            "result": result,
                            "pnl": pnl
                        })
                        self.balance += pnl
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if t['result'] == 'TP']
        losses = [t for t in self.trades if t['result'] == 'SL']
        
        print(f"\n{'='*70}")
        print("RESULTS - Session Scalper V2")
        print(f"{'='*70}")
        print(f"Total Trades: {len(self.trades)}")
        print(f"Wins: {len(wins)} | Losses: {len(losses)}")
        
        if wins or losses:
            closed = len(wins) + len(losses)
            wr = len(wins) / closed * 100 if closed > 0 else 0
            print(f"Win Rate: {wr:.1f}%")
            
            if wins:
                print(f"Total Wins: ${sum(t['pnl'] for t in wins):,.2f}")
            if losses:
                print(f"Total Losses: ${sum(t['pnl'] for t in losses):,.2f}")
            
            pf = sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses)) if losses else 0
            print(f"Profit Factor: {pf:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        print(f"\nAll Trades:")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['direction']:7} | D1:{t['d1']:8} H4:{t['h4']:8} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = SessionScalper()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()