"""Unit tests for the momentum signal module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading.signals.momentum import (
    absolute_trend_filter,
    momentum_12m_1m,
    momentum_n_m,
    rank_cross_section,
)


def _synthetic_prices(n_days: int = 500, n_tickers: int = 5, seed: int = 42) -> pd.DataFrame:
    """Generate a price panel for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    # Random walk prices starting at 100
    rets = rng.normal(0.0005, 0.015, size=(n_days, n_tickers))
    prices = 100 * (1 + pd.DataFrame(rets)).cumprod()
    prices.index = dates
    prices.columns = [f"T{i}" for i in range(n_tickers)]
    return prices


def test_momentum_12m_1m_shape_and_nans():
    prices = _synthetic_prices(n_days=400, n_tickers=3)
    mom = momentum_12m_1m(prices)
    assert mom.shape == prices.shape
    # First 252 rows should be NaN (insufficient lookback)
    assert mom.iloc[:252].isna().all().all()
    # Rows beyond lookback should have values
    assert mom.iloc[260:].notna().any().any()


def test_momentum_n_m_respects_lookback():
    prices = _synthetic_prices(n_days=300, n_tickers=2)
    mom_6_1 = momentum_n_m(prices, lookback_months=6, skip_months=1)
    mom_12_1 = momentum_n_m(prices, lookback_months=12, skip_months=1)
    # 6-month lookback needs less history than 12-month
    assert mom_6_1.notna().sum().sum() > mom_12_1.notna().sum().sum()


def test_rank_cross_section_ordering():
    # Build a score panel where we know the ranks
    dates = pd.bdate_range("2024-01-01", periods=3)
    scores = pd.DataFrame(
        [[0.10, 0.20, 0.30], [0.30, 0.20, 0.10], [0.25, 0.25, 0.25]],
        index=dates,
        columns=["A", "B", "C"],
    )
    ranks = rank_cross_section(scores, ascending=False)
    # Day 1: C highest, A lowest -> C=1, B=2, A=3
    assert ranks.iloc[0]["C"] == 1
    assert ranks.iloc[0]["A"] == 3


def test_absolute_trend_filter_logic():
    # Uptrending series: after the SMA window, should be above SMA
    dates = pd.bdate_range("2020-01-01", periods=400)
    prices = pd.Series(range(100, 500), index=dates, dtype=float)
    risk_on = absolute_trend_filter(prices, sma_window=100)
    # Early dates: SMA not computed -> NaN, which is Falsy but our filter returns boolean
    # After window, monotonic uptrend means above SMA
    assert bool(risk_on.iloc[150]) is True
    assert bool(risk_on.iloc[350]) is True


def test_absolute_trend_filter_downtrend():
    dates = pd.bdate_range("2020-01-01", periods=400)
    prices = pd.Series(range(500, 100, -1), index=dates, dtype=float)
    risk_on = absolute_trend_filter(prices, sma_window=100)
    # Monotonic downtrend: should be below SMA
    assert bool(risk_on.iloc[150]) is False
    assert bool(risk_on.iloc[350]) is False
