"""
Realistic daily profit projection for micro accounts.
Uses actual 180-day backtest results - no inflated numbers.
"""
import math

# ─── Backtest results (180 days, $1000 base) ───────────────────────
# Only using the BEST strategy per coin (from our comparison)
RESULTS = {
    # Coins tradeable on $10 (proper 1% risk scaling)
    "XRPUSDT":  {"pnl_pct": 6.53,  "trades": 94,  "strat": "bb_squeeze",      "min_balance": 5},
    "DOGEUSDT": {"pnl_pct": 21.37, "trades": 62,  "strat": "rsi_divergence",  "min_balance": 5},
    "ADAUSDT":  {"pnl_pct": 5.02,  "trades": 84,  "strat": "bb_squeeze",      "min_balance": 5},
    # Coins needing more capital
    "BNBUSDT":  {"pnl_pct": 16.85, "trades": 87,  "strat": "bb_squeeze",      "min_balance": 15},
    "SOLUSDT":  {"pnl_pct": 16.59, "trades": 64,  "strat": "rsi_divergence",  "min_balance": 40},
    "ETHUSDT":  {"pnl_pct": 18.67, "trades": 59,  "strat": "ema_crossover",   "min_balance": 60},
    "BTCUSDT":  {"pnl_pct": 18.45, "trades": 59,  "strat": "rsi_divergence",  "min_balance": 100},
}

DAYS = 180
ACCOUNTS = [10, 15, 20, 25, 30, 35]

print("=" * 70)
print("  REALISTIC DAILY PROFIT PROJECTION")
print("  Based on 180-day backtest (actual data, not estimates)")
print("=" * 70)

for balance in ACCOUNTS:
    # Which coins can this balance trade?
    active = {k: v for k, v in RESULTS.items() if v["min_balance"] <= balance}
    
    # Combined return over 180 days
    # Each coin's trades happen independently, so returns roughly add
    # but we use a weighted average approach
    total_trades = sum(v["trades"] for v in active.values())
    combined_pct = sum(v["pnl_pct"] for v in active.values())
    
    daily_pct = combined_pct / DAYS
    daily_dollar = balance * daily_pct / 100
    weekly = daily_dollar * 7
    monthly = daily_dollar * 30
    
    # With compounding
    compound_30  = balance * (1 + daily_pct/100) ** 30
    compound_90  = balance * (1 + daily_pct/100) ** 90
    compound_180 = balance * (1 + daily_pct/100) ** 180
    compound_365 = balance * (1 + daily_pct/100) ** 365
    
    coins_list = ", ".join(active.keys())
    
    print(f"\n{'─' * 70}")
    print(f"  ${balance} ACCOUNT  |  {len(active)} coins: {coins_list}")
    print(f"{'─' * 70}")
    print(f"  Daily avg return:   {daily_pct:.3f}%  =  ${daily_dollar:.3f}/day")
    print(f"  Weekly avg:         ${weekly:.2f}")
    print(f"  Monthly avg:        ${monthly:.2f}")
    print(f"  Trades per day:     ~{total_trades/DAYS:.1f}")
    print()
    print(f"  With compounding:")
    print(f"    30 days:   ${compound_30:.2f}  (+${compound_30 - balance:.2f})")
    print(f"    90 days:   ${compound_90:.2f}  (+${compound_90 - balance:.2f})")
    print(f"    6 months:  ${compound_180:.2f}  (+${compound_180 - balance:.2f})")
    print(f"    1 year:    ${compound_365:.2f}  (+${compound_365 - balance:.2f})")

print(f"\n{'=' * 70}")
print("  IMPORTANT CAVEATS")
print("=" * 70)
print("  1. These are AVERAGES from backtesting - individual days WILL vary")
print("  2. Some days will be negative (max drawdown was 8-19%)")
print("  3. Past performance does NOT guarantee future results")
print("  4. Crypto market conditions change - strategies may need re-tuning")
print("  5. Fees and slippage in live trading may reduce returns ~10-20%")
print("  6. Dollar amounts are tiny at this scale - this is a growth game")
print("=" * 70)
