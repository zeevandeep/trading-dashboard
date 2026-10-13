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

    # Step 2: If orders look right, execute (always routes via DO proxy by default)
    python scripts/bedrock_live_rebalance.py

    # Override capital (default Rs 1,00,000)
    python scripts/bedrock_live_rebalance.py --capital 200000

    # Direct execution without proxy (requires locally whitelisted IP — rarely needed)
    python scripts/bedrock_live_rebalance.py --local
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
from trading.signals.value_quality import score_value_quality_from_cache
from trading.execution.angel import login, get_holdings, get_ltp, place_orders, place_orders_remote, log_orders
from trading.utils.logging import setup_logging

log = setup_logging("bedrock_rebalance")

CONFIG_PATH = ROOT / "configs" / "value_quality_v1_live.yaml"
DEFAULT_CAPITAL = 100_000


def _post_rebalance_cleanup(
    strategy_name: str,
    broker_holdings: dict,
    log_path: Path,
    broker_source: str = "angelone",
) -> None:
    """Run after placing real orders:
    1. Validate orders.csv for column-shift corruption (NaN timestamps)
    2. Save pre-rebalance holdings as snapshot dated yesterday — ensures today's
       placed orders are applied on top by compute_holdings (strict > comparison)
    3. Run daily mark for immediate P&L update
    """
    import json
    from datetime import date, timedelta

    strategy_dir = DATA_DIR / "live" / strategy_name
    snap_fname = "kite_snapshot.json" if broker_source == "kite" else "holdings_snapshot.json"
    snap_path = strategy_dir / snap_fname

    # 1. Validate orders.csv
    if log_path.exists():
        import pandas as _pd
        df = _pd.read_csv(log_path)
        bad = int(df["timestamp"].isna().sum())
        if bad > 0:
            print(f"\n⚠ WARNING: {bad} rows have NaN timestamp in {log_path.name}")
            print("  This indicates a column-shift bug (estimated_value missing from order results).")
            print("  Rows are corrupt — status/limit_price/timestamp columns are shifted.")
            print("  Run a manual repair before the next rebalance.")

    # 2. Save snapshot (pre-rebalance holdings, dated yesterday)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Preserve epoch_start from existing snapshot
    epoch_start = None
    if snap_path.exists():
        with open(snap_path) as f:
            old = json.load(f)
        epoch_start = old.get("epoch_start")

    def _strip_eq(s: str) -> str:
        return s[:-3] if s.endswith("-EQ") else s

    snap = {
        "date": yesterday,
        "source": f"{broker_source}_holdings_api",
        "holdings": {
            _strip_eq(sym): {
                "quantity": h["quantity"],
                "average_price": round(float(h.get("average_price", 0)), 2),
                "cost_basis": round(h["quantity"] * float(h.get("average_price", 0)), 2),
            }
            for sym, h in broker_holdings.items()
            if h.get("quantity", 0) > 0
        },
    }
    if epoch_start:
        snap["epoch_start"] = epoch_start

    with open(snap_path, "w") as f:
        json.dump(snap, f, indent=2)

    n = len(snap["holdings"])
    log.info(f"Snapshot saved: {n} pre-rebalance positions dated {yesterday} → {snap_path.name}")
    print(f"\nSnapshot updated: {n} positions, dated {yesterday}")
    print(f"Today's placed orders will be applied on top by compute_holdings.")

    # 3. Immediate daily mark
    print("Running daily mark...")
    import importlib.util
    mark_script = ROOT / "scripts" / "daily_live_mark.py"
    spec = importlib.util.spec_from_file_location("daily_live_mark", mark_script)
    mark_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mark_mod)
    mark_mod.mark_live_strategy(strategy_name)
    print("Mark complete.")


