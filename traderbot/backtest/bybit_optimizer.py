import pandas as pd
import sys
import os
import itertools

# Add root and traderbot directories to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from traderbot.connector.bybit_connector import BybitConnector
from traderbot.strategy.entry_signals import MathRiskV3Signals
from traderbot.strategy.ema_crossover import EMACrossoverStrategy
from traderbot.backtest.bybit_backtest import BybitBacktester

def optimize_math_risk(symbol, df):
    print(f"Optimizing MathRiskV3 for {symbol}...")
    
    atr_multipliers = [1.5, 2.0, 2.5, 3.0]
    adx_mins = [15, 20, 25, 30]
    
    results = []
    backtester = BybitBacktester()
    
    for atr_mult, adx_min in itertools.product(atr_multipliers, adx_mins):
        # Create strategy instance with these params
        strategy = MathRiskV3Signals()
        strategy.atr_multiplier = atr_mult
        strategy.adx_min = adx_min
        
        res = backtester.backtest_logic(symbol, df, strategy)
        
        pnl = res['final'] - 1000.0
        wr = (res['wins'] / (res['wins'] + res['losses']) * 100) if (res['wins'] + res['losses']) > 0 else 0
        
        results.append({
            "atr_mult": atr_mult,
            "adx_min": adx_min,
            "trades": len(res['trades']),
            "win_rate": wr,
            "pnl": pnl
        })
    
    df_results = pd.DataFrame(results).sort_values(by="pnl", ascending=False)
    print(df_results.head(5))
    return df_results.iloc[0]

def optimize_ema_crossover(symbol, df):
    print(f"Optimizing EMA Crossover for {symbol}...")
    
    atr_multipliers = [1.0, 1.2, 1.5, 2.0]
    tp_rs = [2.0, 3.0, 4.0, 5.0]
    
    results = []
    backtester = BybitBacktester()
    
    for atr_mult, tp_r in itertools.product(atr_multipliers, tp_rs):
        strategy = EMACrossoverStrategy(atr_multiplier=atr_mult, tp_r=tp_r)
        
        res = backtester.backtest_logic(symbol, df, strategy)
        
        pnl = res['final'] - 1000.0
        wr = (res['wins'] / (res['wins'] + res['losses']) * 100) if (res['wins'] + res['losses']) > 0 else 0
        
        results.append({
            "atr_mult": atr_mult,
            "tp_r": tp_r,
            "trades": len(res['trades']),
            "win_rate": wr,
            "pnl": pnl
        })
    
    df_results = pd.DataFrame(results).sort_values(by="pnl", ascending=False)
    print(df_results.head(5))
    return df_results.iloc[0]

if __name__ == "__main__":
    connector = BybitConnector()
    if not connector.connect():
        print("Failed to connect")
        sys.exit()
        
    # Get 30 days of data for optimization
    btc_df = connector.get_historical_data("BTCUSDT", "60", count=720)
    eth_df = connector.get_historical_data("ETHUSDT", "60", count=720)
    
    best_btc = optimize_math_risk("BTCUSDT", btc_df)
    print(f"\nBEST BTC PARAMS: ATR_Mult={best_btc['atr_mult']}, ADX_Min={best_btc['adx_min']} | PnL: ${best_btc['pnl']:.2f}")
    
    best_eth = optimize_ema_crossover("ETHUSDT", eth_df)
    print(f"\nBEST ETH PARAMS: ATR_Mult={best_eth['atr_mult']}, TP_R={best_eth['tp_r']} | PnL: ${best_eth['pnl']:.2f}")
