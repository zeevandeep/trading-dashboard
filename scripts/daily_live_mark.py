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

import json
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


def load_kite_snapshot(strategy_dir: Path) -> dict | None:
    """Load Kite holdings snapshot if one exists."""
    snap_path = strategy_dir / "kite_snapshot.json"
    if not snap_path.exists():
        return None
    with open(snap_path) as f:
        return json.load(f)


def compute_holdings(
    orders_df: pd.DataFrame,
    as_of_date: str | None = None,
    kite_snapshot: dict | None = None,
) -> dict[str, dict]:
    """Compute holdings for a given date.

    Priority:
      1. If kite_snapshot exists and as_of_date >= snapshot date: use snapshot
         as the base, then apply any placed orders after the snapshot date.
      2. Otherwise: derive from orders.csv up to as_of_date.

    This handles messy rebalances (duplicate orders, retries) by anchoring to
    what Kite actually holds, as captured by kite_portfolio_sync.py.
    """
    if kite_snapshot and as_of_date and as_of_date >= kite_snapshot["date"]:
        # Start from snapshot
        holdings: dict[str, dict] = {
            sym: {"quantity": h["quantity"], "cost_basis": h["cost_basis"]}
            for sym, h in kite_snapshot["holdings"].items()
            if h["quantity"] > 0
        }
        # Apply orders placed strictly after the snapshot date
        post = orders_df[
            (orders_df["status"] == "placed")
            & (orders_df["timestamp"].str[:10] > kite_snapshot["date"])
            & (orders_df["timestamp"].str[:10] <= as_of_date)
        ].sort_values("timestamp")
        _apply_orders(post, holdings)
        return {s: h for s, h in holdings.items() if h["quantity"] > 0}

    # Derive from orders.csv only
    holdings = {}
    placed = orders_df[orders_df["status"] == "placed"].copy()
    if as_of_date:
        placed = placed[placed["timestamp"].str[:10] <= as_of_date]
    placed = placed.sort_values("timestamp")
    _apply_orders(placed, holdings)
    return {s: h for s, h in holdings.items() if h["quantity"] > 0}


def _apply_orders(orders: pd.DataFrame, holdings: dict) -> None:
    """Apply a set of orders onto a holdings dict in-place."""
    for _, row in orders.iterrows():
        sym = row["symbol"]
        qty = int(row["quantity"])
        value = float(row["estimated_value"]) if pd.notna(row.get("estimated_value")) else 0.0

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
    """Find all trading days with no mark, including gaps in the middle.

    Scans from the first order date to today and returns any business day
    that doesn't have a mark — both mid-history gaps and new dates.
    """
    today = datetime.now().date()
    start = pd.Timestamp(first_order_date).date()

    if equity_path.exists():
        eq_df = pd.read_csv(equity_path)
        marked_dates = set(eq_df["date"].values) if not eq_df.empty else set()
    else:
        marked_dates = set()

    # All business days from first order to today
    bdays = pd.bdate_range(start=start, end=today)
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

    # Compute NAV (time-weighted, unaffected by deposits/withdrawals)
    nav = 1.0
    if equity_path.exists():
        prev_eq = pd.read_csv(equity_path)
        if not prev_eq.empty:
            prev_row = prev_eq.iloc[-1]
            prev_nav = prev_row.get("nav", 1.0)
            prev_mv = prev_row["market_value"]
            prev_inv = prev_row["invested"]
            cash_flow = total_cost - prev_inv
            if abs(cash_flow) > 1:  # capital added/removed (rebalance day)
                adjusted_start = prev_mv + cash_flow
                daily_ret = (current_value / adjusted_start) - 1 if adjusted_start > 0 else 0
            else:
                daily_ret = (current_value / prev_mv) - 1 if prev_mv > 0 else 0
            nav = prev_nav * (1 + daily_ret)

    # Append to equity.csv
    row = pd.DataFrame([{
        "date": mark_date,
        "invested": round(total_cost, 2),
        "market_value": round(current_value, 2),
        "pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl_pct, 2),
        "n_positions": len(holdings),
        "nav": round(nav, 6),
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

    # Load Kite snapshot if available (ground truth for messy rebalances)
    kite_snapshot = load_kite_snapshot(strategy_dir)
    if kite_snapshot:
        log.info(f"{strategy}: using Kite snapshot from {kite_snapshot['date']} as holdings anchor")

    # Find earliest order date for backfill boundary
    first_order_date = orders_df["timestamp"].dropna().min()[:10]

    # Find all missing trading days
    missing = find_missing_dates(equity_path, first_order_date)
    if not missing:
        log.info(f"{strategy}: all dates up to today already marked")
        return

    # Collect all symbols we might need prices for
    # (union of orders-derived symbols and snapshot symbols)
    all_symbols: set[str] = set()
    snap_symbols = set(kite_snapshot["holdings"].keys()) if kite_snapshot else set()
    order_symbols = set(orders_df[orders_df["status"] == "placed"]["symbol"].tolist())
    all_symbols = snap_symbols | order_symbols

    # Fetch historical prices for the full gap
    fetch_start = (pd.Timestamp(missing[0]) - pd.DateOffset(days=5)).strftime("%Y-%m-%d")
    log.info(f"{strategy}: fetching prices for {len(all_symbols)} symbols from {fetch_start}...")
    hist = fetch_historical_closes(list(all_symbols), start=fetch_start)

    if hist.empty:
        log.warning(f"{strategy}: could not fetch historical prices")
        return

    # Mark each missing date
    marked = 0
    for date_str in missing:
        dt = pd.Timestamp(date_str)
        if dt not in hist.index:
            continue  # market holiday

        # Determine holdings for this specific date
        holdings = compute_holdings(orders_df, as_of_date=date_str, kite_snapshot=kite_snapshot)
        if not holdings:
            log.warning(f"{strategy}: no holdings computed for {date_str}, skipping")
            continue

        close_prices = {}
        skip = False
        for sym in holdings:
            if sym in hist.columns and pd.notna(hist.loc[dt, sym]):
                close_prices[sym] = float(hist.loc[dt, sym])
            else:
                log.warning(f"{strategy}: no price for {sym} on {date_str}, skipping day")
                skip = True
                break

        if skip:
            continue

        if mark_single_day(strategy, holdings, close_prices, date_str, equity_path, positions_path):
            marked += 1

    # Sort files by date after backfills
    if marked > 0:
        for fpath in [equity_path, positions_path]:
            if fpath.exists():
                df = pd.read_csv(fpath)
                subset = ["date"] if fpath == equity_path else ["date", "symbol"]
                df = df.sort_values("date").drop_duplicates(subset=subset)
                df.to_csv(fpath, index=False)

    if marked > 0:
        # Summary using latest date's holdings
        latest_holdings = compute_holdings(orders_df, kite_snapshot=kite_snapshot)
        total_cost = sum(h["cost_basis"] for h in latest_holdings.values())
        latest_date = missing[-1]
        current_value = sum(
            latest_holdings[s]["quantity"] * hist[s].loc[:pd.Timestamp(latest_date)].dropna().iloc[-1]
            for s in latest_holdings if s in hist.columns
        ) if not hist.empty else 0
        total_pnl = current_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        log.info(
            f"{strategy}: marked {marked} day(s) "
            f"({'backfilled' if marked > 1 else 'current'}) | "
            f"invested Rs.{total_cost:,.0f} -> value Rs.{current_value:,.0f} "
            f"(P&L {total_pnl:+,.0f} / {total_pnl_pct:+.2f}%) | "
            f"{len(latest_holdings)} positions"
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
