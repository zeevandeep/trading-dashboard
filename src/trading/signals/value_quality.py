"""Value + Quality composite signal.

Scores stocks on four factors:
  1. Earnings Yield (E/P) — higher = cheaper = better
  2. Return on Equity (ROE) — higher = better business
  3. Debt/Equity — lower = safer (inverted so higher rank = better)
  4. Earnings Growth — higher = growing faster

Each factor is cross-sectionally ranked (percentile), then combined into
an equal-weighted composite score. Stocks with missing data on any factor
are excluded.

Data source: yfinance .info endpoint (point-in-time fundamentals).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from trading.utils.logging import setup_logging

log = setup_logging("value_quality")


def fetch_fundamentals(tickers: list[str], max_workers: int = 10) -> pd.DataFrame:
    """Fetch fundamental data for a list of tickers.

    Returns DataFrame with columns: ticker, pe, roe, de, earnings_growth, revenue_growth, market_cap.
    """
    results = []

    def _fetch_one(ticker: str) -> dict | None:
        try:
            yf_ticker = f"{ticker}.NS" if not ticker.endswith((".NS", ".BO")) else ticker
            info = yf.Ticker(yf_ticker).info
            if not info or info.get("regularMarketPrice") is None:
                return None
            return {
                "ticker": ticker,
                "pe": info.get("trailingPE"),
                "roe": info.get("returnOnEquity"),
                "de": info.get("debtToEquity"),
                "earnings_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
                "market_cap": info.get("marketCap"),
            }
        except Exception:
            return None

    log.info(f"Fetching fundamentals for {len(tickers)} tickers...")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 25 == 0:
                log.info(f"  {done}/{len(tickers)} fetched...")
            result = future.result()
            if result:
                results.append(result)

    df = pd.DataFrame(results).set_index("ticker")
    log.info(f"Got fundamentals for {len(df)}/{len(tickers)} tickers")
    return df


def score_value_quality(fundamentals: pd.DataFrame) -> pd.Series:
    """Compute composite Value + Quality score.

    Returns a Series of scores indexed by ticker, higher = better.
    Stocks with missing data on key factors are dropped.
    """
    df = fundamentals.copy()

    # Compute Earnings Yield (inverse of P/E)
    df["earnings_yield"] = 1.0 / df["pe"]

    # Keep only stocks with all required factors
    required = ["earnings_yield", "roe", "de", "earnings_growth"]
    df = df.dropna(subset=required)

    # Remove negative P/E (loss-making companies)
    df = df[df["pe"] > 0]

    # Remove extreme outliers (top/bottom 1%)
    for col in required:
        lower = df[col].quantile(0.01)
        upper = df[col].quantile(0.99)
        df = df[(df[col] >= lower) & (df[col] <= upper)]

    if len(df) < 10:
        log.warning(f"Only {len(df)} stocks after filtering — too few for ranking")
        return pd.Series(dtype=float)

    # Rank each factor (percentile rank 0-1)
    # Higher is better for: earnings_yield, roe, earnings_growth
    # Lower is better for: de (so we invert)
    df["rank_ey"] = df["earnings_yield"].rank(pct=True)
    df["rank_roe"] = df["roe"].rank(pct=True)
    df["rank_de"] = (1.0 - df["de"].rank(pct=True))  # invert: low debt = high rank
    df["rank_eg"] = df["earnings_growth"].rank(pct=True)

    # Equal-weighted composite
    df["composite"] = (
        df["rank_ey"] + df["rank_roe"] + df["rank_de"] + df["rank_eg"]
    ) / 4.0

    scores = df["composite"].sort_values(ascending=False)
    log.info(f"Scored {len(scores)} stocks. Top 5: {list(scores.head().index)}")

    return scores
