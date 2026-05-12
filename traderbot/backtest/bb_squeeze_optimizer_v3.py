"""
BB Squeeze Parameter Optimizer (v2 - Faster)
===========================================
Sweeps refined parameters on XRPUSDT, ADAUSDT, BNBUSDT.
"""
import pandas as pd
import itertools
import sys
import os
import time

# Ensure output is flushed
import functools
print = functools.partial(print, flush=True)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from traderbot.connector.bybit_connector import BybitConnector
from traderbot.strategy.bb_squeeze import BBSqueezeStrategy

# --- Refined Parameter grid (24 combos) ---
PARAM_GRID = {
    "bb_period":        [20],
    "bb_std":           [2.0, 2.5],
    "squeeze_lookback": [20],
    "vol_mult":         [1.2, 1.5],
    "atr_sl":           [1.5, 2.0],
    "atr_tp":           [3.0, 5.0],
}

SYMBOLS = ["XRPUSDT", "ADAUSDT", "BNBUSDT"]
INITIAL_BALANCE = 1000.0
DAYS = 30 # Reduced days to speed up

def backtest_single(df, strategy, initial_balance):
    balance = initial_balance
    wins = losses = 0

    for i in range(100, len(df) - 12):
        lb = df.iloc[:i + 1]
        direction, atr, atr_ratio, levels = strategy.get_signal(lb)
        if not direction:
            continue

        entry = lb['close'].iloc[-1]
        sl_dist = levels["sl_distance"]
        tp_dist = levels["tp1"]

        risk_amt = balance * 0.01
        qty = risk_amt / sl_dist
        fee = entry * qty * 0.001
        balance -= fee

        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        tp = entry + tp_dist if direction == "BUY" else entry - tp_dist

        fut = df.iloc[i + 1: i + 13]
        if len(fut) == 0:
            continue

        hit_sl = any(fut['low'] <= sl) if direction == "BUY" else any(fut['high'] >= sl)
        hit_tp = any(fut['high'] >= tp) if direction == "BUY" else any(fut['low'] <= tp)

        if hit_sl and hit_tp:
            hit_tp = False

        if hit_tp:
            balance += tp_dist * qty
            wins += 1
        elif hit_sl:
            balance -= sl_dist * qty
            losses += 1
        else:
            exit_p = fut['close'].iloc[-1]
            pnl = (exit_p - entry) * qty if direction == "BUY" else (entry - exit_p) * qty
            balance += pnl

    total = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "wr": (wins / total * 100) if total > 0 else 0,
        "pnl": balance - initial_balance,
        "pnl_pct": ((balance - initial_balance) / initial_balance) * 100,
        "final": balance,
    }

def main():
    print("DEBUG: Optimizer script started", flush=True)
    connector = BybitConnector()
    print("DEBUG: Connecting to Bybit...", flush=True)
    if not connector.connect():
        print("Failed to connect to Bybit.")
        return
    print("DEBUG: Connected to Bybit", flush=True)

    data = {}
    for sym in SYMBOLS:
        print(f"DEBUG: Fetching data for {sym}...", flush=True)
        df = connector.get_historical_data(sym, "60", count=DAYS * 24)
        if df is not None and len(df) >= 100:
            data[sym] = df
            print(f"DEBUG: Loaded {sym}: {len(df)} bars", flush=True)
        else:
            print(f"DEBUG: Skipping {sym} — insufficient data", flush=True)

    if not data:
        print("No data loaded.")
        return

    keys = list(PARAM_GRID.keys())
    combos = list(itertools.product(*PARAM_GRID.values()))
    total_combos = len(combos)
    print(f"DEBUG: Testing {total_combos} parameter combinations...", flush=True)

    best_overall = {"score": -999999}

    for idx, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        strat = BBSqueezeStrategy(**params)

        combo_score = 0
        for sym, df in data.items():
            res = backtest_single(df, strat, INITIAL_BALANCE)
            combo_score += res["pnl"]

        if combo_score > best_overall["score"]:
            best_overall = {"score": combo_score, "params": params.copy()}
            print(f"  New Best: ${combo_score:+.2f} with {params}", flush=True)

        if (idx + 1) % 5 == 0:
            print(f"  Progress: {idx+1}/{total_combos}", flush=True)

    print("\n" + "=" * 80)
    print("BEST COMBINED PARAMETERS")
    print("=" * 80)
    print(f"Params: {best_overall['params']}")
    print(f"Score: ${best_overall['score']:+.2f}")

if __name__ == "__main__":
    main()
