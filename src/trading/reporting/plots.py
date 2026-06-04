"""Visualization — equity curve, drawdown, rolling Sharpe, monthly heatmap."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def _style():
    plt.style.use("seaborn-v0_8-whitegrid")


def plot_equity_curve(
    equity: pd.Series, benchmark: pd.Series | None = None, out_path: Path | str | None = None
) -> None:
    """Equity curve with optional benchmark overlay."""
    _style()
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(equity.index, equity.values, label="Strategy", linewidth=2)
    if benchmark is not None and not benchmark.empty:
        b = benchmark.reindex(equity.index).ffill()
        b = b / b.iloc[0] * equity.iloc[0]
        ax.plot(b.index, b.values, label="Benchmark", linewidth=1.5, alpha=0.7, linestyle="--")
    ax.set_title("Equity Curve")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity (normalized)")
    ax.set_yscale("log")
    ax.legend()
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_drawdown(equity: pd.Series, out_path: Path | str | None = None) -> None:
    """Drawdown plot (underwater equity)."""
    _style()
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(dd.index, dd.values, 0, alpha=0.3, color="red")
    ax.plot(dd.index, dd.values, color="darkred", linewidth=1)
    ax.set_title("Drawdown")
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_monthly_heatmap(returns: pd.Series, out_path: Path | str | None = None) -> None:
    """Monthly returns heatmap (year x month)."""
    _style()
    monthly = (1 + returns).resample("ME").prod() - 1
    df = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "ret": monthly.values,
    })
    pivot = df.pivot(index="year", columns="month", values="ret")
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    pivot.columns = [month_labels[m - 1] for m in pivot.columns]

    fig, ax = plt.subplots(figsize=(12, max(4, len(pivot) * 0.35)))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1%",
        cmap="RdYlGn",
        center=0,
        cbar=True,
        ax=ax,
        annot_kws={"size": 9},
    )
    ax.set_title("Monthly Returns (%)")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_rolling_sharpe(
    returns: pd.Series, window_days: int = 252, out_path: Path | str | None = None
) -> None:
    """Rolling annualized Sharpe over a trailing window."""
    _style()
    rolling_mean = returns.rolling(window_days).mean()
    rolling_std = returns.rolling(window_days).std()
    rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(252)
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(rolling_sharpe.index, rolling_sharpe.values, color="steelblue")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhline(1.0, color="green", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_title(f"Rolling Sharpe ({window_days}-day)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Sharpe")
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=150)
    plt.close(fig)
