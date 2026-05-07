"""
ROBUST MULTI-COIN BACKTEST ENGINE
==================================
Tests all coins the bot trades (BTC, ETH, XRP) plus additional crypto pairs.
Fetches extended history via pagination, runs each strategy per-symbol, and
produces professional-grade metrics + an HTML report with equity curves.

Usage:
    py traderbot/backtest/robust_multi_coin_backtest.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import sys
import os
import time
import json
import math

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "traderbot"))

from traderbot.connector.bybit_connector import BybitConnector
from traderbot.strategy.entry_signals import MathRiskV3Signals
from traderbot.strategy.rsi_strategy import RSIStrategy
from traderbot.strategy.ema_crossover import EMACrossoverStrategy
from traderbot.config import SYMBOLS, SYMBOL_STRATEGIES, STRATEGY_CONFIG

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INITIAL_BALANCE = 1000.0
RISK_PER_TRADE  = 0.01        # 1 %
FEE_RATE        = 0.001       # 0.1 % round-trip fee estimate
LOOK_AHEAD_BARS = 24          # max bars to wait for SL/TP hit (24 h on H1)
HISTORY_DAYS    = 180         # 6 months of data
TIMEFRAME       = "60"        # H1

# Coins: the 3 the bot actually trades + 7 extras for benchmarking
COINS_TO_TEST = [
    # --- Primary (bot-traded) ---
    "BTCUSDT", "ETHUSDT", "XRPUSDT",
    # --- Extended universe ---
    "SOLUSDT", "DOGEUSDT", "ADAUSDT",
    "BNBUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT",
]

# Which strategy to use per symbol (fallback = math_risk_v3)
STRATEGY_MAP = {
    "BTCUSDT":  "math_risk_v3",
    "ETHUSDT":  "ema_crossover",
    "XRPUSDT":  "ema_crossover",
    # All extras default to each strategy in turn (we'll test both)
}

# ---------------------------------------------------------------------------
# Helper: paginated kline fetch (Bybit caps at 200 per call)
# ---------------------------------------------------------------------------
def fetch_extended_klines(connector, symbol, interval, days):
    """Fetch >200 bars by paginating backwards."""
    all_data = []
    end_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    bars_needed = days * 24  # H1
    per_page = 200

    while len(all_data) < bars_needed:
        try:
            res = connector.session.get_kline(
                category=connector.category,
                symbol=symbol,
                interval=str(interval),
                limit=per_page,
                end=end_ts,
            )
            if res["retCode"] != 0 or not res["result"]["list"]:
                break

            page = res["result"]["list"]
            all_data.extend(page)

            # Bybit returns newest-first; last element is oldest
            oldest_ts = int(page[-1][0])
            end_ts = oldest_ts - 1  # next page ends just before this

            if len(page) < per_page:
                break  # no more data

            time.sleep(0.12)  # rate-limit courtesy
        except Exception as e:
            print(f"  [WARN] Pagination error for {symbol}: {e}")
            break

    if not all_data:
        return None

    df = pd.DataFrame(all_data, columns=["time", "open", "high", "low", "close", "volume", "turnover"])
    df["time"] = pd.to_datetime(df["time"].astype(float), unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Core backtest engine
# ---------------------------------------------------------------------------
class RobustBacktester:
    def __init__(self, initial_balance=INITIAL_BALANCE):
        self.initial_balance = initial_balance
        self.strategies = {
            "math_risk_v3":  MathRiskV3Signals(),
            "ema_crossover": EMACrossoverStrategy(),
            "rsi":           RSIStrategy(),
        }

    def run_single(self, symbol, df, strategy_key):
        strategy = self.strategies[strategy_key]
        balance = self.initial_balance
        peak_balance = balance
        trades = []
        equity_curve = [{"bar": 0, "balance": balance}]
        max_dd = 0
        consecutive_losses = 0
        max_consec_losses = 0

        warmup = 250  # enough for EMA-200 + ADX

        for i in range(warmup, len(df) - LOOK_AHEAD_BARS):
            lb = df.iloc[: i + 1]
            try:
                direction, atr, atr_ratio, levels = strategy.get_signal(lb)
            except Exception:
                continue

            if not direction or levels is None:
                continue

            entry_price = lb["close"].iloc[-1]
            entry_time  = lb["time"].iloc[-1]
            sl_dist     = levels["sl_distance"]
            tp_dist     = levels.get("tp2", levels.get("tp1", sl_dist * 2))

            if sl_dist <= 0 or tp_dist <= 0:
                continue

            # Position sizing: risk 1 % of current balance
            risk_amount = balance * RISK_PER_TRADE
            qty = risk_amount / sl_dist

            # Fee
            fee = entry_price * qty * FEE_RATE
            balance -= fee

            # SL / TP prices
            if direction == "BUY":
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tp_dist
            else:
                sl_price = entry_price + sl_dist
                tp_price = entry_price - tp_dist

            # Simulate bar-by-bar to find which hits first
            future = df.iloc[i + 1: i + 1 + LOOK_AHEAD_BARS]
            result = "EXPIRED"
            exit_price = future["close"].iloc[-1] if len(future) > 0 else entry_price
            exit_time  = future["time"].iloc[-1] if len(future) > 0 else entry_time

            for _, bar in future.iterrows():
                if direction == "BUY":
                    if bar["low"] <= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = bar["time"]
                        break
                    if bar["high"] >= tp_price:
                        result = "WIN"
                        exit_price = tp_price
                        exit_time = bar["time"]
                        break
                else:  # SELL
                    if bar["high"] >= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = bar["time"]
                        break
                    if bar["low"] <= tp_price:
                        result = "WIN"
                        exit_price = tp_price
                        exit_time = bar["time"]
                        break

            # Calculate P&L
            if direction == "BUY":
                pnl = (exit_price - entry_price) * qty
            else:
                pnl = (entry_price - exit_price) * qty

            balance += pnl

            # Drawdown tracking
            if balance > peak_balance:
                peak_balance = balance
            dd = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
            if dd > max_dd:
                max_dd = dd

            # Consecutive loss tracking
            if result == "LOSS":
                consecutive_losses += 1
                max_consec_losses = max(max_consec_losses, consecutive_losses)
            else:
                consecutive_losses = 0

            r_multiple = pnl / risk_amount if risk_amount > 0 else 0

            trades.append({
                "entry_time":  entry_time,
                "exit_time":   exit_time,
                "direction":   direction,
                "entry_price": entry_price,
                "exit_price":  exit_price,
                "sl":          sl_price,
                "tp":          tp_price,
                "qty":         qty,
                "fee":         fee,
                "pnl":         pnl,
                "result":      result,
                "r_multiple":  r_multiple,
                "balance":     balance,
            })
            equity_curve.append({"bar": i, "balance": balance})

        return trades, equity_curve, max_dd, max_consec_losses


# ---------------------------------------------------------------------------
# Metrics calculator
# ---------------------------------------------------------------------------
def compute_metrics(trades, initial_balance):
    if not trades:
        return {}

    pnls = [t["pnl"] for t in trades]
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    expired = [t for t in trades if t["result"] == "EXPIRED"]

    total = len(wins) + len(losses)
    win_rate = len(wins) / total * 100 if total > 0 else 0

    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss   = abs(sum(t["pnl"] for t in losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    net_pnl = sum(pnls)
    net_pct = net_pnl / initial_balance * 100

    avg_win  = np.mean([t["pnl"] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t["pnl"] for t in losses])) if losses else 0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # Expectancy per trade (in $)
    expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

    # R-multiples
    r_multiples = [t["r_multiple"] for t in trades if t["result"] in ("WIN", "LOSS")]
    avg_r = np.mean(r_multiples) if r_multiples else 0

    # Sharpe & Sortino (annualised, assuming H1 bars → 24 trades/day proxy)
    if len(pnls) > 1:
        returns = np.array(pnls) / initial_balance
        sharpe  = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0
        downside = returns[returns < 0]
        sortino = np.mean(returns) / np.std(downside) * np.sqrt(252 * 24) if len(downside) > 0 and np.std(downside) > 0 else 0
    else:
        sharpe = sortino = 0

    final_balance = trades[-1]["balance"]

    return {
        "total_trades":    len(trades),
        "closed_trades":   total,
        "wins":            len(wins),
        "losses":          len(losses),
        "expired":         len(expired),
        "win_rate":        round(win_rate, 1),
        "profit_factor":   round(profit_factor, 2),
        "net_pnl":         round(net_pnl, 2),
        "net_pct":         round(net_pct, 2),
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
        "payoff_ratio":    round(payoff_ratio, 2),
        "expectancy":      round(expectancy, 2),
        "avg_r":           round(avg_r, 2),
        "sharpe":          round(sharpe, 2),
        "sortino":         round(sortino, 2),
        "final_balance":   round(final_balance, 2),
    }


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------
def print_report(results_all):
    print("\n" + "=" * 90)
    print("  ROBUST MULTI-COIN BACKTEST REPORT")
    print(f"  Period: {HISTORY_DAYS} days  |  Timeframe: H1  |  Initial Balance: ${INITIAL_BALANCE:,.2f}")
    print("=" * 90)

    header = (
        f"{'Symbol':<12} {'Strategy':<16} {'Trades':<7} {'WR%':<7} {'PF':<7} "
        f"{'Net P&L':>10} {'MaxDD%':>7} {'Sharpe':>7} {'Expect$':>9} {'Final$':>10}"
    )
    print(header)
    print("-" * 90)

    total_pnl = 0
    for r in results_all:
        m = r["metrics"]
        if not m:
            print(f"{r['symbol']:<12} {'N/A':<16} {'--':<7}")
            continue

        total_pnl += m["net_pnl"]
        is_primary = r["symbol"] in ("BTCUSDT", "ETHUSDT", "XRPUSDT")
        marker = " *" if is_primary else ""

        print(
            f"{r['symbol']:<12} {r['strategy']:<16} "
            f"{m['total_trades']:<7} {m['win_rate']:<7} {m['profit_factor']:<7} "
            f"${m['net_pnl']:>+9,.2f} {r['max_dd']*100:>6.1f}% "
            f"{m['sharpe']:>6.2f}  ${m['expectancy']:>+8,.2f} "
            f"${m['final_balance']:>9,.2f}{marker}"
        )

    print("-" * 90)
    print(f"{'PORTFOLIO':<29} {'':>27} ${total_pnl:>+9,.2f}")
    print("=" * 90)
    print("  * = primary bot-traded pair\n")

    # Detailed per-coin breakdown
    for r in results_all:
        m = r["metrics"]
        if not m:
            continue
        print(f"\n{'─' * 60}")
        print(f"  {r['symbol']}  ({r['strategy']})")
        print(f"{'─' * 60}")
        print(f"  Closed Trades: {m['closed_trades']}  |  Expired: {m['expired']}")
        print(f"  Wins: {m['wins']}  |  Losses: {m['losses']}  |  Win Rate: {m['win_rate']}%")
        print(f"  Avg Win: ${m['avg_win']:,.2f}  |  Avg Loss: ${m['avg_loss']:,.2f}  |  Payoff: {m['payoff_ratio']:.2f}")
        print(f"  Profit Factor: {m['profit_factor']:.2f}  |  Expectancy: ${m['expectancy']:,.2f}/trade")
        print(f"  Avg R-Multiple: {m['avg_r']:.2f}R")
        print(f"  Sharpe: {m['sharpe']:.2f}  |  Sortino: {m['sortino']:.2f}")
        print(f"  Max Drawdown: {r['max_dd']*100:.1f}%  |  Max Consec Losses: {r['max_consec_losses']}")
        print(f"  Net P&L: ${m['net_pnl']:+,.2f} ({m['net_pct']:+.2f}%)")
        print(f"  Final Balance: ${m['final_balance']:,.2f}")


# ---------------------------------------------------------------------------
# HTML Report Generator
# ---------------------------------------------------------------------------
def generate_html_report(results_all, output_path):
    """Create a self-contained HTML report with embedded equity curves."""

    rows_html = ""
    charts_js = ""

    for idx, r in enumerate(results_all):
        m = r["metrics"]
        if not m:
            continue

        is_primary = r["symbol"] in ("BTCUSDT", "ETHUSDT", "XRPUSDT")
        row_class = "primary" if is_primary else ""

        # Color-code P&L
        pnl_class = "positive" if m["net_pnl"] >= 0 else "negative"
        wr_class = "positive" if m["win_rate"] >= 50 else ("caution" if m["win_rate"] >= 35 else "negative")

        rows_html += f"""
        <tr class="{row_class}">
            <td><strong>{r['symbol']}</strong>{'  ⭐' if is_primary else ''}</td>
            <td>{r['strategy']}</td>
            <td>{m['total_trades']}</td>
            <td class="{wr_class}">{m['win_rate']}%</td>
            <td>{m['profit_factor']}</td>
            <td class="{pnl_class}">${m['net_pnl']:+,.2f}</td>
            <td>{r['max_dd']*100:.1f}%</td>
            <td>{m['sharpe']}</td>
            <td>{m['sortino']}</td>
            <td>${m['expectancy']:+,.2f}</td>
            <td>${m['final_balance']:,.2f}</td>
        </tr>"""

        # Equity curve data
        eq = r["equity_curve"]
        labels = [e["bar"] for e in eq]
        values = [round(e["balance"], 2) for e in eq]
        border_color = "#22c55e" if m["net_pnl"] >= 0 else "#ef4444"

        charts_js += f"""
        new Chart(document.getElementById('chart_{idx}'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: '{r["symbol"]} Equity',
                    data: {json.dumps(values)},
                    borderColor: '{border_color}',
                    backgroundColor: '{border_color}22',
                    fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ display: false }},
                    y: {{ ticks: {{ callback: v => '$' + v.toLocaleString() }} }}
                }}
            }}
        }});
        """

    # Build equity curve canvas divs
    chart_divs = ""
    for idx, r in enumerate(results_all):
        if not r["metrics"]:
            continue
        chart_divs += f"""
        <div class="chart-card">
            <h3>{r['symbol']} <span class="strategy-tag">{r['strategy']}</span></h3>
            <canvas id="chart_{idx}" height="120"></canvas>
        </div>"""

    total_pnl = sum(r["metrics"]["net_pnl"] for r in results_all if r["metrics"])
    total_trades = sum(r["metrics"]["total_trades"] for r in results_all if r["metrics"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TraderBot Robust Backtest Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e4e4e7; --muted: #71717a; --accent: #818cf8;
    --positive: #22c55e; --negative: #ef4444; --caution: #f59e0b;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 2rem; }}
  h1 {{ font-size: 1.75rem; margin-bottom: 0.25rem; }}
  .subtitle {{ color: var(--muted); margin-bottom: 2rem; font-size: 0.95rem; }}
  .kpi-strip {{ display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.5rem; min-width: 160px; }}
  .kpi .label {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .kpi .value {{ font-size: 1.4rem; font-weight: 700; margin-top: 0.25rem; }}
  .positive {{ color: var(--positive); }}
  .negative {{ color: var(--negative); }}
  .caution  {{ color: var(--caution); }}

  table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
  th {{ background: var(--surface); color: var(--muted); text-transform: uppercase; font-size: 0.75rem;
       letter-spacing: 0.06em; padding: 0.75rem 1rem; text-align: left; border-bottom: 2px solid var(--border); }}
  td {{ padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
  tr:hover {{ background: #ffffff08; }}
  tr.primary td {{ background: #818cf808; }}

  .charts-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 1rem; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem; }}
  .chart-card h3 {{ font-size: 1rem; margin-bottom: 0.5rem; }}
  .strategy-tag {{ background: var(--accent); color: #fff; font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; margin-left: 0.5rem; }}

  footer {{ color: var(--muted); font-size: 0.8rem; margin-top: 2rem; text-align: center; }}
</style>
</head>
<body>

<h1>🤖 TraderBot — Robust Multi-Coin Backtest</h1>
<p class="subtitle">Period: {HISTORY_DAYS} days &nbsp;|&nbsp; Timeframe: H1 &nbsp;|&nbsp;
  Initial Balance: ${INITIAL_BALANCE:,.2f} &nbsp;|&nbsp; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<div class="kpi-strip">
  <div class="kpi"><div class="label">Total P&amp;L</div>
    <div class="value {'positive' if total_pnl >= 0 else 'negative'}">${total_pnl:+,.2f}</div></div>
  <div class="kpi"><div class="label">Coins Tested</div>
    <div class="value">{len([r for r in results_all if r['metrics']])}</div></div>
  <div class="kpi"><div class="label">Total Trades</div>
    <div class="value">{total_trades}</div></div>
  <div class="kpi"><div class="label">History</div>
    <div class="value">{HISTORY_DAYS}d</div></div>
</div>

<table>
<thead>
  <tr>
    <th>Symbol</th><th>Strategy</th><th>Trades</th><th>Win Rate</th><th>PF</th>
    <th>Net P&amp;L</th><th>Max DD</th><th>Sharpe</th><th>Sortino</th>
    <th>Expect/Trade</th><th>Final Bal</th>
  </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>

<h2 style="margin-bottom:1rem;">📈 Equity Curves</h2>
<div class="charts-grid">
{chart_divs}
</div>

<footer>TraderBot Backtest Engine &mdash; Data from Bybit API</footer>

<script>
{charts_js}
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ HTML report saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    connector = BybitConnector()
    if not connector.connect():
        print("❌ Failed to connect to Bybit. Check API keys / network.")
        return

    bt = RobustBacktester(initial_balance=INITIAL_BALANCE)
    all_results = []

    for symbol in COINS_TO_TEST:
        print(f"\n{'━' * 50}")
        print(f"  Fetching {symbol} ({HISTORY_DAYS}d of H1 data)...")

        df = fetch_extended_klines(connector, symbol, TIMEFRAME, HISTORY_DAYS)
        if df is None or len(df) < 300:
            print(f"  ⚠ Insufficient data for {symbol} ({0 if df is None else len(df)} bars). Skipping.")
            all_results.append({
                "symbol": symbol, "strategy": "N/A",
                "metrics": {}, "trades": [], "equity_curve": [],
                "max_dd": 0, "max_consec_losses": 0,
            })
            continue

        print(f"  ✓ Loaded {len(df)} bars  ({df['time'].iloc[0].date()} → {df['time'].iloc[-1].date()})")

        # Pick strategy
        strat_key = STRATEGY_MAP.get(symbol, "ema_crossover")
        print(f"  Running strategy: {strat_key}")

        trades, equity, max_dd, max_consec = bt.run_single(symbol, df, strat_key)
        metrics = compute_metrics(trades, INITIAL_BALANCE)

        all_results.append({
            "symbol":            symbol,
            "strategy":          strat_key,
            "metrics":           metrics,
            "trades":            trades,
            "equity_curve":      equity,
            "max_dd":            max_dd,
            "max_consec_losses": max_consec,
        })

        if metrics:
            status = "✅" if metrics["net_pnl"] >= 0 else "🔴"
            print(f"  {status} {metrics['total_trades']} trades | WR {metrics['win_rate']}% | "
                  f"PF {metrics['profit_factor']} | P&L ${metrics['net_pnl']:+,.2f}")

    # Print console report
    print_report(all_results)

    # Generate HTML report
    report_dir = os.path.join(ROOT, "logs")
    os.makedirs(report_dir, exist_ok=True)
    html_path = os.path.join(report_dir, "backtest_report.html")
    generate_html_report(all_results, html_path)

    connector.shutdown()


if __name__ == "__main__":
    main()
