"""Monthly live rebalance script for the top-5 strategy.

This script:
  1. Logs into Kite (opens browser if session expired)
  2. Fetches current broker holdings
  3. Computes new top-5 momentum signals
  4. Calculates order deltas (sells first, then buys)
  5. Shows a dry-run summary and asks for confirmation
  6. Places LIMIT orders on NSE
  7. Logs everything to data/live/

Usage:
    # Step 1: Always dry-run first
    python scripts/monthly_live_rebalance.py --dry-run

    # Step 2: If orders look right, execute for real
    python scripts/monthly_live_rebalance.py

    # Override capital (default Rs 10,000)
    python scripts/monthly_live_rebalance.py --capital 50000
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR, load_strategy_config, ensure_dirs
from trading.data.loader import fetch_many, to_price_panel, fetch_benchmark
from trading.data.universe import smallcap_universe
from trading.signals.momentum import momentum_n_m
from trading.execution.kite import (
    login, get_holdings, get_ltp, place_orders, log_orders,
)
from trading.utils.logging import setup_logging

log = setup_logging("live_rebalance")

CONFIG_PATH = ROOT / "configs" / "smallcap_momentum_v2_live.yaml"
DEFAULT_CAPITAL = 10_000


def main():
    parser = argparse.ArgumentParser(description="Monthly live rebalance (top-5)")
    parser.add_argument("--dry-run", action="store_true", help="Show orders without placing them")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="Total capital in INR")
    parser.add_argument("--force-refresh", action="store_true", help="Re-download all price data")
    args = parser.parse_args()

    ensure_dirs()

    cfg = load_strategy_config(str(CONFIG_PATH))
    strategy_name = cfg.get("name", "smallcap_momentum_v2_live")
    top_n = cfg.get("portfolio", {}).get("top_n", 5)

    print(f"\n{'='*60}")
    print(f"  MONTHLY LIVE REBALANCE")
    print(f"  Strategy: {strategy_name}")
    print(f"  Capital:  Rs. {args.capital:,.0f}")
    print(f"  Top N:    {top_n}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    # ── Kite login
    log.info("Authenticating with Kite...")
    kite = login()

    # ── Universe & price data
    tickers = smallcap_universe()
    log.info(f"Universe: {len(tickers)} tickers")

    sig_cfg = cfg.get("signal", {})
    lookback = sig_cfg.get("lookback_months", 12)
    start = (pd.Timestamp.now() - pd.DateOffset(months=lookback + 2)).strftime("%Y-%m-%d")

    log.info(f"Fetching prices from {start}...")
    price_dict = fetch_many(tickers, start=start, force_refresh=args.force_refresh)
    prices = to_price_panel(price_dict, field="adj_close")
    log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

    # ── Momentum signal
    skip = sig_cfg.get("skip_months", 1)
    scores = momentum_n_m(prices, lookback_months=lookback, skip_months=skip)
    latest_scores = scores.iloc[-1].dropna()

    if latest_scores.empty:
        log.error("No valid momentum scores.")
        return

    picks = latest_scores.nlargest(top_n)
    target_weights = {t: 1.0 / top_n for t in picks.index}
    log.info(f"Target top-{top_n}: {list(picks.index)}")

    # ── Current broker state
    current_holdings = get_holdings(kite)
    log.info(f"Current broker holdings: {len(current_holdings)} positions")

    if current_holdings:
        print("Current holdings:")
        for sym, info in current_holdings.items():
            print(f"  {sym:>15s}  qty={info['quantity']:>5d}  avg={info['average_price']:>10,.2f}")
        print()

    # ── Prices
    all_symbols = list(set(list(target_weights.keys()) + list(current_holdings.keys())))
    live_prices = get_ltp(kite, all_symbols) if all_symbols else {}

    # ── Compute orders with min 1 share per target stock
    orders = []
    current_qty = {s: h["quantity"] for s, h in current_holdings.items()}
    per_stock = args.capital / top_n

    # Target quantities
    target_qty = {}
    for symbol, weight in target_weights.items():
        if symbol not in live_prices or live_prices[symbol] <= 0:
            log.warning(f"No price for {symbol}, skipping")
            continue
        qty = max(1, int(per_stock / live_prices[symbol]))
        target_qty[symbol] = qty

    # Sells first
    all_syms = set(list(current_qty.keys()) + list(target_qty.keys()))
    for symbol in sorted(all_syms):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur
        if delta == 0:
            continue
        price = live_prices.get(symbol, 0)
        if delta < 0:
            orders.append({
                "symbol": symbol, "side": "SELL",
                "quantity": abs(delta), "estimated_value": abs(delta) * price,
            })

    # Then buys
    for symbol in sorted(all_syms):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur
        if delta <= 0:
            continue
        price = live_prices.get(symbol, 0)
        orders.append({
            "symbol": symbol, "side": "BUY",
            "quantity": delta, "estimated_value": delta * price,
        })

    if not orders:
        print("No orders needed — portfolio already at target.")
        return

    # ── Display order plan
    sells = [o for o in orders if o["side"] == "SELL"]
    buys = [o for o in orders if o["side"] == "BUY"]
    total_sell = sum(o["estimated_value"] for o in sells)
    total_buy = sum(o["estimated_value"] for o in buys)

    if sells:
        print(f"SELLS ({len(sells)} orders, ~Rs. {total_sell:,.0f}):")
        for o in sells:
            p = live_prices.get(o["symbol"], 0)
            print(f"  SELL {o['quantity']:>4d} x {o['symbol']:<15s} @ Rs.{p:>10,.2f} = Rs.{o['estimated_value']:>10,.0f}")
        print()

    if buys:
        print(f"BUYS ({len(buys)} orders, ~Rs. {total_buy:,.0f}):")
        for o in buys:
            p = live_prices.get(o["symbol"], 0)
            print(f"  BUY  {o['quantity']:>4d} x {o['symbol']:<15s} @ Rs.{p:>10,.2f} = Rs.{o['estimated_value']:>10,.0f}")
        print()

    print(f"Net cash flow: Rs. {total_sell - total_buy:,.0f}")

    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — no orders placed.")
        print("Run without --dry-run to execute.")
        return

    # ── Confirmation
    print(f"\n{'!'*60}")
    print(f"  THIS WILL PLACE {len(orders)} REAL ORDERS ON NSE")
    print(f"  Total buy value: Rs. {total_buy:,.0f}")
    print(f"{'!'*60}")
    confirm = input("\nType 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    # ── Place orders
    print(f"\nPlacing {len(orders)} orders...")
    results = place_orders(kite, orders, prices=live_prices, exchange="NSE", dry_run=False)

    # ── Log
    log_path = DATA_DIR / "live" / strategy_name / "orders.csv"
    log_orders(results, log_path)

    # ── Summary
    placed = [r for r in results if r["status"] == "placed"]
    failed = [r for r in results if r["status"].startswith("failed")]

    print(f"\nDone: {len(placed)} placed, {len(failed)} failed")
    for r in results:
        status = r["status"]
        oid = r.get("order_id", "-")
        print(f"  {r['side']:>4s} {r['quantity']:>4d} x {r['symbol']:<15s}  status={status}  order_id={oid}")

    if placed:
        print(f"\nOrders logged to {log_path}")
        print("Check your Kite app to verify fills.")


if __name__ == "__main__":
    main()
