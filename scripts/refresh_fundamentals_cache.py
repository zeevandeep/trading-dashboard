"""Refresh the fundamentals cache from Screener.in.

Scrapes annual fundamental data (net income, equity, total debt, shares, revenue)
for all NSE 500 ex Nifty 50 tickers and saves to a parquet cache. The Bedrock
live rebalance reads from this cache — it never scrapes at execution time.

Run this quarterly, a few days before the rebalance. It takes ~10-15 minutes
for 168 tickers with auth cookies (faster than without).

── Auth cookies (recommended) ────────────────────────────────────────────────
Log into screener.in in your browser, then copy cookies:
  Chrome/Arc: DevTools → Application → Cookies → screener.in
  Copy values for: csrftoken, sessionid

Set as environment variables (or in .env):
    export SCREENER_CSRFTOKEN=<value>
    export SCREENER_SESSIONID=<value>

Without cookies, Screener.in rate-limits to ~0.5 req/s (very slow).
With cookies, it runs at ~2 req/s and rarely fails.

── Screener Pro (future) ─────────────────────────────────────────────────────
When scaling to large capital, upgrade to Screener.in Pro (~Rs 1500/yr).
Pro gives API access — replace _extract_from_screener() with a direct API
call and remove the cookie dependency entirely.

── Usage ─────────────────────────────────────────────────────────────────────
    # With env vars set:
    python scripts/refresh_fundamentals_cache.py

    # Pass cookies directly:
    python scripts/refresh_fundamentals_cache.py \\
        --csrftoken <value> --sessionid <value>

    # Refresh only specific tickers (for debugging):
    python scripts/refresh_fundamentals_cache.py --tickers GNFC PETRONET MCX

    # Preview what's in the cache without refreshing:
    python scripts/refresh_fundamentals_cache.py --status
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.data.universe import nifty50_tickers, nse500_starter_tickers
from trading.signals.value_quality import (
    set_screener_cookies,
    _extract_from_screener,
)
from trading.utils.logging import setup_logging

log = setup_logging("refresh_fundamentals")

CACHE_DIR = DATA_DIR / "cache" / "fundamentals"
CACHE_FILE = CACHE_DIR / "historical_fundamentals.parquet"


def load_cache() -> pd.DataFrame:
    if CACHE_FILE.exists():
        df = pd.read_parquet(CACHE_FILE)
        return df
    return pd.DataFrame()


def save_cache(df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_FILE, index=False)
    log.info(f"Cache saved: {len(df)} rows, {df['ticker'].nunique()} tickers → {CACHE_FILE}")


def cache_status() -> None:
    if not CACHE_FILE.exists():
        print("No cache found.")
        return

    df = load_cache()
    tickers = df["ticker"].unique()
    latest_per_ticker = df.groupby("ticker")["date"].max()

    print(f"\nFundamentals cache status")
    print(f"  File:     {CACHE_FILE}")
    print(f"  Tickers:  {len(tickers)}")
    print(f"  Rows:     {len(df)}")
    print(f"  Modified: {date.fromtimestamp(CACHE_FILE.stat().st_mtime)}")
    print(f"\n  Most recent data per ticker (top 20):")
    print(f"  {'Ticker':<15} {'Latest year-end'}")
    print(f"  {'-'*35}")
    for ticker, latest in sorted(latest_per_ticker.items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {ticker:<15} {latest}")
    print()


def refresh_tickers(tickers: list[str], force: bool = False) -> dict[str, pd.DataFrame]:
    """Scrape Screener.in for each ticker and return {ticker: DataFrame}."""
    results = {}
    failed = []

    for i, ticker in enumerate(tickers, 1):
        try:
            df = _extract_from_screener(ticker)
            if df is not None and len(df) >= 2:
                results[ticker] = df
                log.info(f"  [{i}/{len(tickers)}] {ticker}: {len(df)} years OK")
            else:
                log.warning(f"  [{i}/{len(tickers)}] {ticker}: no data")
                failed.append(ticker)
        except Exception as e:
            log.warning(f"  [{i}/{len(tickers)}] {ticker}: error — {e}")
            failed.append(ticker)

    if failed:
        log.warning(f"Failed ({len(failed)}): {', '.join(failed)}")

    return results


def merge_into_cache(existing: pd.DataFrame, new_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merge freshly scraped data into the existing cache.

    For each ticker: replace existing rows with new data (Screener is authoritative).
    Tickers not in new_data are left unchanged.
    """
    if not new_data:
        return existing

    new_rows = []
    for ticker, df in new_data.items():
        df = df.reset_index()  # bring date out of index
        df["ticker"] = ticker
        # Ensure column order matches cache
        df = df[["date", "net_income", "equity", "total_debt", "shares", "revenue", "ticker"]]
        new_rows.append(df)

    new_df = pd.concat(new_rows, ignore_index=True)

    if existing.empty:
        return new_df

    # Remove old rows for tickers being refreshed, then append new
    refreshed_tickers = set(new_data.keys())
    kept = existing[~existing["ticker"].isin(refreshed_tickers)]
    merged = pd.concat([kept, new_df], ignore_index=True)
    merged = merged.sort_values(["ticker", "date"]).reset_index(drop=True)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh fundamentals cache from Screener.in")
    parser.add_argument("--csrftoken", help="Screener.in csrftoken cookie (or set SCREENER_CSRFTOKEN env var)")
    parser.add_argument("--sessionid", help="Screener.in sessionid cookie (or set SCREENER_SESSIONID env var)")
    parser.add_argument("--tickers", nargs="+", help="Refresh only these tickers (default: full universe)")
    parser.add_argument("--force", action="store_true", help="Re-scrape even if cache is fresh")
    parser.add_argument("--status", action="store_true", help="Show cache status and exit")
    args = parser.parse_args()

    if args.status:
        cache_status()
        return

    # ── Auth cookies
    csrftoken = args.csrftoken or os.environ.get("SCREENER_CSRFTOKEN", "")
    sessionid = args.sessionid or os.environ.get("SCREENER_SESSIONID", "")

    if csrftoken and sessionid:
        set_screener_cookies(csrftoken, sessionid)
        log.info("Screener.in: authenticated mode (fast)")
    else:
        log.warning("Screener.in: unauthenticated mode — will be slow (~0.5 req/s). "
                    "Set SCREENER_CSRFTOKEN + SCREENER_SESSIONID env vars for faster scraping.")

    # ── Universe
    if args.tickers:
        tickers = args.tickers
    else:
        nifty50 = set(nifty50_tickers())
        tickers = [t for t in nse500_starter_tickers() if t not in nifty50]

    log.info(f"Refreshing fundamentals for {len(tickers)} tickers...")

    # ── Load existing cache
    existing = load_cache()
    if not existing.empty:
        log.info(f"Existing cache: {existing['ticker'].nunique()} tickers, {len(existing)} rows")

    # ── Scrape
    new_data = refresh_tickers(tickers, force=args.force)
    log.info(f"Scraped {len(new_data)}/{len(tickers)} tickers successfully")

    if not new_data:
        log.error("Nothing scraped — cache unchanged.")
        return

    # ── Merge and save
    updated = merge_into_cache(existing, new_data)
    save_cache(updated)

    # ── Summary
    print(f"\n{'='*50}")
    print(f"  Cache refreshed: {len(new_data)}/{len(tickers)} tickers updated")
    print(f"  Total in cache:  {updated['ticker'].nunique()} tickers, {len(updated)} rows")
    print(f"  Saved to:        {CACHE_FILE}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