def main():
    parser = argparse.ArgumentParser(description="Quarterly Bedrock rebalance (AngelOne)")
    parser.add_argument("--dry-run", action="store_true", help="Show orders without placing them")
    parser.add_argument("--local", action="store_true", help="Place orders directly (requires whitelisted IP — rarely needed)")
    parser.add_argument("--amo", action="store_true", help="Place After Market Orders (use outside 9:15–3:30 IST)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="Total capital in INR")
    args = parser.parse_args()
    args.remote = not args.local  # proxy is always default

    ensure_dirs()

    cfg = load_strategy_config(str(CONFIG_PATH))
    strategy_name = cfg.get("name", "value_quality_v1_live")
    top_n = cfg.get("portfolio", {}).get("top_n", 15)

    print(f"\n{'='*60}")
    print(f"  BEDROCK QUARTERLY REBALANCE (AngelOne)")
    print(f"  Strategy: {strategy_name}")
    print(f"  Capital:  Rs. {args.capital:,.0f}")
    print(f"  Top N:    {top_n}")
    mode_parts = []
    if args.dry_run:
        mode_parts.append("DRY RUN")
    else:
        mode_parts.append("LIVE via PROXY" if args.remote else "LIVE (local)")
        if args.amo:
            mode_parts.append("AMO")
    mode = " | ".join(mode_parts)
    print(f"  Mode:     {mode}")
    print(f"{'='*60}\n")

    # ── AngelOne login (automated via TOTP)
    log.info("Authenticating with AngelOne...")
    obj = login()

    # ── Universe (NSE 500 ex Nifty 50)
    nifty50 = set(nifty50_tickers())
    tickers = [t for t in nse500_starter_tickers() if t not in nifty50]
    log.info(f"Universe: {len(tickers)} tickers (NSE 500 ex Nifty 50)")

    # ── Score V+Q from fundamentals cache
    # Cache is built quarterly by refresh_fundamentals_cache.py
    # Never scrapes live at execution time — decoupled and reliable
    log.info("Scoring V+Q from fundamentals cache...")
    scores = score_value_quality_from_cache(tickers)

    if scores.empty:
        log.error("No valid V+Q scores. Run: python scripts/refresh_fundamentals_cache.py")
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
    # AngelOne returns holdings with '-EQ' suffix (e.g. GLAXO-EQ) — strip for LTP lookup
    def _strip_eq(sym: str) -> str:
        return sym[:-3] if sym.endswith("-EQ") else sym

    target_syms = list(target_weights.keys())
    holding_syms_plain = [_strip_eq(s) for s in current_holdings.keys()]
    all_symbols = list(set(target_syms + holding_syms_plain))
    live_prices = get_ltp(obj, all_symbols) if all_symbols else {}

    # Build a lookup that works for both plain and -EQ symbols
    for sym in list(current_holdings.keys()):
        plain = _strip_eq(sym)
        if plain in live_prices and sym not in live_prices:
            live_prices[sym] = live_prices[plain]

    # ── Compute orders
    orders = []
    # Normalise -EQ suffix from AngelOne holdings so symbols match target picks
    current_qty = {_strip_eq(s): h["quantity"] for s, h in current_holdings.items()}
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

    # ── GSM pre-check: flag any target stocks under NSE cautionary listing
    # Stocks with '-BE' series on AngelOne = Trade-for-Trade = GSM proxy
    # AngelOne blocks API orders on these with error AB4036
    log.info("Running GSM pre-check on order symbols...")
    order_syms = list({o["symbol"] for o in orders})
    gsm_flagged: list[str] = []
    try:
        from scripts.check_gsm_flags import check_gsm_via_angel
        gsm_results = check_gsm_via_angel(order_syms, obj=obj)
        gsm_flagged = [s for s, v in gsm_results.items() if v == "gsm"]
        if gsm_flagged:
            print(f"\n{'!'*60}")
            print(f"  GSM WARNING — AngelOne will BLOCK orders for:")
            for s in gsm_flagged:
                print(f"    {s}")
            print(f"  These will fail with AB4036 (cautionary listing).")
            print(f"  Remove them or handle manually.")
            print(f"{'!'*60}\n")
        else:
            log.info("GSM check passed — no cautionary stocks in order list")
    except Exception as gsm_err:
        log.warning(f"GSM check failed (non-blocking): {gsm_err}")

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
    if args.yes:
        print("Auto-confirmed via --yes flag.")
    else:
        confirm = input("\nType 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return

    # ── Place orders
    amo_label = " AMO" if args.amo else ""
    proxy_label = " (via proxy)" if args.remote else ""
    print(f"\nPlacing {len(orders)}{amo_label} orders{proxy_label}...")
    if args.remote:
        results = place_orders_remote(orders, prices=live_prices, amo=args.amo)
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
        _post_rebalance_cleanup(
            strategy_name=strategy_name,
            broker_holdings=current_holdings,
            log_path=log_path,
            broker_source="angelone",
        )
    else:
        print("No orders placed — skipping post-rebalance cleanup.")


if __name__ == "__main__":
    main()
