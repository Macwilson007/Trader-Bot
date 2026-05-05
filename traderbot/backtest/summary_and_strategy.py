"""
===============================================================================
BACKTEST SUMMARY & ANALYSIS
===============================================================================

After extensive testing, here are the key findings:

1. STRATEGIES TESTED:
   - EMA Crossover + VWAP
   - S/R + Market Structure  
   - Multi-Timeframe Alignment (D1+H4+H1)
   - Trend Following with H4 filter
   - Counter-Trend with RSI
   - Session Momentum
   - Liquidity Sweeps
   - Various combinations

2. CONSISTENT RESULTS:
   - Win Rate: 0.8% - 15% across all strategies
   - All strategies lost money on historical data
   - 6-hour look-ahead window too short for 40-80 pip targets

3. ROOT CAUSE ANALYSIS:
   - XAUUSD experienced massive volatility in 2025-2026
   - No clear trend in London/NY sessions
   - All timeframes rarely aligned
   - High false breakout rate

4. RECOMMENDATION FOR THE BOT:

   Instead of automated strategies that require precise entry timing,
   consider a HYBRID approach:

   A) MANUAL SETUP + AUTOMATED EXECUTION:
      - Human identifies setups
      - Bot executes with proper risk management

   B) SIMPLIFIED STRATEGY (for automation):
      - Trade only at London Open (08:00 GMT)
      - Use Daily trend as ONLY filter
      - Very wide SL (100+ pips)
      - No TP (trail stop manually or use breakeven)

   C) MINIMAL TRADING:
      - Only trade 2-3 times per week
      - High conviction setups only
      - Larger position size for fewer trades

===============================================================================
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


class MinimalStrategy:
    """
    Conservative strategy with wide stops and manual risk management.
    Only trades London open, only when Daily trend is clear.
    """
    
    def __init__(self):
        self.initial_balance = 7157.31
        self.balance = self.initial_balance
        self.trades = []
        
    def run_simple_test(self):
        print("="*70)
        print("MINIMAL STRATEGY - Only London Open, Wide Stops")
        print("="*70)
        
        symbol = "XAUUSDc"
        start = datetime.now() - timedelta(days=180)
        end = datetime.now()
        
        d1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start - timedelta(days=200), end)
        h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, end)
        
        d1_df = pd.DataFrame(d1_rates)
        d1_df['time'] = pd.to_datetime(d1_df['time'], unit='s')
        
        h1_df = pd.DataFrame(h1_rates)
        h1_df['time'] = pd.to_datetime(h1_df['time'], unit='s')
        
        print(f"Data loaded: D1={len(d1_df)}, H1={len(h1_df)}")
        
        sl_pips = 100
        tp_pips = 150
        pip_val = 3.5
        pip_size = 0.01
        lot = 0.35
        
        london_open_trades = 0
        
        for i in range(100, len(h1_df) - 12):
            row = h1_df.iloc[i]
            
            if row['time'].hour != 8 or row['time'].minute != 0:
                continue
            
            london_open_trades += 1
            
            d1_before = d1_df[d1_df['time'] <= row['time']]
            if len(d1_before) < 50:
                continue
            
            d1_ema50 = d1_before['close'].ewm(span=50).mean().iloc[-1]
            d1_ema200 = d1_before['close'].ewm(span=200).mean().iloc[-1]
            d1_price = d1_before['close'].iloc[-1]
            
            if d1_ema50 > d1_ema200 and d1_price > d1_ema50:
                direction = "BUY"
            elif d1_ema50 < d1_ema200 and d1_price < d1_ema50:
                direction = "SELL"
            else:
                continue
            
            entry = h1_df.iloc[i]['close']
            
            if direction == "BUY":
                sl = entry - sl_pips * pip_size
                tp = entry + tp_pips * pip_size
            else:
                sl = entry + sl_pips * pip_size
                tp = entry - tp_pips * pip_size
            
            future = h1_df.iloc[i:i+12]
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
                "time": row['time'],
                "direction": direction,
                "d1_trend": "BULLISH" if d1_ema50 > d1_ema200 else "BEARISH",
                "result": result,
                "pnl": pnl
            })
            self.balance += pnl
        
        print(f"\nLondon Open opportunities: {london_open_trades}")
        print(f"Trades taken (with clear D1 trend): {len(self.trades)}")
        
        wins = [t for t in self.trades if t['result'] == 'TP']
        losses = [t for t in self.trades if t['result'] == 'SL']
        
        print(f"\nResults:")
        print(f"  Wins: {len(wins)}")
        print(f"  Losses: {len(losses)}")
        
        if wins or losses:
            closed = len(wins) + len(losses)
            wr = len(wins) / closed * 100 if closed > 0 else 0
            print(f"  Win Rate: {wr:.1f}%")
            
            total_pnl = self.balance - self.initial_balance
            print(f"  Net P&L: ${total_pnl:+,.2f}")
            print(f"  Final Balance: ${self.balance:,.2f}")
        
        print(f"\nAll Trades:")
        for t in self.trades:
            print(f"  {t['time'].strftime('%Y-%m-%d %H:%M')} | {t['direction']:5} | D1:{t['d1_trend']:8} | {t['result']} | ${t['pnl']:+,.2f}")


def main():
    mt5.initialize()
    mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
    
    strategy = MinimalStrategy()
    strategy.run_simple_test()
    
    mt5.shutdown()


if __name__ == "__main__":
    main()