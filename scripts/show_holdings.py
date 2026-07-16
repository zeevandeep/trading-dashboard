"""Show current AngelOne holdings for Bedrock strategy."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.execution.angel import login, get_holdings


def main():
    obj = login()
    holdings = get_holdings(obj)

    if not holdings:
        print("No holdings found.")
        return

    total_invested = 0.0
    total_current = 0.0

    print(f"\n{'Symbol':<15} {'Qty':>5} {'Avg Price':>10} {'LTP':>10} {'P&L':>10} {'P&L %':>8}")
    print("-" * 62)

    for sym, h in sorted(holdings.items()):
        qty = h["quantity"]
        avg = h["average_price"]
        ltp = h["last_price"]
        pnl = h["pnl"]
        invested = qty * avg
        current = qty * ltp
        pnl_pct = (pnl / invested * 100) if invested else 0

        total_invested += invested
        total_current += current

        print(f"{sym:<15} {qty:>5} {avg:>10.2f} {ltp:>10.2f} {pnl:>+10.2f} {pnl_pct:>+7.2f}%")

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0

    print("-" * 62)
    print(f"{'TOTAL':<15} {'':<5} {total_invested:>10.0f} {total_current:>10.0f} {total_pnl:>+10.2f} {total_pnl_pct:>+7.2f}%")
    print(f"\nPositions: {len(holdings)}")


if __name__ == "__main__":
    main()
