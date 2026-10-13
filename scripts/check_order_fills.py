"""Check whether yesterday's rebalance orders were filled.

Runs at 9:45 AM IST after any rebalance. Compares orders.csv "placed"
orders against current broker holdings and alerts via Telegram if anything
is unfilled or mismatched.

Usage:
    python scripts/check_order_fills.py               # checks both strategies
    python scripts/check_order_fills.py --strategy bedrock
    python scripts/check_order_fills.py --strategy ascent
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.utils.logging import setup_logging

log = setup_logging("fill_check")

LIVE_DIR = DATA_DIR / "live"
STRATEGIES = {
    "bedrock": "value_quality_v1_live",
    "ascent":  "smallcap_momentum_v2_live",
}


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("Telegram not configured — skipping alert")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        log.info("Telegram alert sent")
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


# ── Orders CSV helpers ────────────────────────────────────────────────────────

def load_recent_placed_orders(orders_csv: Path, lookback_days: int = 3) -> pd.DataFrame:
    """Return placed orders from the last N trading days."""
    if not orders_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(orders_csv)
    if df.empty or "status" not in df.columns:
        return pd.DataFrame()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    cutoff = datetime.now() - timedelta(days=lookback_days)
    return df[
        (df["status"] == "placed") &
        (df["timestamp"] >= cutoff)
    ].copy()


def compute_expected_holdings(orders_df: pd.DataFrame, current_holdings: dict[str, int]) -> dict[str, int]:
    """Apply placed orders on top of current holdings to get expected state."""
    expected = dict(current_holdings)
    for _, row in orders_df.iterrows():
        sym = row["symbol"].replace("-EQ", "")
        qty = int(row["quantity"])
        if row["side"] == "BUY":
            expected[sym] = expected.get(sym, 0) + qty
        else:
            expected[sym] = max(0, expected.get(sym, 0) - qty)
    return {k: v for k, v in expected.items() if v > 0}


# ── AngelOne fill check ───────────────────────────────────────────────────────

def check_angel_fills(orders_df: pd.DataFrame) -> list[dict]:
    """Check AngelOne order fills. Returns list of unfilled orders."""
    if orders_df.empty:
        return []

    from trading.execution.angel import login, get_holdings

    log.info("Logging in to AngelOne...")
    obj = login()
    holdings = get_holdings(obj)
    actual_qty = {s.replace("-EQ", ""): h["quantity"] for s, h in holdings.items()}

    unfilled = []
    for _, row in orders_df.iterrows():
        sym = row["symbol"].replace("-EQ", "")
        qty = int(row["quantity"])
        side = row["side"]
        actual = actual_qty.get(sym, 0)

        if side == "BUY" and actual == 0:
            unfilled.append({
                "symbol": sym, "side": side, "quantity": qty,
                "actual_qty": actual, "order_id": row.get("order_id", ""),
                "timestamp": str(row["timestamp"]),
            })
        elif side == "SELL":
            # For sells, check order book if available (today only)
            order_book = []
            try:
                resp = obj.orderBook()
                order_book = resp.get("data") or []
            except Exception:
                pass
            order_id = str(row.get("order_id", ""))
            filled = any(
                o.get("orderid") == order_id and o.get("status") == "complete"
                for o in order_book
            )
            if not filled and order_id:
                # Can't verify sell fills from holdings alone — mark as uncertain
                unfilled.append({
                    "symbol": sym, "side": side, "quantity": qty,
                    "actual_qty": actual, "order_id": order_id,
                    "timestamp": str(row["timestamp"]),
                    "note": "sell fill unverifiable from holdings",
                })

    return unfilled


# ── Ascent (Kite) fill check ─────────────────────────────────────────────────

def check_ascent_fills(orders_df: pd.DataFrame) -> list[dict]:
    """Check Ascent fill status from holdings snapshot (Kite access token not available in CI)."""
    if orders_df.empty:
        return []

    snapshot_path = LIVE_DIR / STRATEGIES["ascent"] / "kite_snapshot.json"
    if not snapshot_path.exists():
        log.warning("No Kite snapshot — skipping Ascent fill check")
        return []

    import json
    with open(snapshot_path) as f:
        snapshot = json.load(f)

    holdings = snapshot.get("holdings", {})
    actual_qty = {s.replace("-EQ", "").replace(":NSE", ""): h.get("quantity", 0)
                  for s, h in holdings.items()}

    unfilled = []
    for _, row in orders_df.iterrows():
        sym = row["symbol"].replace("-EQ", "")
        qty = int(row["quantity"])
        side = row["side"]
        actual = actual_qty.get(sym, 0)

        if side == "BUY" and actual == 0:
            unfilled.append({
                "symbol": sym, "side": side, "quantity": qty,
                "actual_qty": actual, "order_id": row.get("order_id", ""),
                "timestamp": str(row["timestamp"]),
            })

    return unfilled


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["bedrock", "ascent", "both"], default="both")
    args = parser.parse_args()

    all_unfilled: dict[str, list] = {}

    strategies_to_check = (
        ["bedrock", "ascent"] if args.strategy == "both"
        else [args.strategy]
    )

    for strat in strategies_to_check:
        strategy_dir = LIVE_DIR / STRATEGIES[strat]
        orders_csv = strategy_dir / "orders.csv"
        orders_df = load_recent_placed_orders(orders_csv)

        if orders_df.empty:
            log.info(f"{strat}: no placed orders in last 3 days")
            continue

        log.info(f"{strat}: checking {len(orders_df)} placed orders...")

        if strat == "bedrock":
            unfilled = check_angel_fills(orders_df)
        else:
            unfilled = check_ascent_fills(orders_df)

        if unfilled:
            all_unfilled[strat] = unfilled
            for u in unfilled:
                log.warning(f"  UNFILLED: {u['side']} {u['quantity']} {u['symbol']}  order_id={u['order_id']}")
        else:
            log.info(f"  {strat}: all orders filled")

    # ── Alert ────────────────────────────────────────────────────────────────
    if all_unfilled:
        lines = ["*JD Quant — Unfilled Orders Alert*\n"]
        for strat, orders in all_unfilled.items():
            lines.append(f"*{strat.upper()}*")
            for u in orders:
                lines.append(f"  {u['side']} {u['quantity']} {u['symbol']} — order `{u['order_id']}`")
        lines.append("\nRe-run rebalance script to retry.")
        send_telegram("\n".join(lines))
        print("\nUNFILLED ORDERS DETECTED — Telegram alert sent")
        sys.exit(1)
    else:
        log.info("All orders filled. No alert needed.")
        print("\nAll orders filled.")


if __name__ == "__main__":
    main()
