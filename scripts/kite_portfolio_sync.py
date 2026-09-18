"""Sync actual portfolio from Kite and backfill equity.csv.

Run this after any messy rebalance (duplicate orders, failed retries, etc.)
to re-establish ground truth from what Kite actually holds.

What it does:
  1. Logs into Kite (interactive browser)
  2. Fetches actual current holdings
  3. Saves kite_snapshot.json to the strategy folder
  4. Immediately backfills equity.csv from the last marked date to today

After running this once, the daily GH Actions cron takes over automatically.

Usage:
    python scripts/kite_portfolio_sync.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.execution import kite as kite_module
from trading.utils.logging import setup_logging

log = setup_logging("kite_sync")

STRATEGY = "smallcap_momentum_v2_live"
STRATEGY_DIR = DATA_DIR / "live" / STRATEGY
SNAP_PATH = STRATEGY_DIR / "kite_snapshot.json"


def fetch_and_save_snapshot() -> dict:
    """Log into Kite, fetch holdings, save snapshot. Returns holdings dict."""
    log.info("Logging into Kite...")
    kite = kite_module.login()

    raw = kite.holdings()
    holdings = {}
    for h in raw:
        if h["quantity"] > 0:
            qty = h["quantity"]
            avg = h["average_price"]
            holdings[h["tradingsymbol"]] = {
                "quantity": qty,
                "average_price": round(avg, 2),
                "cost_basis": round(qty * avg, 2),
            }

    snap = {
        "date": date.today().isoformat(),
        "source": "kite_holdings_api",
        "holdings": holdings,
    }

    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAP_PATH, "w") as f:
        json.dump(snap, f, indent=2)

    log.info(f"Saved snapshot: {len(holdings)} positions as of {snap['date']}")
    return snap


def print_holdings(snap: dict) -> None:
    holdings = snap["holdings"]
    if not holdings:
        print("No holdings.")
        return

    print(f"\nKite holdings as of {snap['date']}")
    print(f"{'Symbol':<15} {'Qty':>6} {'Avg Price':>11} {'Cost Basis':>12}")
    print("-" * 47)

    total_cost = 0.0
    for sym, h in sorted(holdings.items()):
        print(f"{sym:<15} {h['quantity']:>6} {h['average_price']:>11.2f} {h['cost_basis']:>12.2f}")
        total_cost += h["cost_basis"]

    print("-" * 47)
    print(f"{'TOTAL':<15} {len(holdings):>6} {'':>11} {total_cost:>12.2f}")
    print()


def main():
    snap = fetch_and_save_snapshot()
    print_holdings(snap)

    # Trigger daily mark to backfill equity.csv from last mark to today
    log.info("Triggering live mark backfill...")
    import importlib.util
    mark_script = ROOT / "scripts" / "daily_live_mark.py"
    spec = importlib.util.spec_from_file_location("daily_live_mark", mark_script)
    mark_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mark_mod)
    mark_mod.mark_live_strategy(STRATEGY)

    log.info("Done. equity.csv is now up to date.")


if __name__ == "__main__":
    main()
