"""Momentum signal — Jegadeesh-Titman 12-month minus 1-month cross-sectional momentum.

Formula: return over trailing 12 months, skipping the most recent month.
Rationale: the most recent month exhibits short-term reversal (Jegadeesh 1990),
which is noise for medium-term momentum. Skipping it improves the signal.

Also includes absolute trend filter — a regime gate at the index level.
"""

from __future__ import annotations

import pandas as pd

# Trading-day conventions (NSE ~ 252 sessions/year)
DAYS_PER_YEAR = 252
DAYS_PER_MONTH = 21


def momentum_12m_1m(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute 12-month minus 1-month momentum for a price panel.

    prices: wide DataFrame (date x ticker) of adjusted close prices
    returns: wide DataFrame (date x ticker) of momentum scores.
             NaN for dates with insufficient history.

    Score at date t = (price[t - 21] / price[t - 252]) - 1
    """
    lookback = 12 * DAYS_PER_MONTH  # ~252
    skip = DAYS_PER_MONTH  # 21

    # Price 1 month ago and 12 months ago
    recent = prices.shift(skip)
    far = prices.shift(lookback)

    mom = (recent / far) - 1.0
    return mom


def momentum_n_m(prices: pd.DataFrame, lookback_months: int = 12, skip_months: int = 1) -> pd.DataFrame:
    """Generalized momentum: n-month minus k-month (skip the most recent k months)."""
    lookback = lookback_months * DAYS_PER_MONTH
    skip = skip_months * DAYS_PER_MONTH
    recent = prices.shift(skip)
    far = prices.shift(lookback)
    return (recent / far) - 1.0


def absolute_trend_filter(benchmark_prices: pd.Series, sma_window: int = 200) -> pd.Series:
    """Return a boolean Series: True when benchmark is above its SMA (risk-on)."""
    sma = benchmark_prices.rolling(window=sma_window, min_periods=sma_window).mean()
    return benchmark_prices > sma


def rank_cross_section(scores: pd.DataFrame, ascending: bool = False) -> pd.DataFrame:
    """Rank scores across tickers at each date. ascending=False => higher score = rank 1 (best)."""
    return scores.rank(axis=1, ascending=ascending, method="first")
