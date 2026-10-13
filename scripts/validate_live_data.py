"""Validate live strategy data integrity.

Catches data issues before they corrupt NAV history:
  1. equity.csv: NAV continuity, no resets, invested matches capital events
  2. orders.csv: schema, no NaN in placed BUYs, no duplicates
  3. capital_events.csv: dates match invested changes in equity.csv
  4. positions.csv: no cost_basis=0 for placed BUYs
  5. kite_snapshot: epoch_start is consistent

Run manually or automatically after daily mark:
    python scripts/validate_live_data.py
    python scripts/validate_live_data.py --strategy smallcap_momentum_v2_live
    python scripts/validate_live_data.py --strict   # exit 1 on any warning
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.utils.logging import setup_logging

log = setup_logging("validate")

LIVE_DIR = DATA_DIR / "live"
ORDERS_SCHEMA = ["symbol", "side", "quantity", "estimated_value",
                 "order_id", "status", "limit_price", "timestamp"]


# ── Result collector ──────────────────────────────────────────────────────────

class Results:
    def __init__(self, strategy: str):
        self.strategy = strategy
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        log.error(f"[{self.strategy}] ERROR: {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        log.warning(f"[{self.strategy}] WARN: {msg}")

    def ok(self, msg: str) -> None:
        log.info(f"[{self.strategy}] OK: {msg}")

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


# ── Individual checks ─────────────────────────────────────────────────────────

def check_orders(r: Results, strategy_dir: Path) -> pd.DataFrame | None:
    path = strategy_dir / "orders.csv"
    if not path.exists():
        r.warn("orders.csv not found")
        return None

    df = pd.read_csv(path)

    # Schema columns
    missing_cols = [c for c in ORDERS_SCHEMA if c not in df.columns]
    if missing_cols:
        r.error(f"orders.csv missing columns: {missing_cols}")
        return df
    r.ok(f"orders.csv schema valid ({len(df)} rows)")

    placed = df[df["status"] == "placed"].copy()

    # No NaN timestamps in placed orders
    bad_ts = placed[placed["timestamp"].isna()]
    if not bad_ts.empty:
        r.error(f"orders.csv: {len(bad_ts)} placed order(s) have NaN timestamp — "
                f"column-shift bug. Symbols: {bad_ts['symbol'].tolist()}")

    # No NaN estimated_value in placed BUYs
    placed_buys = placed[placed["side"] == "BUY"]
    nan_ev = placed_buys[placed_buys["estimated_value"].isna()]
    if not nan_ev.empty:
        r.error(f"orders.csv: {len(nan_ev)} placed BUY(s) have NaN estimated_value — "
                f"cost_basis will be 0. Symbols: {nan_ev['symbol'].tolist()}")
    else:
        r.ok("orders.csv: all placed BUYs have estimated_value")

    # Duplicate placed orders (same symbol+side+date) — symptom of retry double-booking
    placed["date"] = placed["timestamp"].str[:10]
    dupes = placed.groupby(["symbol", "side", "date"]).size()
    dupes = dupes[dupes > 1]
    if not dupes.empty:
        r.warn(f"orders.csv: {len(dupes)} duplicate placed orders (same symbol/side/date) — "
               f"may cause inflated holdings. Check: {dupes.index.tolist()[:5]}")

    return df


def check_capital_events(r: Results, strategy_dir: Path) -> pd.DataFrame | None:
    path = strategy_dir / "capital_events.csv"
    if not path.exists():
        r.warn("capital_events.csv not found — NAV and invested will use cost_basis fallback")
        return None

    df = pd.read_csv(path)
    df["date"] = df["date"].astype(str)

    # No duplicate dates
    dupes = df[df.duplicated("date")]
    if not dupes.empty:
        r.error(f"capital_events.csv: duplicate dates {dupes['date'].tolist()}")

    r.ok(f"capital_events.csv: {len(df)} event(s), total Rs.{df['amount'].sum():,.0f}")
    return df


def check_equity(r: Results, strategy_dir: Path,
                 capital_events: pd.DataFrame | None) -> None:
    path = strategy_dir / "equity.csv"
    if not path.exists():
        r.warn("equity.csv not found — strategy not yet marked")
        return

    eq = pd.read_csv(path)
    if eq.empty:
        r.warn("equity.csv is empty")
        return

    eq["date"] = eq["date"].astype(str)

    # Sorted and unique dates
    if not eq["date"].is_monotonic_increasing:
        r.error("equity.csv: dates are not in ascending order")
    dupe_dates = eq[eq.duplicated("date")]
    if not dupe_dates.empty:
        r.error(f"equity.csv: duplicate dates {dupe_dates['date'].tolist()}")

    # NAV never resets to 1.0 after row 0
    nav_resets = eq.iloc[1:][eq.iloc[1:]["nav"].round(4) == 1.0]
    if not nav_resets.empty:
        r.error(f"equity.csv: NAV reset to 1.0 on {nav_resets['date'].tolist()} — "
                f"capital addition was not chain-linked. Run record_capital_event.py "
                f"with --recompute to fix.")

    # NAV daily change > 25% without a capital event is suspicious
    if capital_events is not None:
        cap_dates = set(capital_events["date"].astype(str))
    else:
        cap_dates = set()

    for i in range(1, len(eq)):
        prev = eq.iloc[i - 1]
        curr = eq.iloc[i]
        if curr["date"] in cap_dates:
            continue
        if prev["nav"] > 0:
            chg = abs(curr["nav"] / prev["nav"] - 1)
            if chg > 0.25:
                r.error(f"equity.csv: NAV changed {chg*100:.1f}% on {curr['date']} "
                        f"with no capital event — likely wrong snapshot epoch or bad price data")

    # invested column should match cumulative capital events
    if capital_events is not None:
        for _, row in eq.iterrows():
            expected_invested = float(
                capital_events.loc[capital_events["date"] <= row["date"], "amount"].sum()
            )
            actual_invested = float(row["invested"])
            if abs(actual_invested - expected_invested) > 1:
                r.error(f"equity.csv: invested on {row['date']} is Rs.{actual_invested:,.2f} "
                        f"but capital_events sum to Rs.{expected_invested:,.2f} — "
                        f"capital event date is wrong or missing")
                break  # Only report first mismatch

    # n_positions > 0 on all rows
    zero_pos = eq[eq["n_positions"] == 0]
    if not zero_pos.empty:
        r.warn(f"equity.csv: n_positions=0 on {zero_pos['date'].tolist()}")

    last = eq.iloc[-1]
    r.ok(f"equity.csv: {len(eq)} rows | latest {last['date']} | "
         f"NAV={last['nav']:.4f} ({(last['nav']-1)*100:+.1f}%) | "
         f"MV=Rs.{last['market_value']:,.0f}")


def check_positions(r: Results, strategy_dir: Path,
                    orders_df: pd.DataFrame | None) -> None:
    path = strategy_dir / "positions.csv"
    if not path.exists():
        r.warn("positions.csv not found")
        return

    pos = pd.read_csv(path)
    if pos.empty:
        return

    # No cost_basis=0 for any position
    zero_cb = pos[(pos["cost_basis"] == 0) & (pos["quantity"] > 0)]
    if not zero_cb.empty:
        symbols = zero_cb["symbol"].unique().tolist()
        r.error(f"positions.csv: cost_basis=0 for {symbols} — "
                f"check orders.csv estimated_value for their BUY orders")
    else:
        r.ok("positions.csv: all cost_basis > 0")

    # Latest date should match equity.csv latest (they're written together)
    equity_path = strategy_dir / "equity.csv"
    if equity_path.exists():
        eq = pd.read_csv(equity_path)
        if not eq.empty:
            eq_last = eq.iloc[-1]["date"]
            pos_last = pos["date"].max()
            if str(pos_last) != str(eq_last):
                r.warn(f"positions.csv last date ({pos_last}) != equity.csv last date ({eq_last})")


def check_snapshot(r: Results, strategy_dir: Path,
                   capital_events: pd.DataFrame | None) -> None:
    snap_path = None
    for name in ("kite_snapshot.json", "holdings_snapshot.json"):
        p = strategy_dir / name
        if p.exists():
            snap_path = p
            break

    if snap_path is None:
        r.warn("No portfolio snapshot found (kite_snapshot.json / holdings_snapshot.json)")
        return

    with open(snap_path) as f:
        snap = json.load(f)

    snap_date = snap.get("date", "")
    epoch_start = snap.get("epoch_start", snap_date)

    # epoch_start must be <= snapshot date
    if epoch_start > snap_date:
        r.error(f"snapshot: epoch_start={epoch_start} is AFTER snapshot date={snap_date} — impossible")

    # epoch_start should correspond to a capital event date (or the strategy start)
    if capital_events is not None:
        cap_dates = set(capital_events["date"].astype(str))
        if epoch_start not in cap_dates:
            r.warn(f"snapshot: epoch_start={epoch_start} has no matching capital event — "
                   f"verify this is correct. Known capital dates: {sorted(cap_dates)}")
        else:
            r.ok(f"snapshot: epoch_start={epoch_start} matches a capital event ✓")

    holdings = snap.get("holdings", {})
    active = {s: h for s, h in holdings.items() if h.get("quantity", 0) > 0}
    r.ok(f"snapshot: {snap_date} | epoch_start={epoch_start} | {len(active)} holdings")


# ── Main ──────────────────────────────────────────────────────────────────────

def validate_strategy(strategy: str) -> Results:
    r = Results(strategy)
    strategy_dir = LIVE_DIR / strategy

    if not strategy_dir.exists():
        r.error(f"Strategy directory not found: {strategy_dir}")
        return r

    log.info(f"── Validating {strategy} ──")
    orders_df    = check_orders(r, strategy_dir)
    capital_ev   = check_capital_events(r, strategy_dir)
    check_equity(r, strategy_dir, capital_ev)
    check_positions(r, strategy_dir, orders_df)
    check_snapshot(r, strategy_dir, capital_ev)
    return r


def find_live_strategies() -> list[str]:
    if not LIVE_DIR.exists():
        return []
    return [p.name for p in LIVE_DIR.iterdir()
            if p.is_dir() and (p / "orders.csv").exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate live strategy data integrity")
    parser.add_argument("--strategy", help="Validate only this strategy")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any error is found (use in CI)")
    args = parser.parse_args()

    strategies = [args.strategy] if args.strategy else find_live_strategies()
    if not strategies:
        log.info("No live strategies found.")
        return

    all_results = [validate_strategy(s) for s in strategies]

    print("\n" + "═" * 60)
    print("  VALIDATION SUMMARY")
    print("═" * 60)
    any_error = False
    for r in all_results:
        status = "✓ PASS" if r.passed else "✗ FAIL"
        print(f"\n  {status}  {r.strategy}")
        for e in r.errors:
            print(f"    ERROR  {e}")
        for w in r.warnings:
            print(f"    WARN   {w}")
        if not r.errors and not r.warnings:
            print("    All checks passed.")
        if not r.passed:
            any_error = True
    print("\n" + "═" * 60)

    if any_error and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
