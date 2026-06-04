"""Price data loader — pulls historical OHLCV from yfinance and caches as parquet.

Free data source. For research and paper trading this is sufficient. When we move
to production we'll add a Kite Connect loader that uses authoritative exchange data.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from trading.config import CACHE_DIR
from trading.data.universe import to_yfinance_ticker
from trading.utils.logging import setup_logging

log = setup_logging("data.loader")


def _cache_path(ticker: str) -> Path:
    """Where we store the cached parquet for a single ticker."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe}.parquet"


def fetch_one(
    ticker: str,
    start: str = "2010-01-01",
    end: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch one ticker's OHLCV. Uses cache unless force_refresh=True.

    Returns DataFrame indexed by date with columns [open, high, low, close, adj_close, volume].
    Empty DataFrame on failure.
    """
    yf_ticker = to_yfinance_ticker(ticker)
    cache_file = _cache_path(yf_ticker)

    if cache_file.exists() and not force_refresh:
        try:
            df = pd.read_parquet(cache_file)
            if not df.empty:
                return df
        except Exception as e:
            log.warning(f"Cache read failed for {yf_ticker}: {e}. Refetching.")

    try:
        raw = yf.download(
            yf_ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception as e:
        log.error(f"yfinance download failed for {yf_ticker}: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        log.warning(f"No data returned for {yf_ticker}")
        return pd.DataFrame()

    # yfinance returns MultiIndex columns when threads=True or single-level otherwise; normalize
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )[["open", "high", "low", "close", "adj_close", "volume"]]

    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"

    df.to_parquet(cache_file)
    return df


def fetch_many(
    tickers: list[str],
    start: str = "2010-01-01",
    end: str | None = None,
    force_refresh: bool = False,
    sleep_between: float = 0.1,
) -> dict[str, pd.DataFrame]:
    """Fetch many tickers. Returns dict of ticker (bare, no suffix) -> DataFrame."""
    out: dict[str, pd.DataFrame] = {}
    for tkr in tqdm(tickers, desc="Fetching prices"):
        df = fetch_one(tkr, start=start, end=end, force_refresh=force_refresh)
        if not df.empty:
            out[tkr] = df
        if sleep_between > 0:
            time.sleep(sleep_between)  # be polite to yfinance
    log.info(f"Fetched {len(out)}/{len(tickers)} tickers successfully")
    return out


def to_price_panel(
    price_dict: dict[str, pd.DataFrame], field: str = "adj_close"
) -> pd.DataFrame:
    """Convert {ticker: OHLCV df} to a single wide DataFrame (date x ticker) for one field.

    Uses adj_close by default (accounts for splits/dividends) — essential for momentum.
    """
    series = {t: df[field].rename(t) for t, df in price_dict.items() if field in df.columns}
    panel = pd.concat(series.values(), axis=1)
    panel.columns = list(series.keys())
    panel = panel.sort_index()
    return panel


def fetch_benchmark(symbol: str = "^NSEI", start: str = "2010-01-01") -> pd.DataFrame:
    """Fetch a benchmark index (default: Nifty 50 = ^NSEI). Used for trend filter."""
    try:
        raw = yf.download(symbol, start=start, progress=False, auto_adjust=False, threads=False)
    except Exception as e:
        log.error(f"Benchmark fetch failed for {symbol}: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    return df
