"""Quarterly live rebalance for Bedrock (Value + Quality) on AngelOne.

Fully automated login via TOTP — no browser needed.

This script:
  1. Logs into AngelOne (automated TOTP)
  2. Fetches current broker holdings
  3. Fetches fundamentals and computes V+Q scores
  4. Calculates order deltas (sells first, then buys)
  5. Shows a dry-run summary and asks for confirmation
  6. Places LIMIT orders on NSE
  7. Logs everything to data/live/

Usage:
    # Step 1: Always dry-run first
    python scripts/bedrock_live_rebalance.py --dry-run

    # Step 2: If orders look right, execute for real
    python scripts/bedrock_live_rebalance.py

    # Override capital (default Rs 1,00,000)
    python scripts/bedrock_live_rebalance.py --capital 200000
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
from trading.data.universe import nifty50_tickers, nse500_starter_tickers
from trading.signals.value_quality import fetch_fundamentals, score_value_quality
from trading.execution.angel import login, get_holdings, get_ltp, place_orders, place_orders_remote, log_orders
from trading.utils.logging import setup_logging

log = setup_logging("bedrock_rebalance")

CONFIG_PATH = ROOT / "configs" / "value_quality_v1_live.yaml"
DEFAULT_CAPITAL = 100_000


def main():
    parser = argparse.ArgumentParser(description="Quarterly Bedrock rebalance (AngelOne)")
    parser.add_argument("--dry-run", action="store_true", help="Show orders without placing them")
    parser.add_argument("--remote", action="store_true", help="Route orders via Render proxy (fixed IP)")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="Total capital in INR")
    args = parser.parse_args()

    ensure_dirs()

    cfg = load_strategy_config(str(CONFIG_PATH))
    strategy_name = cfg.get("name", "value_quality_v1_live")
    top_n = cfg.get("portfolio", {}).get("top_n", 15)

    print(f"\n{'='*60}")
    print(f"  BEDROCK QUARTERLY REBALANCE (AngelOne)")
    print(f"  Strategy: {strategy_name}")
    print(f"  Capital:  Rs. {args.capital:,.0f}")
    print(f"  Top N:    {top_n}")
    mode = "DRY RUN" if args.dry_run else ("LIVE via PROXY" if args.remote else "LIVE")
    print(f"  Mode:     {mode}")
    print(f"{'='*60}\n")

    # ── AngelOne login (automated via TOTP)
    log.info("Authenticating with AngelOne...")
    obj = login()

    # ── Universe (NSE 500 ex Nifty 50)
    nifty50 = set(nifty50_tickers())
    tickers = [t for t in nse500_starter_tickers() if t not in nifty50]
    log.info(f"Universe: {len(tickers)} tickers (NSE 500 ex Nifty 50)")

    # ── Fetch fundamentals and score
    log.info("Fetching fundamentals...")
    fundamentals = fetch_fundamentals(tickers)

    if fundamentals.empty:
        log.error("No fundamentals fetched.")
        return

    scores = score_value_quality(fundamentals)

    if scores.empty:
        log.error("No valid V+Q scores.")
        return

    if len(scores) < top_n:
        log.error(f"Only {len(scores)} valid scores, need at least {top_n}.")
        return

    picks = scores.nlargest(top_n)
    target_weights = {t: 1.0 / top_n for t in picks.index}
    log.info(f"Target top-{top_n}: {list(picks.index)}")

    # ── Current broker state
    current_holdings = get_holdings(obj)
    log.info(f"Current AngelOne holdings: {len(current_holdings)} positions")

    if current_holdings:
        print("Current holdings:")
        for sym, info in current_holdings.items():
            print(f"  {sym:>15s}  qty={info['quantity']:>5d}  avg={info['average_price']:>10,.2f}")
        print()

    # ── Prices
    all_symbols = list(set(list(target_weights.keys()) + list(current_holdings.keys())))
    live_prices = get_ltp(obj, all_symbols) if all_symbols else {}

    # ── Compute orders
    orders = []
    current_qty = {s: h["quantity"] for s, h in current_holdings.items()}
    per_stock = args.capital / top_n

    target_qty = {}
    for symbol in target_weights:
        if symbol not in live_prices or live_prices[symbol] <= 0:
            log.warning(f"No price for {symbol}, skipping")
            continue
        qty = max(1, int(per_stock / live_prices[symbol]))
        target_qty[symbol] = qty

    all_syms = set(list(current_qty.keys()) + list(target_qty.keys()))

    # Sells first
    for symbol in sorted(all_syms):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur
        if delta < 0:
            price = live_prices.get(symbol, 0)
            orders.append({
                "symbol": symbol, "side": "SELL",
                "quantity": abs(delta), "estimated_value": abs(delta) * price,
            })

    # Then buys
    for symbol in sorted(all_syms):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur
        if delta > 0:
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
    print(f"  THIS WILL PLACE {len(orders)} REAL ORDERS ON ANGELONE")
    print(f"  Total buy value: Rs. {total_buy:,.0f}")
    print(f"{'!'*60}")
    confirm = input("\nType 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    # ── Place orders
    print(f"\nPlacing {len(orders)} orders{'  (via proxy)' if args.remote else ''}...")
    if args.remote:
        results = place_orders_remote(orders, prices=live_prices)
    else:
        results = place_orders(obj, orders, prices=live_prices, dry_run=False)

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
        print("Check your AngelOne app to verify fills.")


if __name__ == "__main__":
    main()
