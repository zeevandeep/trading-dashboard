"""Daily mark-to-market for live trading portfolio.

Reads the order log to determine current holdings and quantities,
fetches prices via yfinance, computes portfolio value, and
appends to data/live/<strategy>/equity.csv.

Automatically detects and backfills any missing trading days since
the last mark, so gaps from failed runs are self-healing.

Usage:
    python scripts/daily_live_mark.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
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
            if holdings[sym]["quantity"] > 0:
                avg_cost = holdings[sym]["cost_basis"] / holdings[sym]["quantity"]
                holdings[sym]["cost_basis"] -= avg_cost * qty
            holdings[sym]["quantity"] -= qty

    return {s: h for s, h in holdings.items() if h["quantity"] > 0}


def fetch_historical_closes(symbols: list[str], start: str) -> pd.DataFrame:
    """Fetch daily close prices from yfinance for multiple symbols.

    Returns DataFrame indexed by date with columns = symbols (internal names).
    """
    yf_map = {}
    for s in symbols:
        yf_map[s] = f"{s}.NS" if not (s.endswith(".NS") or s.endswith(".BO")) else s

    yf_tickers = list(yf_map.values())
    reverse_map = {v: k for k, v in yf_map.items()}

    try:
        data = yf.download(yf_tickers, start=start, progress=False, threads=True)
        if data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]]
            close.columns = yf_tickers

        close = close.rename(columns=reverse_map)
        return close
    except Exception as e:
        log.warning(f"yfinance historical fetch failed: {e}")
        return pd.DataFrame()


def find_missing_dates(equity_path: Path, first_order_date: str) -> list[str]:
    """Find trading days with no mark since the last recorded mark.

    If no equity file exists, backfills from the first order date.
    """
    today = datetime.now().date()

    if equity_path.exists():
        eq_df = pd.read_csv(equity_path)
        if not eq_df.empty:
            marked_dates = set(eq_df["date"].values)
            last_marked = pd.Timestamp(eq_df["date"].iloc[-1]).date()
        else:
            marked_dates = set()
            last_marked = pd.Timestamp(first_order_date).date() - timedelta(days=1)
    else:
        marked_dates = set()
        last_marked = pd.Timestamp(first_order_date).date() - timedelta(days=1)

    # Generate all business days from day after last mark to today
    bdays = pd.bdate_range(start=last_marked + timedelta(days=1), end=today)
    missing = [d.strftime("%Y-%m-%d") for d in bdays if d.strftime("%Y-%m-%d") not in marked_dates]

    return missing


def mark_single_day(
    strategy: str,
    holdings: dict[str, dict],
    close_prices: dict[str, float],
    mark_date: str,
    equity_path: Path,
    positions_path: Path,
) -> bool:
    """Write a single day's mark to equity.csv and positions.csv.

    Returns True if successful.
    """
    total_cost = sum(h["cost_basis"] for h in holdings.values())

    current_value = 0.0
    position_details = []
    for sym, info in holdings.items():
        qty = info["quantity"]
        cost = info["cost_basis"]
        price = close_prices.get(sym, 0)
        if price <= 0:
            return False
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
        "date": mark_date,
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

    # Append to positions.csv
    pos_df = pd.DataFrame(position_details)
    pos_df["date"] = mark_date
    if positions_path.exists():
        pos_df.to_csv(positions_path, mode="a", header=False, index=False)
    else:
        pos_df.to_csv(positions_path, index=False)

    return True


def mark_live_strategy(strategy: str) -> None:
    strategy_dir = LIVE_DIR / strategy
    orders_path = strategy_dir / "orders.csv"
    equity_path = strategy_dir / "equity.csv"
    positions_path = strategy_dir / "positions.csv"

    orders_df = pd.read_csv(orders_path)
    if orders_df.empty:
        log.info(f"{strategy}: no orders, skipping")
        return

    holdings = compute_holdings(orders_df)
    if not holdings:
        log.info(f"{strategy}: no active holdings, skipping")
        return

    # Find earliest order date for backfill boundary
    first_order_date = orders_df["timestamp"].min()[:10]

    # Find all missing trading days
    missing = find_missing_dates(equity_path, first_order_date)
    if not missing:
        log.info(f"{strategy}: all dates up to today already marked")
        return

    symbols = list(holdings.keys())
    total_cost = sum(h["cost_basis"] for h in holdings.values())

    # Fetch historical prices covering the entire gap
    fetch_start = (pd.Timestamp(missing[0]) - pd.DateOffset(days=5)).strftime("%Y-%m-%d")
    log.info(f"{strategy}: fetching prices for {len(symbols)} holdings from {fetch_start}...")
    hist = fetch_historical_closes(symbols, start=fetch_start)

    if hist.empty:
        log.warning(f"{strategy}: could not fetch historical prices")
        return

    # Mark each missing date
    marked = 0
    for date_str in missing:
        dt = pd.Timestamp(date_str)
        if dt not in hist.index:
            # Not a trading day (holiday), skip
            continue

        close_prices = {}
        skip = False
        for sym in symbols:
            if sym in hist.columns and pd.notna(hist.loc[dt, sym]):
                close_prices[sym] = float(hist.loc[dt, sym])
            else:
                skip = True
                break

        if skip:
            log.warning(f"{strategy}: missing price data for {date_str}, skipping")
            continue

        if mark_single_day(strategy, holdings, close_prices, date_str, equity_path, positions_path):
            marked += 1

    if marked > 0:
        # Log summary for the latest mark
        latest_date = missing[-1] if missing else "?"
        current_value = sum(
            holdings[s]["quantity"] * hist[s].loc[:pd.Timestamp(latest_date)].dropna().iloc[-1]
            for s in symbols if s in hist.columns
        ) if not hist.empty else 0
        total_pnl = current_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        log.info(
            f"{strategy}: marked {marked} day(s) "
            f"({'backfilled' if marked > 1 else 'current'}) | "
            f"invested Rs.{total_cost:,.0f} -> value Rs.{current_value:,.0f} "
            f"(P&L {total_pnl:+,.0f} / {total_pnl_pct:+.2f}%) | "
            f"{len(holdings)} positions"
        )
    else:
        log.info(f"{strategy}: no trading days to mark (holidays?)")


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
            raise  # Don't silently swallow — let the workflow see the failure

    log.info("Done.")


if __name__ == "__main__":
    main()
