"""Universe definition — which stocks we consider investable.

Two modes:
1. **Survivor-only** (original): current NSE 500 ex Nifty 50.
   Fast, simple, but survivorship-biased.

2. **Survivorship-bias-free** (new): current NSE 500 ex Nifty 50 PLUS
   historically significant stocks that were removed from the index
   (crashed, delisted, restructured). These dead stocks are loaded from
   ``data/universe/nse500_dead.csv`` and their price histories (including
   crashes to zero) are included in the backtest. The momentum signal
   naturally handles missing data via NaN — a stock only enters the
   investable set once it has enough price history, and exits when it
   stops trading.

   Per academic research (arxiv:2603.19380), survivorship bias inflates
   Indian smallcap index returns by ~4.9% CAGR (23.3%) and Sharpe by
   0.097 (9.1%). Including dead stocks gives honest numbers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading.config import UNIVERSE_DIR


def load_ticker_list(csv_name: str) -> list[str]:
    """Load a flat list of tickers from a CSV under data/universe/."""
    path = UNIVERSE_DIR / csv_name
    if not path.exists():
        raise FileNotFoundError(f"Universe CSV not found: {path}")
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        raise ValueError(f"{path} must have a 'ticker' column")
    return df["ticker"].dropna().str.strip().str.upper().tolist()


def nifty50_tickers() -> list[str]:
    """Nifty 50 constituents (for exclusion from smallcap universe)."""
    return load_ticker_list("nifty50.csv")


def nse500_starter_tickers() -> list[str]:
    """NSE 500 starter universe (expandable — paste more tickers into CSV)."""
    return load_ticker_list("nse500_starter.csv")


def dead_stock_tickers() -> list[str]:
    """Historically significant NSE 500 stocks that were removed/delisted/crashed.

    These are included in survivorship-bias-free backtests so that stocks
    which would have been picked by momentum and then crashed are properly
    accounted for.
    """
    path = UNIVERSE_DIR / "nse500_dead.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        return []
    return df["ticker"].dropna().str.strip().str.upper().tolist()


def smallcap_universe(include_dead: bool = False) -> list[str]:
    """NSE 500 ex Nifty 50 — the investable smallcap/midcap universe.

    Parameters
    ----------
    include_dead: if True, also include historically significant stocks
                  that were removed from the index (survivorship-bias-free mode).

    Returns tickers WITHOUT exchange suffix (e.g. 'RELIANCE', not 'RELIANCE.NS').
    The data loader adds the suffix when querying yfinance.
    """
    big = set(nifty50_tickers())
    all_names = set(nse500_starter_tickers())

    if include_dead:
        all_names |= set(dead_stock_tickers())

    return sorted([t for t in all_names if t not in big])


def to_yfinance_ticker(symbol: str, exchange: str = "NS") -> str:
    """Convert a bare NSE symbol to yfinance format ('RELIANCE' -> 'RELIANCE.NS')."""
    symbol = symbol.strip().upper()
    if "." in symbol:
        return symbol  # already suffixed
    return f"{symbol}.{exchange}"


def from_yfinance_ticker(yf_ticker: str) -> str:
    """Reverse — strip exchange suffix."""
    return yf_ticker.split(".")[0]
