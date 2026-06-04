"""Daily mark-to-market for paper trading strategies.

Updates equity based on actual price changes since last rebalance,
WITHOUT changing positions. Run this daily via cron to build the
equity curve needed for the 90-day graduation gate.

Usage:
    python scripts/daily_mark.py
    python scripts/daily_mark.py --strategy smallcap_momentum_v2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.data.loader import fetch_many, to_price_panel
from trading.utils.logging import setup_logging

log = setup_logging("daily_mark")

PAPER_DIR = DATA_DIR / "paper"


def find_strategies() -> list[str]:
    """Find all paper strategies with state.json."""
    if not PAPER_DIR.exists():
        return []
    return [
        p.name for p in PAPER_DIR.iterdir()
        if p.is_dir() and (p / "state.json").exists()
    ]


def mark_to_market(strategy: str) -> None:
    """Update equity for a paper strategy using today's prices."""
    state_path = PAPER_DIR / strategy / "state.json"
    equity_path = PAPER_DIR / strategy / "equity.csv"

    with open(state_path) as f:
        state = json.load(f)

    holdings = state.get("holdings", {})
    if not holdings:
        log.info(f"{strategy}: no holdings, skipping")
        return

    last_rebalance = state.get("last_rebalance")
    if not last_rebalance:
        log.info(f"{strategy}: never rebalanced, skipping")
        return

    # Check if we already marked today
    today_str = datetime.now().strftime("%Y-%m-%d")
    if equity_path.exists():
        eq_df = pd.read_csv(equity_path)
        if today_str in eq_df["date"].values:
            log.info(f"{strategy}: already marked for {today_str}, skipping")
            return

    # Fetch recent prices for held tickers
    tickers = list(holdings.keys())
    start = (pd.Timestamp(last_rebalance) - pd.DateOffset(days=5)).strftime("%Y-%m-%d")

    log.info(f"{strategy}: fetching prices for {len(tickers)} holdings...")
    price_dict = fetch_many(tickers, start=start, force_refresh=True)
    prices = to_price_panel(price_dict, field="adj_close")

    # Compute drift from last rebalance
    last_dt = pd.Timestamp(last_rebalance)
    recent = prices.loc[prices.index > last_dt]

    if recent.empty:
        log.info(f"{strategy}: no new price data since {last_rebalance}")
        # Still log today's equity (unchanged)
        equity = state["equity"]
    else:
        held = [t for t in holdings if t in prices.columns]
        missing = [t for t in holdings if t not in prices.columns]
        if missing:
            log.warning(f"{strategy}: no price data for {missing}")

        if not held:
            log.warning(f"{strategy}: no price data for any holdings")
            equity = state["equity"]
        else:
            rets = prices[held].pct_change().fillna(0.0)
            drift_rets = rets.loc[rets.index > last_dt]

            equity = state["equity"]
            for dt in drift_rets.index:
                daily_port_ret = sum(
                    holdings.get(t, 0.0) * drift_rets.loc[dt, t]
                    for t in held
                )
                equity *= (1.0 + daily_port_ret)

    # Append to equity.csv
    row = pd.DataFrame([{
        "date": today_str,
        "equity": round(equity, 10),
        "n_positions": len(holdings),
        "cash_weight": state.get("cash_weight", 0),
    }])
    if equity_path.exists():
        row.to_csv(equity_path, mode="a", header=False, index=False)
    else:
        row.to_csv(equity_path, index=False)

    pct_change = (equity / state["equity"] - 1) * 100
    log.info(
        f"{strategy}: equity {state['equity']:.6f} -> {equity:.6f} "
        f"({pct_change:+.2f}%) | {len(holdings)} positions | marked {today_str}"
    )


def main():
    parser = argparse.ArgumentParser(description="Daily paper trading mark-to-market")
    parser.add_argument("--strategy", "-s", help="Specific strategy (default: all)")
    args = parser.parse_args()

    if args.strategy:
        strategies = [args.strategy]
    else:
        strategies = find_strategies()

    if not strategies:
        log.info("No paper strategies found.")
        return

    log.info(f"Marking {len(strategies)} strategy(ies) to market...")
    for s in strategies:
        try:
            mark_to_market(s)
        except Exception as e:
            log.error(f"{s}: mark-to-market failed: {e}")

    log.info("Done.")


if __name__ == "__main__":
    main()
