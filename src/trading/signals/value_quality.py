"""Value + Quality composite signal.

Scores stocks on four factors:
  1. Earnings Yield (E/P) — higher = cheaper = better
  2. Return on Equity (ROE) — higher = better business
  3. Debt/Equity — lower = safer (inverted so higher rank = better)
  4. Earnings Growth — higher = growing faster

Each factor is cross-sectionally ranked (percentile), then combined into
an equal-weighted composite score. Stocks with missing data on any factor
are excluded.

Two modes:
  - **Live** (fetch_fundamentals): uses yfinance .info for current snapshot.
  - **Historical** (fetch_historical_fundamentals): uses yfinance annual
    financial statements (income_stmt + balance_sheet) for backtesting.
    Indian companies report March year-end; results are public by ~June,
    so a 3-month reporting lag is applied for point-in-time correctness.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
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


# ═══════════════════════════════════════════════════════════════════════════════
#  HISTORICAL FUNDAMENTALS (for backtesting)
# ═══════════════════════════════════════════════════════════════════════════════

REPORTING_LAG_MONTHS = 3  # Indian companies: March YE, results public by ~June


def _extract_annual_fundamentals(ticker: str) -> pd.DataFrame | None:
    """Pull annual income statement + balance sheet from yfinance.

    Returns a DataFrame indexed by fiscal year-end date with columns:
    net_income, equity, total_debt, shares, revenue.
    """
    try:
        yf_ticker = f"{ticker}.NS" if not ticker.endswith((".NS", ".BO")) else ticker
        tk = yf.Ticker(yf_ticker)
        inc = tk.income_stmt
        bs = tk.balance_sheet

        if inc is None or bs is None or inc.empty or bs.empty:
            return None

        rows = []
        for dt in inc.columns:
            ni = inc.at["Net Income", dt] if "Net Income" in inc.index else np.nan
            rev = inc.at["Total Revenue", dt] if "Total Revenue" in inc.index else np.nan

            if dt not in bs.columns:
                continue

            eq = bs.at["Stockholders Equity", dt] if "Stockholders Equity" in bs.index else np.nan
            debt = bs.at["Total Debt", dt] if "Total Debt" in bs.index else np.nan
            shares = bs.at["Share Issued", dt] if "Share Issued" in bs.index else np.nan

            rows.append({
                "date": dt,
                "net_income": ni,
                "equity": eq,
                "total_debt": debt,
                "shares": shares,
                "revenue": rev,
            })

        if not rows:
            return None

        df = pd.DataFrame(rows).set_index("date").sort_index()
        return df

    except Exception:
        return None


def fetch_historical_fundamentals(
    tickers: list[str],
    max_workers: int = 10,
    cache_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch annual financial statements for all tickers.

    Returns {ticker: DataFrame} where each DataFrame has columns:
    net_income, equity, total_debt, shares, revenue — indexed by fiscal year-end.

    Results are cached to parquet if cache_dir is provided.
    """
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "historical_fundamentals.parquet"
        if cache_file.exists():
            log.info(f"Loading cached historical fundamentals from {cache_file}")
            all_df = pd.read_parquet(cache_file)
            result = {}
            for ticker in all_df["ticker"].unique():
                result[ticker] = all_df[all_df["ticker"] == ticker].drop(columns=["ticker"]).set_index("date")
            log.info(f"Loaded cached fundamentals for {len(result)} tickers")
            return result

    result: dict[str, pd.DataFrame] = {}

    def _fetch(t: str) -> tuple[str, pd.DataFrame | None]:
        return t, _extract_annual_fundamentals(t)

    log.info(f"Fetching historical fundamentals for {len(tickers)} tickers...")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, t): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 25 == 0:
                log.info(f"  {done}/{len(tickers)} fetched...")
            ticker, df = future.result()
            if df is not None and len(df) >= 2:
                result[ticker] = df

    log.info(f"Got historical fundamentals for {len(result)}/{len(tickers)} tickers")

    if cache_dir is not None and result:
        frames = []
        for ticker, df in result.items():
            tmp = df.reset_index()
            tmp["ticker"] = ticker
            frames.append(tmp)
        pd.concat(frames, ignore_index=True).to_parquet(cache_file)
        log.info(f"Cached to {cache_file}")

    return result


