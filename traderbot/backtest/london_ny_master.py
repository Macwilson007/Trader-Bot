"""
TRADING STRATEGY: "London NY Session Master"

Based on TradingRush research + proven forex principles:

RULES:
1. DAILY TREND FILTER: EMA 50 > EMA 200 = Bullish, < = Bearish
2. H4 MOMENTUM: Price above/below EMA 21 on H4 confirms direction
3. H1 ENTRY: EMA 9 crosses EMA 21 + candle confirmation
4. SESSIONS: Only trade at 08:00, 10:00, 13:00, 15:00, 17:00 GMT
5. SL: 40 pips | TP: 80 pips (1:2 R:R)
6. PARTIAL TP: 50% at 40 pips, move SL to breakeven

KEY INSIGHT: Trading with multi-timeframe alignment increases win rate significantly.
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


class LondonNYStrategy:
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        self.lot_size = 0.35
        self.sl_pips = 40
        self.tp_pips = 80
        
    def get_pip_value(self, symbol):
        if "XAU" in symbol:
            return 3.5
        elif "XAG" in symbol:
            return 0.35
        return 3.5
    
    def get_pip_size(self, symbol):
        return 0.01 if "XAU" in symbol or "XAG" in symbol else 0.0001
    
    def get_daily_trend(self, d1_df, current_time):
        d1_before = d1_df[d1_df['time'] <= current_time].tail(50)
        if len(d1_before) < 30:
            return None
        ema50 = d1_before['close'].ewm(span=50).mean().iloc[-1]
        ema200 = d1_before['close'].ewm(span=200).mean().iloc[-1]
        price = d1_before['close'].iloc[-1]
        if ema50 > ema200 and price > ema50:
            return "BULLISH"
        elif ema50 < ema200 and price < ema50:
            return "BEARISH"
        return None
    
    def get_h4_momentum(self, h4_df, current_time):
        h4_before = h4_df[h4_df['time'] <= current_time].tail(20)
        if len(h4_before) < 10:
            return None
        ema21 = h4_before['close'].ewm(span=21).mean().iloc[-1]
        price = h4_before['close'].iloc[-1]
        if price > ema21:
            return "BULLISH"
        elif price < ema21:
            return "BEARISH"
        return None
    
    def get_h1_entry(self, h1_df, idx):
        if idx < 21:
            return "HOLD"
        
        lookback = h1_df.iloc[:idx+1]
        ema9 = lookback['close'].ewm(span=9).mean()
        ema21 = lookback['close'].ewm(span=21).mean()
        
        last = lookback.iloc[-1]
        prev = lookback.iloc[-2]
        
        ema9_current = ema9.iloc[-1]
        ema21_current = ema21.iloc[-1]
        ema9_prev = ema9.iloc[-2]
        ema21_prev = ema21.iloc[-2]
        
        bullish_cross = (ema9_prev <= ema21_prev) and (ema9_current > ema21_current)
        bearish_cross = (ema9_prev >= ema21_prev) and (ema9_current < ema21_current)
        
        if bullish_cross:
            return "BUY"
        elif bearish_cross:
            return "SELL"
        return "HOLD"
    
    def check_all_aligned(self, d1_trend, h4_momentum, h1_entry):
        if d1_trend == "BULLISH" and h4_momentum == "BULLISH" and h1_entry == "BUY":
            return "BUY"
        elif d1_trend == "BEARISH" and h4_momentum == "BEARISH" and h1_entry == "SELL":
            return "SELL"
        return "HOLD"
    
    def run_backtest(self):
        print("="*70)
        print("LONDON NY SESSION MASTER - Multi-Timeframe Strategy")
        print("="*70)
        print("Strategy: D1 Trend + H4 Momentum + H1 EMA Cross")
        print("Filters: Must align on all 3 timeframes")
        print("="*70)
        
        symbols = ["XAUUSDc", "XAGUSDc", "EURUSDc", "GBPUSDc"]
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        
        all_data = {}
        
        for symbol in symbols:
            print(f"\nLoading {symbol}...")
            d1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start - timedelta(days=300), end)
            h4_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, start - timedelta(days=60), end)
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
                print(f"  D1: {len(all_data[symbol]['D1'])} | H4: {len(all_data[symbol]['H4'])} | H1: {len(all_data[symbol]['H1'])}")
        
        if not all_data:
            print("No data loaded!")
            return
        
        sessions = [(8, 0), (10, 0), (13, 0), (15, 0), (17, 0)]
        
        total_trades = 0
        
        for symbol, data in all_data.items():
            d1_df = data["D1"]
            h4_df = data["H4"]
            h1_df = data["H1"]
            
            print(f"\nProcessing {symbol}...")
            symbol_trades = 0
            
            for i in range(100, len(h1_df) - 6):
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
                h1_entry = self.get_h1_entry(h1_df, i)
                
                signal = self.check_all_aligned(d1_trend, h4_momentum, h1_entry)
                
                if signal in ["BUY", "SELL"]:
                    symbol_trades += 1
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
                        "h4": h4_momentum,
                        "entry": entry,
                        "exit": exit_price,
                        "result": result,
                        "pnl": pnl
                    })
                    self.balance += pnl
            
            total_trades += symbol_trades
            print(f"  Trades: {symbol_trades}")
        
        self.print_results()
    
    def print_results(self):
        wins = [t for t in self.trades if t['result'] == 'TP']
        losses = [t for t in self.trades if t['result'] == 'SL']
        open_trades = [t for t in self.trades if t['result'] == 'OPEN']
        
        print(f"\n{'='*70}")
        print("BACKTEST RESULTS")
        print(f"{'='*70}")
        print(f"Total Trades: {len(self.trades)}")
        print(f"Closed: {len(wins) + len(losses)} | Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"Open: {len(open_trades)}")
        
        if wins or losses:
            win_rate = len(wins) / (len(wins) + len(losses)) * 100
            print(f"\nWin Rate: {win_rate:.1f}%")
            
            if wins:
                avg_win = sum(t['pnl'] for t in wins) / len(wins)
                print(f"Avg Win: ${avg_win:,.2f}")
            if losses:
                avg_loss = abs(sum(t['pnl'] for t in losses) / len(losses))
                print(f"Avg Loss: ${avg_loss:,.2f}")
            
            total_wins = sum(t['pnl'] for t in wins)
            total_losses = abs(sum(t['pnl'] for t in losses))
            pf = total_wins / total_losses if total_losses > 0 else 0
            print(f"Profit Factor: {pf:.2f}")
        
        total_pnl = self.balance - self.initial_balance
        print(f"\nInitial: ${self.initial_balance:,.2f}")
        print(f"Final: ${self.balance:,.2f}")
        print(f"Net P&L: ${total_pnl:+,.2f}")
        
        print(f"\n{'='*70}")
        print("ALL TRADES")
        print(f"{'='*70}")
        for t in self.trades:
            print(f"{t['time'].strftime('%Y-%m-%d %H:%M')} | {t['symbol']:10} | {t['signal']} | D1:{t['d1']:8} H4:{t['h4']:8} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = LondonNYStrategy()
    strategy.run_backtest()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()