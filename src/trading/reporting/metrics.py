"""Performance metrics — CAGR, Sharpe, Sortino, max drawdown, Calmar, win rate, etc."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def cagr(equity: pd.Series) -> float:
    """Compound annual growth rate from an equity curve."""
    if equity.empty or equity.iloc[0] <= 0:
        return float("nan")
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)


def annualized_volatility(returns: pd.Series) -> float:
    """Annualized standard deviation of daily returns."""
    if returns.empty:
        return float("nan")
    return float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio. risk_free_rate as annualized decimal (0.06 = 6%)."""
    if returns.empty:
        return float("nan")
    daily_rf = (1 + risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess = returns - daily_rf
    std = excess.std()
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sortino ratio — uses downside deviation only."""
    if returns.empty:
        return float("nan")
    daily_rf = (1 + risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess = returns - daily_rf
    downside = excess[excess < 0]
    dd_std = downside.std()
    if dd_std == 0 or np.isnan(dd_std) or downside.empty:
        return float("nan")
    return float(excess.mean() / dd_std * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    """Max drawdown magnitude (negative), peak date, trough date."""
    if equity.empty:
        return float("nan"), pd.NaT, pd.NaT
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    trough = dd.idxmin()
    # Peak is the last running-max date on or before the trough
    peak_mask = (running_max.loc[:trough] == running_max.loc[trough])
    peak = peak_mask[peak_mask].index[0] if peak_mask.any() else equity.index[0]
    return float(dd.min()), peak, trough


def calmar(equity: pd.Series) -> float:
    """Calmar ratio: CAGR / |max drawdown|."""
    ann = cagr(equity)
    dd, _, _ = max_drawdown(equity)
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float(ann / abs(dd))


def win_rate_monthly(returns: pd.Series) -> float:
    """Fraction of months with positive return."""
    if returns.empty:
        return float("nan")
    monthly = (1 + returns).resample("ME").prod() - 1
    return float((monthly > 0).mean())


def summary(
    equity: pd.Series, returns: pd.Series, risk_free_rate: float = 0.0
) -> dict[str, float]:
    """One-shot metrics dictionary — the table you print after every backtest."""
    dd, peak, trough = max_drawdown(equity)
    return {
        "start_date": str(equity.index[0].date()) if not equity.empty else "",
        "end_date": str(equity.index[-1].date()) if not equity.empty else "",
        "cagr": cagr(equity),
        "annual_vol": annualized_volatility(returns),
        "sharpe": sharpe(returns, risk_free_rate),
        "sortino": sortino(returns, risk_free_rate),
        "max_drawdown": dd,
        "max_dd_peak": str(peak.date()) if peak is not pd.NaT else "",
        "max_dd_trough": str(trough.date()) if trough is not pd.NaT else "",
        "calmar": calmar(equity),
        "win_rate_monthly": win_rate_monthly(returns),
        "final_equity": float(equity.iloc[-1]) if not equity.empty else float("nan"),
    }


def format_summary(summary_dict: dict) -> str:
    """Pretty-print the summary dict as a table string."""
    from tabulate import tabulate

    pct = lambda x: f"{x:.2%}" if isinstance(x, float) and not np.isnan(x) else str(x)
    num = lambda x: f"{x:.2f}" if isinstance(x, float) and not np.isnan(x) else str(x)

    rows = [
        ("Period", f"{summary_dict['start_date']} → {summary_dict['end_date']}"),
        ("CAGR", pct(summary_dict["cagr"])),
        ("Annualized Vol", pct(summary_dict["annual_vol"])),
        ("Sharpe", num(summary_dict["sharpe"])),
        ("Sortino", num(summary_dict["sortino"])),
        ("Max Drawdown", pct(summary_dict["max_drawdown"])),
        ("Max DD Peak", summary_dict["max_dd_peak"]),
        ("Max DD Trough", summary_dict["max_dd_trough"]),
        ("Calmar", num(summary_dict["calmar"])),
        ("Win Rate (monthly)", pct(summary_dict["win_rate_monthly"])),
        ("Final Equity (x)", num(summary_dict["final_equity"])),
    ]
    return tabulate(rows, headers=["Metric", "Value"], tablefmt="simple")
