#!/usr/bin/env python3
"""Research: Trend filter variants for Ascent (momentum) strategy.

Tests multiple approaches to see if any market regime filter
improves risk-adjusted returns without destroying CAGR.

Variants tested:
  1. No filter (baseline — current production)
  2. 200-day SMA on Nifty 50
  3. 150-day SMA on Nifty 50
  4. 100-day SMA on Nifty 50
  5. 10-month momentum on Nifty 50 (Antonacci dual momentum)
  6. 50/200 golden cross on Nifty 50

Usage:
    python -m scripts.research_trend_filter
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.backtest.costs import CostConfig
from trading.backtest.engine import run_backtest
from trading.data.loader import fetch_benchmark, fetch_many, to_price_panel
from trading.data.universe import smallcap_universe
from trading.portfolio.constructor import resample_to_rebalance_dates, top_n_equal_weight
from trading.reporting.metrics import summary
from trading.signals.momentum import momentum_n_m
from trading.utils.logging import setup_logging

log = setup_logging("trend_research")


def main():
    # ── Load data (same as production Ascent config)
    tickers = smallcap_universe()
    start = "2010-01-01"
    top_n = 15
    freq = "ME"
    rfr = 0.06
    cost_config = CostConfig(slippage_per_side=0.003)

    log.info(f"Loading data for {len(tickers)} tickers from {start}...")
    price_dict = fetch_many(tickers, start=start)
    prices = to_price_panel(price_dict, field="adj_close")
    log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

    # Benchmark
    bench_df = fetch_benchmark("^NSEI", start=start)
    nifty = bench_df["adj_close"]
    log.info(f"Nifty data: {len(nifty)} days")

    # Momentum scores (computed once, reused across all variants)
    scores = momentum_n_m(prices, lookback_months=12, skip_months=1)
    log.info("Momentum scores computed")

    # ── Define trend filter variants
    filters = {}

    # 1. No filter (baseline)
    filters["No filter (baseline)"] = None

    # 2-4. SMA filters
    for window in [100, 150, 200]:
        sma = nifty.rolling(window).mean()
        filters[f"SMA-{window}"] = nifty > sma

    # 5. 10-month momentum (Antonacci)
    mom_10m = nifty / nifty.shift(210) - 1  # ~10 months
    filters["10M momentum"] = mom_10m > 0

    # 6. 50/200 golden cross
    sma_50 = nifty.rolling(50).mean()
    sma_200 = nifty.rolling(200).mean()
    filters["Golden cross (50/200)"] = sma_50 > sma_200

    # ── Run backtests
    results = []

    for name, risk_on in filters.items():
        log.info(f"Running: {name}...")

        daily_weights = top_n_equal_weight(scores, top_n=top_n, risk_on=risk_on)
        rebal_weights = resample_to_rebalance_dates(daily_weights, frequency=freq)

        bt = run_backtest(
            prices=prices,
            target_weights_at_rebal=rebal_weights,
            cost_config=cost_config,
            initial_capital=1.0,
        )

        sm = summary(bt.equity_curve, bt.returns, risk_free_rate=rfr)

        # Time in market
        if risk_on is not None:
            aligned = risk_on.reindex(prices.index).ffill()
            time_in = aligned.mean()
        else:
            time_in = 1.0

        # Calmar ratio (CAGR / max DD)
        cagr = sm["cagr"]
        max_dd = abs(sm["max_drawdown"])
        calmar = cagr / max_dd if max_dd > 0 else 0

        results.append({
            "Filter": name,
            "CAGR": sm["cagr"],
            "Max DD": sm["max_drawdown"],
            "Sharpe": sm["sharpe"],
            "Sortino": sm["sortino"],
            "Calmar": calmar,
            "Vol": sm["annual_vol"],
            "Win Rate": sm["win_rate_monthly"],
            "Time In Mkt": time_in,
            "Final Eq": sm["final_equity"],
        })

        log.info(
            f"  CAGR={cagr:.1%}  MaxDD={sm['max_drawdown']:.1%}  "
            f"Sharpe={sm['sharpe']:.2f}  Calmar={calmar:.2f}  "
            f"Time={time_in:.0%}"
        )

    # ── Print comparison table
    df = pd.DataFrame(results)

    print("\n" + "=" * 90)
    print("  TREND FILTER RESEARCH — ASCENT (MOMENTUM) STRATEGY")
    print("  Universe: NSE 500 ex Nifty 50 | Period: 2010–2026 | Top 15 EW | Monthly rebalance")
    print("=" * 90)

    # Format for display
    fmt = df.copy()
    fmt["CAGR"] = fmt["CAGR"].apply(lambda x: f"{x:.1%}")
    fmt["Max DD"] = fmt["Max DD"].apply(lambda x: f"{x:.1%}")
    fmt["Sharpe"] = fmt["Sharpe"].apply(lambda x: f"{x:.2f}")
    fmt["Sortino"] = fmt["Sortino"].apply(lambda x: f"{x:.2f}")
    fmt["Calmar"] = fmt["Calmar"].apply(lambda x: f"{x:.2f}")
    fmt["Vol"] = fmt["Vol"].apply(lambda x: f"{x:.1%}")
    fmt["Win Rate"] = fmt["Win Rate"].apply(lambda x: f"{x:.0%}")
    fmt["Time In Mkt"] = fmt["Time In Mkt"].apply(lambda x: f"{x:.0%}")
    fmt["Final Eq"] = fmt["Final Eq"].apply(lambda x: f"{x:.1f}x")

    print()
    print(fmt.to_string(index=False))

    # ── Key takeaways
    baseline = results[0]
    print("\n" + "-" * 90)
    print("  KEY FINDINGS")
    print("-" * 90)

    best_sharpe = max(results, key=lambda x: x["Sharpe"])
    best_calmar = max(results, key=lambda x: x["Calmar"])
    best_cagr = max(results, key=lambda x: x["CAGR"])
    least_dd = max(results, key=lambda x: x["Max DD"])  # max DD is negative, so max = least severe

    print(f"  Best CAGR:    {best_cagr['Filter']} ({best_cagr['CAGR']:.1%})")
    print(f"  Best Sharpe:  {best_sharpe['Filter']} ({best_sharpe['Sharpe']:.2f})")
    print(f"  Best Calmar:  {best_calmar['Filter']} ({best_calmar['Calmar']:.2f})")
    print(f"  Least DD:     {least_dd['Filter']} ({least_dd['Max DD']:.1%})")

    # Check if any filter improves Sharpe without losing >5pp CAGR
    print()
    for r in results[1:]:
        cagr_loss = baseline["CAGR"] - r["CAGR"]
        sharpe_gain = r["Sharpe"] - baseline["Sharpe"]
        dd_improvement = r["Max DD"] - baseline["Max DD"]  # less negative = better
        verdict = "WORTH IT" if sharpe_gain > 0 and cagr_loss < 0.05 else "NOT WORTH IT"
        print(
            f"  {r['Filter']:<25s}  CAGR {'-' if cagr_loss > 0 else '+'}{abs(cagr_loss):.1%}  "
            f"Sharpe {'+' if sharpe_gain > 0 else ''}{sharpe_gain:.2f}  "
            f"DD {'+' if dd_improvement > 0 else ''}{dd_improvement:.1%}  "
            f"→ {verdict}"
        )

    print()


if __name__ == "__main__":
    main()
