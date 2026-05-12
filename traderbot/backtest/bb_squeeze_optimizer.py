"""
BB Squeeze Parameter Optimizer
================================
Sweeps key parameters on XRPUSDT, ADAUSDT, BNBUSDT to find
the best bb_squeeze configuration.
"""
import pandas as pd
import itertools
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from traderbot.connector.bybit_connector import BybitConnector
from traderbot.strategy.bb_squeeze import BBSqueezeStrategy

# --- Parameter grid ---
PARAM_GRID = {
    "bb_period":        [15, 20, 25],
    "bb_std":           [1.5, 2.0, 2.5],
    "squeeze_lookback": [15, 20, 25],
    "vol_mult":         [1.0, 1.25, 1.5],
    "atr_sl":           [1.0, 1.3, 1.5, 2.0],
    "atr_tp":           [2.5, 3.0, 4.0, 5.0],
}

SYMBOLS = ["XRPUSDT", "ADAUSDT", "BNBUSDT"]
INITIAL_BALANCE = 1000.0
DAYS = 40


def backtest_single(df, strategy, initial_balance):
    """Run a single backtest pass, return stats dict."""
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
            hit_tp = False  # conservative

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
    connector = BybitConnector()
    if not connector.connect():
        print("Failed to connect to Bybit.")
        return

    # Pre-fetch data for each symbol
    data = {}
    for sym in SYMBOLS:
        df = connector.get_historical_data(sym, "60", count=DAYS * 24)
        if df is not None and len(df) >= 100:
            data[sym] = df
            print(f"Loaded {sym}: {len(df)} bars")
        else:
            print(f"Skipping {sym} — insufficient data")

    if not data:
        print("No data loaded.")
        return

    # Build all param combos
    keys = list(PARAM_GRID.keys())
    combos = list(itertools.product(*PARAM_GRID.values()))
    total_combos = len(combos)
    print(f"\nTesting {total_combos} parameter combinations across {len(data)} symbols...")
    print("=" * 80)

    best_per_symbol = {s: {"pnl": -999999} for s in data}
    best_overall = {"score": -999999}

    for idx, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        strat = BBSqueezeStrategy(**params)

        combo_score = 0
        combo_results = {}

        for sym, df in data.items():
            res = backtest_single(df, strat, INITIAL_BALANCE)
            combo_results[sym] = res
            combo_score += res["pnl"]

            if res["pnl"] > best_per_symbol[sym]["pnl"]:
                best_per_symbol[sym] = {**res, "params": params.copy()}

        if combo_score > best_overall["score"]:
            best_overall = {"score": combo_score, "params": params.copy(), "results": combo_results}

        # Progress every 100 combos
        if (idx + 1) % 100 == 0 or idx == total_combos - 1:
            print(f"  [{idx + 1}/{total_combos}] Best combined PnL so far: ${best_overall['score']:+.2f}")

    # --- Print results ---
    print("\n" + "=" * 80)
    print("BEST PARAMETERS PER SYMBOL")
    print("=" * 80)
    for sym in SYMBOLS:
        if sym not in best_per_symbol or "params" not in best_per_symbol[sym]:
            continue
        b = best_per_symbol[sym]
        print(f"\n  {sym}:")
        print(f"    PnL: ${b['pnl']:+.2f} ({b['pnl_pct']:+.2f}%) | WR: {b['wr']:.1f}% | Trades: {b['total']}")
        print(f"    Params: {b['params']}")

    print("\n" + "=" * 80)
    print("BEST COMBINED (ALL 3 SYMBOLS)")
    print("=" * 80)
    bp = best_overall["params"]
    print(f"  Combined PnL: ${best_overall['score']:+.2f}")
    print(f"  Params: {bp}")
    for sym, res in best_overall["results"].items():
        print(f"    {sym}: PnL ${res['pnl']:+.2f} ({res['pnl_pct']:+.2f}%) | WR {res['wr']:.1f}% | {res['total']} trades")

    print("\n" + "=" * 80)
    print("RECOMMENDED bb_squeeze.py UPDATE")
    print("=" * 80)
    print(f"""
class BBSqueezeStrategy:
    def __init__(self, bb_period={bp['bb_period']}, bb_std={bp['bb_std']}, squeeze_lookback={bp['squeeze_lookback']},
                 vol_mult={bp['vol_mult']}, atr_period=14, atr_sl={bp['atr_sl']}, atr_tp={bp['atr_tp']}):
""")


if __name__ == "__main__":
    main()
