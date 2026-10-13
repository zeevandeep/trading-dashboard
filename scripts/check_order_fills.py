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

def check_angel_fills(orders_df: pd.DataFrame, strategy_dir: Path) -> list[dict]:
    """Check AngelOne fills: compare expected post-rebalance holdings vs actual.

    Expected = snapshot (pre-rebalance base) + placed orders applied on top.
    Actual = live AngelOne holdings via API.
    Flags any symbol where actual qty != expected qty.
    """
    if orders_df.empty:
        return []

    import json
    from trading.execution.angel import login, get_holdings

    # Build expected holdings: snapshot + orders
    snap_path = strategy_dir / "holdings_snapshot.json"
    snap_qty: dict[str, int] = {}
    if snap_path.exists():
        with open(snap_path) as f:
            snap = json.load(f)
        snap_qty = {s: int(h["quantity"]) for s, h in snap["holdings"].items() if h["quantity"] > 0}

    expected_qty = dict(snap_qty)
    for _, row in orders_df.iterrows():
        sym = str(row["symbol"]).replace("-EQ", "")
        qty = int(row["quantity"])
        if row["side"] == "BUY":
            expected_qty[sym] = expected_qty.get(sym, 0) + qty
        elif row["side"] == "SELL":
            expected_qty[sym] = max(0, expected_qty.get(sym, 0) - qty)
    expected_qty = {k: v for k, v in expected_qty.items() if v > 0}

    log.info("Logging in to AngelOne...")
    obj = login()
    holdings = get_holdings(obj)
    actual_qty = {s.replace("-EQ", ""): h["quantity"] for s, h in holdings.items()}

    unfilled = []
    for sym, expected in expected_qty.items():
        actual = actual_qty.get(sym, 0)
        if actual != expected:
            side = "BUY" if actual < expected else "SELL"
            unfilled.append({
                "symbol": sym,
                "side": side,
                "quantity": abs(expected - actual),
                "expected_qty": expected,
                "actual_qty": actual,
                "order_id": orders_df[orders_df["symbol"].str.replace("-EQ", "") == sym]["order_id"].iloc[0]
                             if sym in orders_df["symbol"].str.replace("-EQ", "").values else "",
                "timestamp": str(orders_df["timestamp"].iloc[-1]),
            })

    return unfilled


# ── Ascent (Kite) fill check ─────────────────────────────────────────────────

def check_ascent_fills(orders_df: pd.DataFrame) -> list[dict]:
    """Kite automated login is not available in CI (requires browser OAuth).

    Instead of a broken holdings comparison, send a Telegram reminder listing
    what was placed so JD can manually verify fills in the Kite app.
    Returns the placed orders as "pending verification" items.
    """
    if orders_df.empty:
        return []

    log.info("Ascent: Kite automated login unavailable in CI — returning orders for manual verification")
    result = []
    for _, row in orders_df.iterrows():
        result.append({
            "symbol": str(row["symbol"]).replace("-EQ", ""),
            "side": row["side"],
            "quantity": int(row["quantity"]),
            "actual_qty": None,  # unknown — manual check needed
            "order_id": row.get("order_id", ""),
            "timestamp": str(row["timestamp"]),
            "note": "manual Kite verification required",
        })
    return result


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

        strategy_dir = LIVE_DIR / STRATEGIES[strat]
        if strat == "bedrock":
            unfilled = check_angel_fills(orders_df, strategy_dir)
        else:
            unfilled = check_ascent_fills(orders_df)

        if unfilled:
            all_unfilled[strat] = unfilled
            for u in unfilled:
                if u.get("note") == "manual Kite verification required":
                    log.info(f"  PLACED (verify manually): {u['side']} {u['quantity']} {u['symbol']}  order_id={u['order_id']}")
                else:
                    log.warning(f"  UNFILLED: {u['side']} {u['quantity']} {u['symbol']}  expected={u['expected_qty']} actual={u['actual_qty']}")
        else:
            log.info(f"  {strat}: all orders filled")

    # ── Alert ────────────────────────────────────────────────────────────────
    # Separate true failures (Bedrock mismatch) from manual-check reminders (Ascent)
    real_failures: dict[str, list] = {}
    manual_check: dict[str, list] = {}
    for strat, orders in all_unfilled.items():
        for u in orders:
            if u.get("note") == "manual Kite verification required":
                manual_check.setdefault(strat, []).append(u)
            else:
                real_failures.setdefault(strat, []).append(u)

    if manual_check:
        lines = ["*JD Quant — Kite Fill Check*", "Verify these orders in the Kite app:\n"]
        for strat, orders in manual_check.items():
            lines.append(f"*{strat.upper()}* ({orders[0]['timestamp'][:10]})")
            for u in orders:
                lines.append(f"  {u['side']} {u['quantity']} × {u['symbol']}")
        lines.append("\nOpen Kite → Orders → check status.")
        send_telegram("\n".join(lines))
        print("\nAscent fill reminder sent via Telegram.")

    if real_failures:
        lines = ["*JD Quant — UNFILLED ORDERS*\n"]
        for strat, orders in real_failures.items():
            lines.append(f"*{strat.upper()}*")
            for u in orders:
                lines.append(
                    f"  {u['side']} {u['symbol']}: expected {u['expected_qty']} got {u['actual_qty']}"
                    f" — order `{u['order_id']}`"
                )
        lines.append("\nRe-run rebalance script to retry.")
        send_telegram("\n".join(lines))
        print("\nUNFILLED ORDERS DETECTED — Telegram alert sent")
        sys.exit(1)

    if not all_unfilled:
        log.info("All orders filled. No alert needed.")
        print("\nAll orders filled.")


if __name__ == "__main__":
    main()
