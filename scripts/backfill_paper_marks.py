"""Backfill missing daily equity marks for paper trading strategies.

Fills in all missing trading days between the last recorded equity date
and today. Uses the same drift logic as daily_mark.py but iterates over
each missing day.

Usage:
    python scripts/backfill_paper_marks.py
"""

from __future__ import annotations

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

log = setup_logging("backfill_mark")

PAPER_DIR = DATA_DIR / "paper"


def backfill_strategy(strategy: str, prices: pd.DataFrame | None = None) -> None:
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

    # Load existing equity entries
    existing_dates = set()
    if equity_path.exists():
        eq_df = pd.read_csv(equity_path)
        existing_dates = set(eq_df["date"].values)
    else:
        eq_df = pd.DataFrame()

    # Fetch prices if not provided
    tickers = list(holdings.keys())
    if prices is None:
        start = (pd.Timestamp(last_rebalance) - pd.DateOffset(days=5)).strftime("%Y-%m-%d")
        log.info(f"{strategy}: fetching prices for {len(tickers)} holdings from {start}...")
        price_dict = fetch_many(tickers, start=start, force_refresh=True)
        prices = to_price_panel(price_dict, field="adj_close")

    # Get the base equity from rebalance
    base_equity = state["equity"]
    rebal_dt = pd.Timestamp(last_rebalance)

    # Compute daily returns for held tickers
    held = [t for t in holdings if t in prices.columns]
    missing = [t for t in holdings if t not in prices.columns]
    if missing:
        log.warning(f"{strategy}: no price data for {missing}")
    if not held:
        log.warning(f"{strategy}: no price data for any holdings, skipping")
        return

    rets = prices[held].pct_change().fillna(0.0)
    drift_rets = rets.loc[rets.index > rebal_dt]

    if drift_rets.empty:
        log.info(f"{strategy}: no trading days since rebalance {last_rebalance}")
        return

    # Walk through each trading day, computing cumulative equity
    today_str = datetime.now().strftime("%Y-%m-%d")
    equity = base_equity
    new_rows = []

    for dt in drift_rets.index:
        daily_port_ret = sum(
            holdings.get(t, 0.0) * drift_rets.loc[dt, t]
            for t in held
        )
        equity *= (1.0 + daily_port_ret)

        dt_str = dt.strftime("%Y-%m-%d")
        if dt_str not in existing_dates:
            new_rows.append({
                "date": dt_str,
                "equity": round(equity, 10),
                "n_positions": len(holdings),
                "cash_weight": state.get("cash_weight", 0),
            })

    if not new_rows:
        log.info(f"{strategy}: no missing days to backfill")
        return

    # Append new rows
    new_df = pd.DataFrame(new_rows)
    if equity_path.exists():
        # Read existing, append, sort, deduplicate, rewrite
        existing_df = pd.read_csv(equity_path)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"], keep="first")
        combined = combined.sort_values("date").reset_index(drop=True)
        combined.to_csv(equity_path, index=False)
    else:
        new_df.to_csv(equity_path, index=False)

    log.info(
        f"{strategy}: backfilled {len(new_rows)} days | "
        f"equity {base_equity:.6f} -> {equity:.6f} "
        f"({(equity / base_equity - 1) * 100:+.2f}%)"
    )


def main():
    strategies = [
        p.name for p in PAPER_DIR.iterdir()
        if p.is_dir() and (p / "state.json").exists()
    ]

    if not strategies:
        log.info("No paper strategies found.")
        return

    log.info(f"Backfilling {len(strategies)} strategy(ies)...")
    for s in strategies:
        try:
            backfill_strategy(s)
        except Exception as e:
            log.error(f"{s}: backfill failed: {e}", exc_info=True)

    log.info("Backfill complete.")


if __name__ == "__main__":
    main()
