"""Daily mark for the trend-filtered Ascent paper portfolio.

Tracks what Ascent would look like with a NIFTY 10-month momentum filter:
  - RISK-ON  (NIFTY today > NIFTY 10 months ago): copy Ascent's daily NAV return
  - RISK-OFF (NIFTY today <= NIFTY 10 months ago): stay flat (cash, 0% return)

This gives a live apples-to-apples comparison vs the unfiltered live Ascent.
After 12-18 months of track record, decide whether to wire the filter in live.

Output: data/paper/ascent_trend_filtered/equity.csv

Columns: date, nav, regime (RISK_ON / RISK_OFF), ascent_nav, nifty_10m_ret

Usage:
    python scripts/trend_filter_paper_mark.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.utils.logging import setup_logging

log = setup_logging("trend_filter_paper")

PAPER_DIR = DATA_DIR / "paper" / "ascent_trend_filtered"
EQUITY_PATH = PAPER_DIR / "equity.csv"
ASCENT_EQUITY = DATA_DIR / "live" / "smallcap_momentum_v2_live" / "equity.csv"

NIFTY_TICKER = "^NSEI"
LOOKBACK_MONTHS = 10


def fetch_nifty(start: str) -> pd.Series:
    """Fetch NIFTY 50 daily closes from yfinance."""
    try:
        data = yf.download(NIFTY_TICKER, start=start, progress=False)
        if data.empty:
            return pd.Series(dtype=float)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = pd.to_datetime(close.index).normalize()
        return close.dropna()
    except Exception as e:
        log.warning(f"NIFTY fetch failed: {e}")
        return pd.Series(dtype=float)


def nifty_regime(nifty: pd.Series, date: pd.Timestamp) -> tuple[str, float]:
    """Return (RISK_ON|RISK_OFF, 10m_return_pct) for a given date."""
    # Find price 10 months ago (approx 210 trading days)
    lookback_date = date - pd.DateOffset(months=LOOKBACK_MONTHS)
    prior = nifty[nifty.index <= lookback_date]
    if prior.empty or date not in nifty.index:
        return "UNKNOWN", 0.0
    current = nifty[date]
    past = prior.iloc[-1]
    ret = (current / past - 1) * 100
    regime = "RISK_ON" if ret > 0 else "RISK_OFF"
    return regime, round(ret, 2)


def find_missing_dates(ascent_df: pd.DataFrame) -> list[str]:
    """Return dates present in Ascent equity but not yet in our paper equity."""
    if EQUITY_PATH.exists():
        paper_df = pd.read_csv(EQUITY_PATH)
        marked = set(paper_df["date"].astype(str))
    else:
        marked = set()

    ascent_dates = ascent_df["date"].astype(str).tolist()
    return [d for d in ascent_dates if d not in marked]


def main() -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)

    # Load Ascent live equity (source of truth for dates and daily returns)
    if not ASCENT_EQUITY.exists():
        log.error("Ascent live equity.csv not found — run daily_live_mark.py first")
        return

    ascent_df = pd.read_csv(ASCENT_EQUITY).sort_values("date").reset_index(drop=True)
    if ascent_df.empty:
        log.info("Ascent equity.csv is empty")
        return

    missing = find_missing_dates(ascent_df)
    if not missing:
        log.info("Trend filter paper: already up to date")
        return

    # Fetch enough NIFTY history for 10-month lookback
    fetch_start = (pd.Timestamp(missing[0]) - pd.DateOffset(months=LOOKBACK_MONTHS + 1)).strftime("%Y-%m-%d")
    log.info(f"Fetching NIFTY from {fetch_start}...")
    nifty = fetch_nifty(fetch_start)
    if nifty.empty:
        log.warning("Could not fetch NIFTY data")
        return

    # Load existing paper equity for NAV chaining
    if EQUITY_PATH.exists():
        paper_df = pd.read_csv(EQUITY_PATH)
        last_nav = float(paper_df.iloc[-1]["nav"])
    else:
        paper_df = pd.DataFrame()
        last_nav = 1.0

    new_rows = []
    for date_str in missing:
        dt = pd.Timestamp(date_str)

        # Get Ascent's daily NAV return for this date
        ascent_row = ascent_df[ascent_df["date"] == date_str]
        if ascent_row.empty:
            continue
        ascent_nav = float(ascent_row.iloc[0]["nav"])

        # Get previous Ascent NAV for daily return calculation
        idx = ascent_df[ascent_df["date"] == date_str].index[0]
        if idx == 0:
            ascent_daily_ret = 0.0
        else:
            prev_ascent_nav = float(ascent_df.iloc[idx - 1]["nav"])
            ascent_daily_ret = (ascent_nav / prev_ascent_nav) - 1 if prev_ascent_nav > 0 else 0.0

        # Check NIFTY regime
        regime, nifty_10m_ret = nifty_regime(nifty, dt)

        # Apply return: RISK_ON copies Ascent, RISK_OFF stays flat
        if regime == "RISK_ON":
            new_nav = last_nav * (1 + ascent_daily_ret)
        else:
            new_nav = last_nav  # cash — no return

        new_rows.append({
            "date": date_str,
            "nav": round(new_nav, 6),
            "regime": regime,
            "ascent_nav": round(ascent_nav, 6),
            "nifty_10m_ret": nifty_10m_ret,
        })
        last_nav = new_nav

    if not new_rows:
        log.info("No new rows to add")
        return

    new_df = pd.DataFrame(new_rows)
    if paper_df.empty:
        new_df.to_csv(EQUITY_PATH, index=False)
    else:
        new_df.to_csv(EQUITY_PATH, mode="a", header=False, index=False)

    # Sort and deduplicate
    full_df = pd.read_csv(EQUITY_PATH).sort_values("date").drop_duplicates(subset=["date"])
    full_df.to_csv(EQUITY_PATH, index=False)

    latest = new_rows[-1]
    nav_pct = (latest["nav"] - 1.0) * 100
    log.info(
        f"Trend filter paper: marked {len(new_rows)} day(s) | "
        f"NAV {nav_pct:+.2f}% | regime={latest['regime']} | "
        f"NIFTY 10m={latest['nifty_10m_ret']:+.1f}%"
    )


if __name__ == "__main__":
    main()
