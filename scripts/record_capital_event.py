"""Record a capital addition or withdrawal and recompute equity.csv.

capital_events.csv is the source of truth for how much external cash has been
deployed into (or withdrawn from) each live strategy. The daily mark script
reads it to set the correct `invested`, P&L, and NAV values.

Run this script whenever you add or remove money from a live strategy.

Usage:
    # Record a deposit and fix equity.csv from that date onward
    python scripts/record_capital_event.py \\
        --strategy smallcap_momentum_v2_live \\
        --date 2026-08-26 \\
        --amount 72456.47 \\
        --note "1L add-on" \\
        --recompute

    # Record a withdrawal (use negative amount)
    python scripts/record_capital_event.py \\
        --strategy smallcap_momentum_v2_live \\
        --date 2026-11-01 \\
        --amount -50000 \\
        --note "Partial withdrawal" \\
        --recompute

    # List all capital events for a strategy
    python scripts/record_capital_event.py \\
        --strategy smallcap_momentum_v2_live \\
        --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.utils.logging import setup_logging

log = setup_logging("record_capital")

LIVE_DIR = DATA_DIR / "live"


def list_events(strategy: str) -> None:
    events_path = LIVE_DIR / strategy / "capital_events.csv"
    if not events_path.exists():
        print(f"No capital_events.csv found for {strategy}.")
        return

    df = pd.read_csv(events_path)
    df = df.sort_values("date").reset_index(drop=True)
    total = df["amount"].sum()

    print(f"\nCapital events for {strategy}")
    print(f"{'Date':<14} {'Amount':>12}  Note")
    print("-" * 55)
    running = 0.0
    for _, row in df.iterrows():
        running += row["amount"]
        direction = "+" if row["amount"] >= 0 else ""
        print(f"{row['date']:<14} {direction}{row['amount']:>11,.2f}  {row.get('note', '')}")
    print("-" * 55)
    print(f"{'Total deployed':<14} {total:>12,.2f}")
    print()


def record_event(strategy: str, date: str, amount: float, note: str) -> None:
    events_path = LIVE_DIR / strategy / "capital_events.csv"

    if events_path.exists():
        df = pd.read_csv(events_path)
        # Check for duplicate on same date with same amount
        duplicate = df[(df["date"] == date) & (df["amount"] == amount)]
        if not duplicate.empty:
            print(f"Event already recorded for {date} / Rs.{amount:,.2f} — skipping.")
            return
    else:
        df = pd.DataFrame(columns=["date", "amount", "note"])

    new_row = pd.DataFrame([{"date": date, "amount": amount, "note": note}])
    df = pd.concat([df, new_row], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(events_path, index=False)
    direction = "Deposit" if amount >= 0 else "Withdrawal"
    log.info(f"{direction} of Rs.{abs(amount):,.2f} recorded on {date} for {strategy}")


def truncate_equity_from(strategy: str, date: str) -> None:
    """Delete all equity.csv and positions.csv rows on or after `date`."""
    strategy_dir = LIVE_DIR / strategy

    for fname in ("equity.csv", "positions.csv"):
        fpath = strategy_dir / fname
        if not fpath.exists():
            continue
        df = pd.read_csv(fpath)
        before = df[df["date"] < date]
        dropped = len(df) - len(before)
        before.to_csv(fpath, index=False)
        log.info(f"Truncated {fname}: removed {dropped} row(s) from {date} onwards")


def recompute_from(strategy: str, date: str) -> None:
    """Re-run daily mark for all trading days from `date` to today."""
    import importlib.util
    mark_script = ROOT / "scripts" / "daily_live_mark.py"
    spec = importlib.util.spec_from_file_location("daily_live_mark", mark_script)
    mark_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mark_mod)
    log.info(f"Recomputing equity.csv for {strategy} from {date}...")
    mark_mod.mark_live_strategy(strategy)
    log.info("Recompute complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a capital event and optionally recompute equity.csv")
    parser.add_argument("--strategy", required=True, help="Strategy name (e.g. smallcap_momentum_v2_live)")
    parser.add_argument("--date", help="Event date YYYY-MM-DD")
    parser.add_argument("--amount", type=float, help="Amount in INR (positive = deposit, negative = withdrawal)")
    parser.add_argument("--note", default="", help="Human-readable description")
    parser.add_argument("--recompute", action="store_true",
                        help="Truncate equity.csv from event date and recompute")
    parser.add_argument("--list", action="store_true", help="List all capital events for the strategy")
    args = parser.parse_args()

    if args.list:
        list_events(args.strategy)
        return

    if not args.date or args.amount is None:
        parser.error("--date and --amount are required unless using --list")

    strategy_dir = LIVE_DIR / args.strategy
    if not strategy_dir.exists():
        log.error(f"Strategy directory not found: {strategy_dir}")
        sys.exit(1)

    record_event(args.strategy, args.date, args.amount, args.note)
    list_events(args.strategy)

    if args.recompute:
        truncate_equity_from(args.strategy, args.date)
        recompute_from(args.strategy, args.date)
        print(f"\nEquity recomputed from {args.date}. Run daily_live_mark.py to verify.")


if __name__ == "__main__":
    main()
