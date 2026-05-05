"""
STRATEGY V3: "Counter-Trend Session Trader"

Key insight: When everyone is trading with the trend, the market often reverses.
This strategy trades AGAINST the short-term momentum at session opens,
with strong D1 trend confirmation.

Rules:
1. D1 trend must be aligned (EMA crossover)
2. Price at session open is far from recent highs/lows (potential reversal)
3. RSI on H1 is in overbought (>70) or oversold (<30)
4. Trade the reversal with tight stop
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class CounterTrendStrategy:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.sl_pips = 30
        self.tp_pips = 60
        
    def get_pip_value(self, symbol):
        return 3.5
    
    def get_pip_size(self, symbol):
        return 0.01
    
    def get_d1_trend(self, d1_df, current_time):
        d1_before = d1_df[d1_df['time'] <= current_time].tail(50)
        if len(d1_before) < 30:
            return None
        ema50 = d1_before['close'].ewm(span=50).mean()
        ema200 = d1_before['close'].ewm(span=200).mean()
        if ema50.iloc[-1] > ema200.iloc[-1]:
            return "BULLISH"
        elif ema50.iloc[-1] < ema200.iloc[-1]:
            return "BEARISH"
        return None
    
    def get_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def get_session_signal(self, h1_df, idx, d1_trend):
        if idx < 50:
            return "HOLD"
        
        lookback = h1_df.iloc[:idx+1].tail(50)
        rsi = self.get_rsi(lookback)
        
        if len(rsi) < 14:
            return "HOLD"
        
        last_rsi = rsi.iloc[-1]
        
        recent_high = lookback['high'].tail(20).max()
        recent_low = lookback['low'].tail(20).min()
        current_price = lookback['close'].iloc[-1]
        
        range_pos = (current_price - recent_low) / (recent_high - recent_low) if recent_high != recent_low else 0.5
        
        if d1_trend == "BULLISH" and last_rsi > 70 and range_pos > 0.8:
            return "SELL"
        elif d1_trend == "BEARISH" and last_rsi < 30 and range_pos < 0.2:
            return "BUY"
        
        return "HOLD"
    
    def run_backtest(self):
        print("="*70)
        print("COUNTER-TREND SESSION STRATEGY V3")
        print("Logic: Trade reversals when D1 trend is strong but RSI is extreme")
        print("="*70)
        
        symbols = ["XAUUSDc", "EURUSDc"]
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        
        all_data = {}
        
        for symbol in symbols:
            print(f"\nLoading {symbol}...")
            d1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start - timedelta(days=300), end)
            h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, end)
            
            if d1_rates is not None and h1_rates is not None:
                all_data[symbol] = {
                    "D1": pd.DataFrame(d1_rates),
                    "H1": pd.DataFrame(h1_rates)
                }
                for key in all_data[symbol]:
                    all_data[symbol][key]['time'] = pd.to_datetime(
                        all_data[symbol][key]['time'], unit='s'
                    )
                print(f"  D1: {len(all_data[symbol]['D1'])}, H1: {len(all_data[symbol]['H1'])}")
        
        if not all_data:
            print("No data!")
            return
        
        sessions = [(8, 0), (10, 0), (13, 0), (15, 0), (17, 0)]
        
        for symbol, data in all_data.items():
            d1_df = data["D1"]
            h1_df = data["H1"]
            
            print(f"\nBacktesting {symbol}...")
            
            for i in range(100, len(h1_df) - 6):
                row = h1_df.iloc[i]
                session_time = row['time']
                
                is_session = any(
                    session_time.hour == h and session_time.minute == m 
                    for h, m in sessions
                )
                
                if not is_session:
                    continue
                
                d1_trend = self.get_d1_trend(d1_df, session_time)
                signal = self.get_session_signal(h1_df, i, d1_trend)
                
                if signal in ["BUY", "SELL"]:
                    entry = h1_df.iloc[i]['close']
                    pip_val = self.get_pip_value(symbol)
                    pip_size = self.get_pip_size(symbol)
                    
                    if signal == "BUY":
                        sl = entry - self.sl_pips * pip_size
                        tp = entry + self.tp_pips * pip_size
                    else:
                        sl = entry + self.sl_pips * pip_size
                        tp = entry - self.tp_pips * pip_size
                    
                    future = h1_df.iloc[i:i+6]
                    result = "OPEN"
                    exit_price = future.iloc[-1]['close']
                    
                    for f in future.itertuples():
                        if signal == "BUY":
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
                    
                    pnl = (exit_price - entry) / pip_size * pip_val if signal == "BUY" else (entry - exit_price) / pip_size * pip_val
                    
                    self.trades.append({
                        "symbol": symbol,
                        "signal": signal,
                        "time": session_time,
                        "d1": d1_trend,
                        "result": result,
                        "pnl": pnl
                    })
                    self.balance += pnl
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if t['result'] == 'TP']
        losses = [t for t in self.trades if t['result'] == 'SL']
        
        print(f"\n{'='*70}")
        print("RESULTS - Counter-Trend Strategy")
        print(f"{'='*70}")
        print(f"Total Trades: {len(self.trades)}")
        print(f"Wins: {len(wins)} | Losses: {len(losses)}")
        
        if wins or losses:
            closed = len(wins) + len(losses)
            wr = len(wins) / closed * 100 if closed > 0 else 0
            print(f"Win Rate: {wr:.1f}%")
            
            total_wins = sum(t['pnl'] for t in wins)
            total_losses = abs(sum(t['pnl'] for t in losses))
            print(f"Wins: ${total_wins:,.2f} | Losses: ${total_losses:,.2f}")
            
            pf = total_wins / total_losses if total_losses > 0 else 0
            print(f"Profit Factor: {pf:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        print(f"\nAll Trades:")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['symbol']:10} | {t['signal']} | D1:{t['d1']:8} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = CounterTrendStrategy()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()