def compute_historical_scores(
    fundamentals: dict[str, pd.DataFrame],
    prices: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Compute V+Q scores at each rebalance date using point-in-time data.

    Parameters
    ----------
    fundamentals: {ticker: DataFrame} from fetch_historical_fundamentals
    prices: wide DataFrame (date x ticker) of adjusted close prices
    rebalance_dates: dates at which to score (quarterly month-ends)

    Returns
    -------
    DataFrame (date x ticker) of composite V+Q scores, same shape convention
    as momentum scores — can be fed directly into top_n_equal_weight().
    """
    all_scores = {}

    # Find the earliest date any ticker has 2+ annual reports (minimum for YoY growth)
    earliest_usable = None
    for fdf in fundamentals.values():
        if len(fdf) >= 2:
            second_report = fdf.index[1]
            available_from = second_report + pd.DateOffset(months=REPORTING_LAG_MONTHS)
            if earliest_usable is None or available_from < earliest_usable:
                earliest_usable = available_from
    if earliest_usable is not None:
        rebalance_dates = rebalance_dates[rebalance_dates >= earliest_usable]
        log.info(f"Fundamental data available from {earliest_usable.date()}, {len(rebalance_dates)} rebalance dates to score")

    for rebal_date in rebalance_dates:
        # Point-in-time cutoff: only use financials reported before this date
        # Indian companies have ~3 month reporting lag from fiscal year-end
        cutoff = rebal_date - pd.DateOffset(months=REPORTING_LAG_MONTHS)

        fund_snapshot = {}
        for ticker, fdf in fundamentals.items():
            # Get the two most recent annual reports available by cutoff
            available = fdf[fdf.index <= cutoff]
            if len(available) < 2:
                continue

            latest = available.iloc[-1]
            prev = available.iloc[-2]

            ni = latest["net_income"]
            eq = latest["equity"]
            debt = latest["total_debt"]
            shares = latest["shares"]
            ni_prev = prev["net_income"]

            if pd.isna(ni) or pd.isna(eq) or eq <= 0 or pd.isna(shares) or shares <= 0:
                continue

            # EPS and P/E from price
            eps = ni / shares
            if eps <= 0:
                continue

            # Get price at rebalance date
            if ticker not in prices.columns:
                continue
            price_at = prices[ticker].loc[:rebal_date].dropna()
            if price_at.empty:
                continue
            price = float(price_at.iloc[-1])
            if price <= 0:
                continue

            pe = price / eps
            roe = ni / eq
            de = (debt / eq) if pd.notna(debt) else 0.0
            eg = (ni - ni_prev) / abs(ni_prev) if pd.notna(ni_prev) and abs(ni_prev) > 0 else np.nan

            fund_snapshot[ticker] = {
                "pe": pe, "roe": roe, "de": de, "earnings_growth": eg,
            }

        if len(fund_snapshot) < 10:
            log.warning(f"{rebal_date.date()}: only {len(fund_snapshot)} stocks with data, skipping")
            continue

        # Score using the same logic as score_value_quality
        df = pd.DataFrame(fund_snapshot).T
        scores = score_value_quality(df)
        if not scores.empty:
            all_scores[rebal_date] = scores

    if not all_scores:
        log.warning("No valid scoring dates — empty result")
        return pd.DataFrame()

    # Build wide DataFrame: (date x ticker), forward-filled daily for the backtest engine
    score_df = pd.DataFrame(all_scores).T.sort_index()
    score_df.index.name = "date"
    log.info(
        f"Historical V+Q scores: {len(score_df)} rebalance dates, "
        f"~{score_df.notna().sum(axis=1).mean():.0f} stocks scored per date"
    )
    return score_df
