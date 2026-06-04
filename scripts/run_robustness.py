"""Robustness tests for the smallcap momentum strategy.

Runs 5 variants of the same strategy, same data, and produces a side-by-side
comparison. This is how we stress-test the backtest before trusting it.

Variants:
  1. Baseline           — top_n=15, trend filter on, 2010→today
  2. No trend filter    — top_n=15, filter off (should show COVID drawdown)
  3. Top 10             — tighter concentration (stability check)
  4. Top 20             — looser concentration (stability check)
  5. OOS split (≤2020)  — backtest ending 2020-12-31 (pre-2021 regime check)

Usage:
    python scripts/run_robustness.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Make src/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from tabulate import tabulate

from trading.backtest.costs import CostConfig
from trading.backtest.engine import run_backtest
from trading.config import OUTPUTS_DIR, ensure_dirs, load_strategy_config
from trading.data.loader import fetch_benchmark, fetch_many, to_price_panel
from trading.data.universe import smallcap_universe
from trading.portfolio.constructor import resample_to_rebalance_dates, top_n_equal_weight
from trading.reporting.metrics import summary
from trading.signals.momentum import absolute_trend_filter, momentum_n_m
from trading.utils.logging import setup_logging

log = setup_logging("robustness")


def run_variant(
    name: str,
    prices: pd.DataFrame,
    bench_price: pd.Series | None,
    *,
    lookback_months: int = 12,
    skip_months: int = 1,
    top_n: int = 15,
    trend_filter_enabled: bool = True,
    sma_window: int = 200,
    end_date: str | None = None,
    rebalance_freq: str = "ME",
    risk_free_rate: float = 0.06,
) -> dict:
    """Run a single variant and return its summary metrics + variant name."""
    log.info(f"Running variant: {name}")

    # Optional temporal truncation for OOS test
    if end_date:
        prices = prices.loc[:end_date]
        if bench_price is not None:
            bench_price = bench_price.loc[:end_date]

    scores = momentum_n_m(prices, lookback_months, skip_months)

    if trend_filter_enabled and bench_price is not None:
        risk_on = absolute_trend_filter(bench_price, sma_window)
    else:
        risk_on = None

    daily_w = top_n_equal_weight(scores, top_n=top_n, risk_on=risk_on)
    rebal_w = resample_to_rebalance_dates(daily_w, frequency=rebalance_freq)

    result = run_backtest(prices, rebal_w, cost_config=CostConfig())
    sm = summary(result.equity_curve, result.returns, risk_free_rate=risk_free_rate)
    sm["variant"] = name
    sm["n_rebalances"] = len(result.rebalance_dates)
    sm["avg_turnover"] = float(result.turnover.mean()) if not result.turnover.empty else 0.0
    return sm


def format_table(rows: list[dict]) -> pd.DataFrame:
    """Build a display-ready DataFrame from variant summary dicts."""
    df = pd.DataFrame(rows)
    col_order = [
        "variant",
        "cagr",
        "annual_vol",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
        "win_rate_monthly",
        "final_equity",
        "avg_turnover",
        "n_rebalances",
    ]
    df = df[[c for c in col_order if c in df.columns]]
    return df


def pretty_print(df: pd.DataFrame) -> None:
    """Print the comparison table with formatted values."""
    display = df.copy()
    pct_cols = ["cagr", "annual_vol", "max_drawdown", "win_rate_monthly", "avg_turnover"]
    num_cols = ["sharpe", "sortino", "calmar", "final_equity"]
    int_cols = ["n_rebalances"]

    for c in pct_cols:
        if c in display.columns:
            display[c] = display[c].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "")
    for c in num_cols:
        if c in display.columns:
            display[c] = display[c].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    for c in int_cols:
        if c in display.columns:
            display[c] = display[c].apply(lambda x: f"{int(x)}" if pd.notna(x) else "")

    print()
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=False))
    print()


def interpret(df: pd.DataFrame) -> None:
    """Auto-commentary on the robustness results."""
    rows = {r["variant"]: r for _, r in df.iterrows()}
    print("=" * 60)
    print("INTERPRETATION")
    print("=" * 60)

    base = rows.get("Baseline")
    no_filter = rows.get("No trend filter")
    top10 = rows.get("Top 10")
    top20 = rows.get("Top 20")
    oos = rows.get("OOS (≤ 2020-12-31)")

    # Trend filter contribution
    if base is not None and no_filter is not None:
        dd_delta = no_filter["max_drawdown"] - base["max_drawdown"]
        cagr_delta = base["cagr"] - no_filter["cagr"]
        if dd_delta < -0.05:
            print(f"✓ Trend filter is doing real work — removes {abs(dd_delta):.1%} of drawdown.")
            if cagr_delta < 0:
                print(f"  Costs {abs(cagr_delta):.1%} CAGR but reduces DD meaningfully. Worth it.")
            else:
                print(f"  AND adds {cagr_delta:.1%} CAGR. Unusual — expected filter to cost a little.")
        else:
            print(f"⚠ Trend filter impact is small (DD only {abs(dd_delta):.1%} different). Consider removing.")

    # Parameter stability
    if base is not None and top10 is not None and top20 is not None:
        cagrs = [base["cagr"], top10["cagr"], top20["cagr"]]
        spread = max(cagrs) - min(cagrs)
        if spread < 0.06:
            print(f"✓ Parameter stable across top_n ∈ {{10, 15, 20}} — CAGR spread {spread:.1%}.")
        else:
            print(f"⚠ Parameter sensitive — CAGR spread {spread:.1%} across top_n values. Possibly overfit.")

    # OOS degradation
    if base is not None and oos is not None:
        oos_cagr = oos["cagr"]
        full_cagr = base["cagr"]
        if oos_cagr > full_cagr * 0.7:
            print(f"✓ Pre-2021 period stands on its own — OOS CAGR {oos_cagr:.1%} vs full {full_cagr:.1%}.")
        else:
            print(f"⚠ Much of the edge comes from post-2020 window — OOS CAGR {oos_cagr:.1%} vs full {full_cagr:.1%}.")
            print("  Strategy may be riding a regime rather than exploiting a durable anomaly.")

    print("=" * 60)


def main() -> None:
    ensure_dirs()

    log.info("Loading base config...")
    cfg = load_strategy_config("smallcap_momentum_v1.yaml")

    log.info("Loading universe and price history (uses cache if available)...")
    tickers = smallcap_universe()
    price_dict = fetch_many(
        tickers,
        start=cfg["data"]["start"],
        end=cfg["data"].get("end"),
        force_refresh=False,
    )
    prices = to_price_panel(price_dict, field="adj_close")
    log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

    bench_df = fetch_benchmark(cfg["benchmark"]["symbol"], start=cfg["data"]["start"])
    bench_price = bench_df["adj_close"] if not bench_df.empty else None

    # ---- Run variants ----
    results = [
        run_variant("Baseline", prices, bench_price, top_n=15, trend_filter_enabled=True),
        run_variant("No trend filter", prices, bench_price, top_n=15, trend_filter_enabled=False),
        run_variant("Top 10", prices, bench_price, top_n=10, trend_filter_enabled=True),
        run_variant("Top 20", prices, bench_price, top_n=20, trend_filter_enabled=True),
        run_variant(
            "OOS (≤ 2020-12-31)",
            prices,
            bench_price,
            top_n=15,
            trend_filter_enabled=True,
            end_date="2020-12-31",
        ),
    ]

    df = format_table(results)
    pretty_print(df)
    interpret(df)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUTS_DIR / f"robustness_comparison_{ts}.csv"
    df.to_csv(out_path, index=False)
    log.info(f"Comparison table saved: {out_path}")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
