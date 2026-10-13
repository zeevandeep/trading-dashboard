"""Retry specific failed/missed orders via the DO proxy.

Usage:
    # Always dry-run first
    python scripts/retry_failed_orders.py --dry-run

    # Execute when orders look right
    python scripts/retry_failed_orders.py
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx
import yfinance as yf
from trading.config import DATA_DIR, Secrets
from trading.execution.angel import log_orders
from trading.utils.logging import setup_logging

log = setup_logging("retry_orders")

# Oct 12 rebalance — outstanding corrections
# IOB SELL 142 ✓ placed  |  AUBANK BUY 4 ✓ placed
# IEX SELL 13 — BLOCKED: NSE cautionary listing (AB4036), exchange blocks API trading
# BAJAJHLDNG BUY 1 — BLOCKED: NSE cautionary listing (AB4036), exchange blocks API trading
# Both require AngelOne app to place manually (exchange-level restriction, no API workaround)
PENDING_ORDERS: list[dict] = []

LOG_PATH = DATA_DIR / "live" / "value_quality_v1_live" / "orders.csv"


def _angel_creds(secrets: Secrets) -> dict:
    return {
        "angel_api_key":     secrets.angel_api_key,
        "angel_client_id":   secrets.angel_client_id,
        "angel_password":    secrets.angel_password,
        "angel_totp_secret": secrets.angel_totp_secret,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show orders without placing them")
    args = parser.parse_args()

    syms = [o["symbol"] for o in PENDING_ORDERS]
    log.info(f"Fetching prices for {syms}...")
    raw = yf.download([f"{s}.NS" for s in syms], period="1d", progress=False)["Close"].iloc[-1]
    prices = {s: round(float(raw[f"{s}.NS"]), 2) for s in syms}

    orders = [
        {**o, "estimated_value": round(o["quantity"] * prices[o["symbol"]], 2)}
        for o in PENDING_ORDERS
    ]

    print("\n── Dry-run: orders to be placed ──────────────────────")
    total_sell = sum(o["estimated_value"] for o in orders if o["side"] == "SELL")
    total_buy  = sum(o["estimated_value"] for o in orders if o["side"] == "BUY")
    for o in orders:
        print(f"  {o['side']:>4s}  {o['quantity']:>4d} x {o['symbol']:<15s}  ~Rs {o['estimated_value']:>9,.0f}  (LTP {prices[o['symbol']]})")
    print(f"\n  Total SELL: Rs {total_sell:,.0f}  |  Total BUY: Rs {total_buy:,.0f}")
    print("──────────────────────────────────────────────────────\n")

    if args.dry_run:
        print("Dry-run mode — no orders placed.")
        return

    confirm = input("Place these orders? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    secrets = Secrets.from_env()
    proxy_url = secrets.proxy_url.rstrip("/")
    proxy_key = secrets.proxy_api_key

    payload = {
        **_angel_creds(secrets),
        "orders": orders,
        "prices": prices,
        "amo": False,
    }

    log.info(f"Sending {len(orders)} orders to proxy at {proxy_url}...")
    resp = httpx.post(
        f"{proxy_url}/api/angel/place-orders",
        json=payload,
        headers={"Authorization": f"Bearer {proxy_key}"},
        timeout=120,
    )
    resp.raise_for_status()

    results = resp.json()
    placed, failed = [], []
    for r in results:
        status = r.get("status", "unknown")
        log.info(f"  {r['side']:>4s} {r['quantity']:>4d} x {r['symbol']:<15s} → {status}  order_id={r.get('order_id')}")
        (placed if status == "placed" else failed).append(r)

    log_orders(results, LOG_PATH)
    log.info(f"Results logged to {LOG_PATH}")

    print(f"\nDone: {len(placed)} placed, {len(failed)} failed")
    if failed:
        for f in failed:
            print(f"  FAILED: {f['side']} {f['quantity']} {f['symbol']} — {f.get('status')}")
        print("\nCheck AngelOne app or re-run.")


if __name__ == "__main__":
    main()
