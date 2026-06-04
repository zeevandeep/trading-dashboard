"""Monthly rebalance on AngelOne (top-10 strategy).

Fully automated — no browser login needed (uses TOTP).

Usage:
    python scripts/monthly_angel_rebalance.py --dry-run
    python scripts/monthly_angel_rebalance.py --capital 10000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR, load_strategy_config, ensure_dirs
from trading.data.loader import fetch_many, to_price_panel
from trading.data.universe import smallcap_universe
from trading.signals.momentum import momentum_n_m
from trading.execution.angel import login, get_holdings, get_ltp, place_orders, log_orders
from trading.utils.logging import setup_logging

log = setup_logging("angel_rebalance")

CONFIG_PATH = ROOT / "configs" / "smallcap_momentum_v2_angel.yaml"
DEFAULT_CAPITAL = 10_000


def main():
    parser = argparse.ArgumentParser(description="Monthly AngelOne rebalance (top-10)")
    parser.add_argument("--dry-run", action="store_true", help="Show orders without placing")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="Capital in INR")
    parser.add_argument("--force-refresh", action="store_true", help="Re-download price data")
    args = parser.parse_args()

    ensure_dirs()

    cfg = load_strategy_config(str(CONFIG_PATH))
    strategy_name = cfg.get("name", "smallcap_momentum_v2_angel")
    top_n = cfg.get("portfolio", {}).get("top_n", 10)

    print(f"\n{'='*60}")
    print(f"  ANGELONE MONTHLY REBALANCE")
    print(f"  Strategy: {strategy_name}")
    print(f"  Capital:  Rs. {args.capital:,.0f}")
    print(f"  Top N:    {top_n}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    # Login (automated via TOTP)
    log.info("Authenticating with AngelOne...")
    obj = login()

    # Universe & prices
    tickers = smallcap_universe()
    log.info(f"Universe: {len(tickers)} tickers")

    sig_cfg = cfg.get("signal", {})
    lookback = sig_cfg.get("lookback_months", 12)
    start = (pd.Timestamp.now() - pd.DateOffset(months=lookback + 2)).strftime("%Y-%m-%d")

    log.info(f"Fetching prices from {start}...")
    price_dict = fetch_many(tickers, start=start, force_refresh=args.force_refresh)
    prices = to_price_panel(price_dict, field="adj_close")
    log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

    # Signal
    skip = sig_cfg.get("skip_months", 1)
    scores = momentum_n_m(prices, lookback_months=lookback, skip_months=skip)
    latest_scores = scores.iloc[-1].dropna()

    if latest_scores.empty:
        log.error("No valid momentum scores.")
        return

    picks = latest_scores.nlargest(top_n)
    target_weights = {t: 1.0 / top_n for t in picks.index}
    log.info(f"Target top-{top_n}: {list(picks.index)}")

    # Current broker state
    current_holdings = get_holdings(obj)
    log.info(f"Current AngelOne holdings: {len(current_holdings)} positions")

    if current_holdings:
        print("Current holdings:")
        for sym, info in current_holdings.items():
            print(f"  {sym:>15s}  qty={info['quantity']:>5d}  avg={info['average_price']:>10,.2f}")
        print()

    # Prices
    all_symbols = list(set(list(target_weights.keys()) + list(current_holdings.keys())))
    live_prices = get_ltp(obj, all_symbols) if all_symbols else {}

    # Compute orders
    orders = []
    current_qty = {s: h["quantity"] for s, h in current_holdings.items()}
    per_stock = args.capital / top_n

    target_qty = {}
    for symbol, weight in target_weights.items():
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
            orders.append({"symbol": symbol, "side": "SELL", "quantity": abs(delta), "estimated_value": abs(delta) * price})

    # Then buys
    for symbol in sorted(all_syms):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur
        if delta > 0:
            price = live_prices.get(symbol, 0)
            orders.append({"symbol": symbol, "side": "BUY", "quantity": delta, "estimated_value": delta * price})

    if not orders:
        print("No orders needed — portfolio already at target.")
        return

    # Display
    sells = [o for o in orders if o["side"] == "SELL"]
    buys = [o for o in orders if o["side"] == "BUY"]

    if sells:
        total_sell = sum(o["estimated_value"] for o in sells)
        print(f"SELLS ({len(sells)} orders, ~Rs. {total_sell:,.0f}):")
        for o in sells:
            p = live_prices.get(o["symbol"], 0)
            print(f"  SELL {o['quantity']:>4d} x {o['symbol']:<15s} @ Rs.{p:>10,.2f} = Rs.{o['estimated_value']:>10,.0f}")
        print()

    if buys:
        total_buy = sum(o["estimated_value"] for o in buys)
        print(f"BUYS ({len(buys)} orders, ~Rs. {total_buy:,.0f}):")
        for o in buys:
            p = live_prices.get(o["symbol"], 0)
            print(f"  BUY  {o['quantity']:>4d} x {o['symbol']:<15s} @ Rs.{p:>10,.2f} = Rs.{o['estimated_value']:>10,.0f}")
        print()

    if args.dry_run:
        print(f"{'='*60}")
        print("DRY RUN — no orders placed.")
        return

    # Confirm
    print(f"\n{'!'*60}")
    print(f"  THIS WILL PLACE {len(orders)} REAL ORDERS ON ANGELONE")
    print(f"{'!'*60}")
    confirm = input("\nType 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    # Execute
    print(f"\nPlacing {len(orders)} orders...")
    results = place_orders(obj, orders, prices=live_prices, dry_run=False)

    log_path = DATA_DIR / "live" / strategy_name / "orders.csv"
    log_orders(results, log_path)

    placed = [r for r in results if r["status"] == "placed"]
    failed = [r for r in results if r["status"].startswith("failed")]
    print(f"\nDone: {len(placed)} placed, {len(failed)} failed")
    for r in results:
        print(f"  {r['side']:>4s} {r['quantity']:>4d} x {r['symbol']:<15s}  status={r['status']}  order_id={r.get('order_id', '-')}")


if __name__ == "__main__":
    main()
