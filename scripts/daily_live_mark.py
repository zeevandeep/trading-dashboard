"""Daily mark-to-market for live trading portfolio.

Reads the order log to determine current holdings and quantities,
fetches live prices via yfinance, computes portfolio value, and
appends to data/live/<strategy>/equity.csv.

Usage:
    python scripts/daily_live_mark.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.execution.kite import _get_ltp_yfinance
from trading.utils.logging import setup_logging

log = setup_logging("live_mark")

LIVE_DIR = DATA_DIR / "live"


def find_live_strategies() -> list[str]:
    if not LIVE_DIR.exists():
        return []
    return [
        p.name for p in LIVE_DIR.iterdir()
        if p.is_dir() and (p / "orders.csv").exists()
    ]


def compute_holdings(orders_df: pd.DataFrame) -> dict[str, dict]:
    """Compute current holdings from order log.

    Returns {symbol: {quantity, cost_basis}} by netting buys and sells.
    """
    holdings = {}
    placed = orders_df[orders_df["status"] == "placed"]

    for _, row in placed.iterrows():
        sym = row["symbol"]
        qty = int(row["quantity"])
        value = float(row["estimated_value"])

        if sym not in holdings:
            holdings[sym] = {"quantity": 0, "cost_basis": 0.0}

        if row["side"] == "BUY":
            holdings[sym]["cost_basis"] += value
            holdings[sym]["quantity"] += qty
        elif row["side"] == "SELL":
            # Reduce cost basis proportionally
            if holdings[sym]["quantity"] > 0:
                avg_cost = holdings[sym]["cost_basis"] / holdings[sym]["quantity"]
                holdings[sym]["cost_basis"] -= avg_cost * qty
            holdings[sym]["quantity"] -= qty

    # Remove zero/negative positions
    return {s: h for s, h in holdings.items() if h["quantity"] > 0}


def mark_live_strategy(strategy: str) -> None:
    strategy_dir = LIVE_DIR / strategy
    orders_path = strategy_dir / "orders.csv"
    equity_path = strategy_dir / "equity.csv"

    orders_df = pd.read_csv(orders_path)
    if orders_df.empty:
        log.info(f"{strategy}: no orders, skipping")
        return

    # Check if already marked today
    today_str = datetime.now().strftime("%Y-%m-%d")
    if equity_path.exists():
        eq_df = pd.read_csv(equity_path)
        if today_str in eq_df["date"].values:
            log.info(f"{strategy}: already marked for {today_str}, skipping")
            return

    # Compute current holdings from order log
    holdings = compute_holdings(orders_df)
    if not holdings:
        log.info(f"{strategy}: no active holdings, skipping")
        return

    symbols = list(holdings.keys())
    total_cost = sum(h["cost_basis"] for h in holdings.values())

    # Fetch current prices
    log.info(f"{strategy}: fetching prices for {len(symbols)} holdings...")
    prices = _get_ltp_yfinance(symbols)

    if not prices:
        log.warning(f"{strategy}: could not fetch prices")
        return

    # Compute current portfolio value
    current_value = 0.0
    position_details = []
    for sym, info in holdings.items():
        qty = info["quantity"]
        cost = info["cost_basis"]
        price = prices.get(sym, 0)
        mkt_value = qty * price
        pnl = mkt_value - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        current_value += mkt_value
        position_details.append({
            "symbol": sym,
            "quantity": qty,
            "cost_basis": round(cost, 2),
            "price": round(price, 2),
            "market_value": round(mkt_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    total_pnl = current_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    # Append to equity.csv
    row = pd.DataFrame([{
        "date": today_str,
        "invested": round(total_cost, 2),
        "market_value": round(current_value, 2),
        "pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl_pct, 2),
        "n_positions": len(holdings),
    }])
    if equity_path.exists():
        row.to_csv(equity_path, mode="a", header=False, index=False)
    else:
        row.to_csv(equity_path, index=False)

    # Save daily positions snapshot
    positions_path = strategy_dir / "positions.csv"
    pos_df = pd.DataFrame(position_details)
    pos_df["date"] = today_str
    if positions_path.exists():
        pos_df.to_csv(positions_path, mode="a", header=False, index=False)
    else:
        pos_df.to_csv(positions_path, index=False)

    log.info(
        f"{strategy}: invested Rs.{total_cost:,.0f} -> "
        f"value Rs.{current_value:,.0f} "
        f"(P&L {total_pnl:+,.0f} / {total_pnl_pct:+.2f}%) | "
        f"{len(holdings)} positions | marked {today_str}"
    )

    # Print position details
    for p in position_details:
        sign = "+" if p["pnl"] >= 0 else ""
        log.info(
            f"  {p['symbol']:>12s}  qty={p['quantity']:>4d}  "
            f"cost={p['cost_basis']:>8,.0f}  mkt={p['market_value']:>8,.0f}  "
            f"P&L={sign}{p['pnl']:,.0f} ({sign}{p['pnl_pct']:.1f}%)"
        )


def main():
    strategies = find_live_strategies()
    if not strategies:
        log.info("No live strategies found.")
        return

    log.info(f"Marking {len(strategies)} live strategy(ies)...")
    for s in strategies:
        try:
            mark_live_strategy(s)
        except Exception as e:
            log.error(f"{s}: live mark failed: {e}")

    log.info("Done.")


if __name__ == "__main__":
    main()
