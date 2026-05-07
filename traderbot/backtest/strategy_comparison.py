"""
STRATEGY COMPARISON BACKTEST
==============================
Tests 3 new strategies vs current strategies on all coins.
Generates a side-by-side comparison HTML report.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import sys, os, time, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "traderbot"))

from traderbot.connector.bybit_connector import BybitConnector
from traderbot.strategy.entry_signals import MathRiskV3Signals
from traderbot.strategy.ema_crossover import EMACrossoverStrategy
from traderbot.strategy.rsi_strategy import RSIStrategy
from traderbot.strategy.bb_squeeze import BBSqueezeStrategy
from traderbot.strategy.rsi_divergence import RSIDivergenceStrategy
from traderbot.strategy.mtf_ema_crossover import MTFEmaCrossoverStrategy

INITIAL_BALANCE = 1000.0
RISK_PCT = 0.01
FEE_RATE = 0.001
LOOKAHEAD = 24
HISTORY_DAYS = 180
TIMEFRAME = "60"

COINS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT"]

# Tests to run: (label, strategy_key, coins)
TESTS = [
    # Current strategies
    ("CURRENT: math_risk_v3",   "math_risk_v3",   ["BTCUSDT"]),
    ("CURRENT: ema_crossover",  "ema_crossover",  ["ETHUSDT","XRPUSDT","BNBUSDT","SOLUSDT","DOGEUSDT","ADAUSDT"]),
    # New strategies - test on all
    ("NEW: bb_squeeze",         "bb_squeeze",     COINS),
    ("NEW: rsi_divergence",     "rsi_divergence", COINS),
    ("NEW: mtf_ema_crossover",  "mtf_ema",        COINS),
]

ALL_STRATEGIES = {
    "math_risk_v3":  MathRiskV3Signals(),
    "ema_crossover": EMACrossoverStrategy(),
    "rsi":           RSIStrategy(),
    "bb_squeeze":    BBSqueezeStrategy(),
    "rsi_divergence": RSIDivergenceStrategy(),
    "mtf_ema":       MTFEmaCrossoverStrategy(),
}


def fetch_klines(connector, symbol, interval, days):
    all_data = []
    end_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    needed = days * 24
    per = 200
    while len(all_data) < needed:
        try:
            res = connector.session.get_kline(
                category=connector.category, symbol=symbol,
                interval=str(interval), limit=per, end=end_ts)
            if res["retCode"] != 0 or not res["result"]["list"]:
                break
            page = res["result"]["list"]
            all_data.extend(page)
            end_ts = int(page[-1][0]) - 1
            if len(page) < per:
                break
            time.sleep(0.12)
        except Exception as e:
            print(f"  [WARN] {symbol}: {e}")
            break
    if not all_data:
        return None
    df = pd.DataFrame(all_data, columns=["time","open","high","low","close","volume","turnover"])
    df["time"] = pd.to_datetime(df["time"].astype(float), unit="ms")
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    return df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)


def run_backtest(df, strategy, initial=INITIAL_BALANCE):
    balance = initial
    peak = balance
    trades = []
    eq = [{"bar": 0, "bal": balance}]
    max_dd = 0
    max_cl = 0
    cl = 0

    for i in range(250, len(df) - LOOKAHEAD):
        lb = df.iloc[:i+1]
        try:
            direction, atr, atr_ratio, levels = strategy.get_signal(lb)
        except Exception:
            continue
        if not direction or levels is None:
            continue

        entry = lb["close"].iloc[-1]
        sl_d = levels["sl_distance"]
        tp_d = levels.get("tp2", levels.get("tp1", sl_d * 2))
        if sl_d <= 0 or tp_d <= 0:
            continue

        risk_amt = balance * RISK_PCT
        qty = risk_amt / sl_d
        fee = entry * qty * FEE_RATE
        balance -= fee

        if direction == "BUY":
            sl_p, tp_p = entry - sl_d, entry + tp_d
        else:
            sl_p, tp_p = entry + sl_d, entry - tp_d

        fut = df.iloc[i+1:i+1+LOOKAHEAD]
        result = "EXPIRED"
        exit_p = fut["close"].iloc[-1] if len(fut) > 0 else entry

        for _, bar in fut.iterrows():
            if direction == "BUY":
                if bar["low"] <= sl_p:
                    result, exit_p = "LOSS", sl_p; break
                if bar["high"] >= tp_p:
                    result, exit_p = "WIN", tp_p; break
            else:
                if bar["high"] >= sl_p:
                    result, exit_p = "LOSS", sl_p; break
                if bar["low"] <= tp_p:
                    result, exit_p = "WIN", tp_p; break

        pnl = (exit_p - entry) * qty if direction == "BUY" else (entry - exit_p) * qty
        balance += pnl

        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

        if result == "LOSS":
            cl += 1
            max_cl = max(max_cl, cl)
        else:
            cl = 0

        trades.append({"pnl": pnl, "result": result, "balance": balance,
                       "r": pnl / risk_amt if risk_amt > 0 else 0})
        eq.append({"bar": i, "bal": balance})

    return trades, eq, max_dd, max_cl


def calc_metrics(trades, initial):
    if not trades:
        return None
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    total = len(wins) + len(losses)
    wr = len(wins) / total * 100 if total > 0 else 0
    gp = sum(t["pnl"] for t in wins)
    gl = abs(sum(t["pnl"] for t in losses))
    pf = gp / gl if gl > 0 else 99
    net = sum(t["pnl"] for t in trades)
    aw = np.mean([t["pnl"] for t in wins]) if wins else 0
    al = abs(np.mean([t["pnl"] for t in losses])) if losses else 0
    exp = (wr/100 * aw) - ((1 - wr/100) * al)
    pnls = [t["pnl"] for t in trades]
    rets = np.array(pnls) / initial
    sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252*24) if len(rets)>1 and np.std(rets)>0 else 0
    ds = rets[rets < 0]
    sortino = np.mean(rets) / np.std(ds) * np.sqrt(252*24) if len(ds)>0 and np.std(ds)>0 else 0
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "wr": round(wr, 1), "pf": round(pf, 2), "net": round(net, 2),
        "net_pct": round(net/initial*100, 2),
        "aw": round(aw, 2), "al": round(al, 2),
        "payoff": round(aw/al, 2) if al > 0 else 99,
        "exp": round(exp, 2), "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "final": round(trades[-1]["balance"], 2),
        "avg_r": round(np.mean([t["r"] for t in trades if t["result"] in ("WIN","LOSS")]), 2) if trades else 0,
    }


def generate_report(results, path):
    rows = ""
    for r in results:
        m = r["m"]
        if not m:
            continue
        pc = "positive" if m["net"] >= 0 else "negative"
        wc = "positive" if m["wr"] >= 40 else ("caution" if m["wr"] >= 30 else "negative")
        is_new = "NEW" in r["label"]
        rc = "new-row" if is_new else "current-row"
        badge = "<span class='badge new'>NEW</span>" if is_new else "<span class='badge curr'>CURRENT</span>"
        rows += f"""<tr class="{rc}">
            <td>{r['coin']}</td><td>{badge} {r['strat']}</td>
            <td>{m['trades']}</td><td class="{wc}">{m['wr']}%</td>
            <td>{m['pf']}</td><td>{m['payoff']}</td>
            <td class="{pc}">${m['net']:+,.2f}</td>
            <td>{r['dd']*100:.1f}%</td><td>{m['sharpe']}</td>
            <td>${m['exp']:+,.2f}</td><td>${m['final']:,.2f}</td></tr>"""

    # Build equity chart JS
    charts_js = ""
    chart_divs = ""
    cidx = 0
    # Group by coin
    coins_seen = {}
    for r in results:
        if not r["m"]:
            continue
        coins_seen.setdefault(r["coin"], []).append(r)

    for coin, entries in coins_seen.items():
        datasets = ""
        colors = ["#818cf8", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#ec4899"]
        for j, e in enumerate(entries):
            eq = e["eq"]
            labs = [x["bar"] for x in eq]
            vals = [round(x["bal"], 2) for x in eq]
            col = colors[j % len(colors)]
            tag = "NEW" if "NEW" in e["label"] else "CUR"
            datasets += f"""{{
                label: '{tag}: {e["strat"]}',
                data: {json.dumps(vals)},
                borderColor: '{col}', backgroundColor: '{col}22',
                fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2
            }},"""
        chart_divs += f"""<div class="chart-card">
            <h3>{coin}</h3>
            <canvas id="ch_{cidx}" height="130"></canvas></div>"""
        charts_js += f"""new Chart(document.getElementById('ch_{cidx}'), {{
            type: 'line',
            data: {{ labels: {json.dumps(labs)}, datasets: [{datasets}] }},
            options: {{ responsive: true,
                scales: {{ x: {{ display: false }},
                    y: {{ ticks: {{ callback: v => '$'+v.toLocaleString() }} }} }} }}
        }});"""
        cidx += 1

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Strategy Comparison - TraderBot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{ --bg:#0f1117; --sf:#1a1d27; --bd:#2a2d3a; --tx:#e4e4e7; --mt:#71717a;
  --pos:#22c55e; --neg:#ef4444; --cau:#f59e0b; --acc:#818cf8; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--tx); padding:2rem; }}
h1 {{ font-size:1.75rem; margin-bottom:.25rem; }}
.sub {{ color:var(--mt); margin-bottom:1.5rem; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:2rem; }}
th {{ background:var(--sf); color:var(--mt); text-transform:uppercase; font-size:.72rem;
  letter-spacing:.06em; padding:.7rem .8rem; text-align:left; border-bottom:2px solid var(--bd); }}
td {{ padding:.55rem .8rem; border-bottom:1px solid var(--bd); font-size:.85rem; }}
tr:hover {{ background:#ffffff08; }}
.new-row td {{ background:#818cf808; }}
.positive {{ color:var(--pos); }} .negative {{ color:var(--neg); }} .caution {{ color:var(--cau); }}
.badge {{ font-size:.65rem; padding:2px 6px; border-radius:3px; font-weight:700; }}
.badge.new {{ background:var(--acc); color:#fff; }}
.badge.curr {{ background:var(--bd); color:var(--mt); }}
.charts-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:1rem; margin-top:1rem; }}
.chart-card {{ background:var(--sf); border:1px solid var(--bd); border-radius:10px; padding:1rem; }}
.chart-card h3 {{ font-size:1rem; margin-bottom:.5rem; }}
.legend {{ color:var(--mt); font-size:.8rem; margin-top:1rem; }}
</style></head><body>
<h1>Strategy Comparison Backtest</h1>
<p class="sub">Current vs New strategies | {HISTORY_DAYS} days H1 | ${INITIAL_BALANCE:,.0f} initial | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<table><thead><tr>
<th>Coin</th><th>Strategy</th><th>Trades</th><th>WR</th><th>PF</th><th>Payoff</th>
<th>Net P&L</th><th>Max DD</th><th>Sharpe</th><th>Expect</th><th>Final</th>
</tr></thead><tbody>{rows}</tbody></table>
<h2>Equity Curves (Current vs New)</h2>
<div class="charts-grid">{chart_divs}</div>
<p class="legend">Purple/Blue = NEW strategies | Green = Current strategies</p>
<script>{charts_js}</script>
</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[OK] HTML report: {path}")


def main():
    connector = BybitConnector()
    if not connector.connect():
        print("Failed to connect to Bybit.")
        return

    # Fetch data for all coins first
    data_cache = {}
    for coin in COINS:
        print(f"Fetching {coin}...")
        df = fetch_klines(connector, coin, TIMEFRAME, HISTORY_DAYS)
        if df is not None and len(df) >= 300:
            data_cache[coin] = df
            print(f"  OK: {len(df)} bars")
        else:
            print(f"  SKIP: insufficient data")

    # Run all tests
    results = []
    for label, strat_key, coins in TESTS:
        strategy = ALL_STRATEGIES[strat_key]
        for coin in coins:
            if coin not in data_cache:
                continue
            df = data_cache[coin]
            print(f"Testing {label} on {coin}...")
            trades, eq, dd, mcl = run_backtest(df, strategy)
            m = calc_metrics(trades, INITIAL_BALANCE)

            if m:
                status = "+" if m["net"] >= 0 else "-"
                print(f"  {status} {m['trades']}t WR:{m['wr']}% PF:{m['pf']} P&L:${m['net']:+,.2f}")
            else:
                print(f"  No trades generated")

            results.append({
                "coin": coin, "strat": strat_key, "label": label,
                "m": m, "eq": eq, "dd": dd, "mcl": mcl,
            })

    # Console summary
    print("\n" + "=" * 100)
    print("STRATEGY COMPARISON RESULTS")
    print("=" * 100)
    hdr = f"{'Coin':<10} {'Strategy':<20} {'Type':<8} {'Trades':<7} {'WR%':<6} {'PF':<6} {'Net P&L':>10} {'DD%':>6} {'Expect':>8}"
    print(hdr)
    print("-" * 100)
    for r in results:
        m = r["m"]
        if not m:
            continue
        t = "NEW" if "NEW" in r["label"] else "CUR"
        print(f"{r['coin']:<10} {r['strat']:<20} {t:<8} {m['trades']:<7} "
              f"{m['wr']:<6} {m['pf']:<6} ${m['net']:>+9,.2f} {r['dd']*100:>5.1f}% ${m['exp']:>+7,.2f}")

    # Best strategy per coin
    print("\n" + "=" * 100)
    print("BEST STRATEGY PER COIN (by expectancy)")
    print("=" * 100)
    for coin in COINS:
        coin_results = [r for r in results if r["coin"] == coin and r["m"]]
        if not coin_results:
            continue
        best = max(coin_results, key=lambda x: x["m"]["exp"])
        m = best["m"]
        tag = "NEW" if "NEW" in best["label"] else "CUR"
        print(f"  {coin:<10} -> {best['strat']:<20} [{tag}]  WR:{m['wr']}%  PF:{m['pf']}  "
              f"Exp:${m['exp']:+,.2f}  P&L:${m['net']:+,.2f}")

    # Generate HTML
    rpt = os.path.join(ROOT, "logs", "strategy_comparison.html")
    os.makedirs(os.path.dirname(rpt), exist_ok=True)
    generate_report(results, rpt)
    connector.shutdown()


if __name__ == "__main__":
    main()
