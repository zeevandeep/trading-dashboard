"""Generate a one-page PDF factsheet for a paper-trading strategy."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd
import yfinance as yf

from trading.reporting.metrics import (
    cagr, annualized_volatility, sharpe, sortino, max_drawdown, calmar,
)

# ── Config ───────────────────────────────────────────────────────────────
STRATEGY_META = {
    "smallcap_momentum_v2": {
        "display_name": "Ascent",
        "tagline": "Cross-sectional momentum on NSE 500 ex Nifty 50",
        "rebalance": "Monthly",
        "benchmark": "Nifty Smallcap 250",
        "benchmark_ticker": "^NSEI",  # fallback to Nifty 50
    },
    "value_quality_v1": {
        "display_name": "Bedrock",
        "tagline": "Composite value + quality factor (EY, ROE, D/E, EG)",
        "rebalance": "Quarterly",
        "benchmark": "Nifty 50",
        "benchmark_ticker": "^NSEI",
    },
}

SECTOR_MAP = {
    "NATIONALUM": "Metals & Mining", "HINDCOPPER": "Metals & Mining",
    "MCX": "Financial Services", "VEDL": "Metals & Mining",
    "RBLBANK": "Financial Services", "BHARATFORG": "Auto Components",
    "LAURUSLABS": "Pharmaceuticals", "GESHIP": "Shipping",
    "ASHOKLEY": "Automobiles", "CUMMINSIND": "Capital Goods",
    "ABCAPITAL": "Financial Services", "AUBANK": "Financial Services",
    "DELHIVERY": "Logistics", "NAVINFLUOR": "Chemicals",
    "CANBK": "Financial Services", "IEX": "Financial Services",
    "OFSS": "IT Services", "GNFC": "Chemicals",
    "LUPIN": "Pharmaceuticals", "NMDC": "Metals & Mining",
    "CHAMBLFERT": "Chemicals", "MUTHOOTFIN": "Financial Services",
    "PETRONET": "Oil & Gas", "GLAXO": "Pharmaceuticals",
    "IRCTC": "Tourism & Travel",
}

# Colors
DARK = "#1a1a2e"
ACCENT = "#c9a84c"
LIGHT = "#f5f5f5"
GREEN = "#2e7d32"
RED = "#c62828"


def load_strategy(strategy: str) -> tuple[pd.Series, dict]:
    """Load equity curve and state for a strategy."""
    base = Path("data/paper") / strategy
    eq = pd.read_csv(base / "equity.csv", parse_dates=["date"], index_col="date")["equity"]
    with open(base / "state.json") as f:
        state = json.load(f)
    return eq, state


def fetch_benchmark(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch benchmark close prices."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty:
            return pd.Series(dtype=float)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close
    except Exception:
        return pd.Series(dtype=float)


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "Other")


def generate_factsheet(strategy: str, out_dir: str = "outputs/factsheets"):
    meta = STRATEGY_META[strategy]
    equity, state = load_strategy(strategy)
    returns = equity.pct_change().dropna()
    holdings = state["holdings"]
    tickers = list(holdings.keys())

    # Benchmark
    bm = fetch_benchmark(
        meta["benchmark_ticker"],
        str(equity.index[0].date()),
        str(equity.index[-1].date() + pd.Timedelta(days=1)),
    )
    if not bm.empty:
        bm = bm.reindex(equity.index, method="ffill")
        bm = bm / bm.iloc[0]  # normalize to 1.0

    # Metrics
    dd_val, dd_peak, dd_trough = max_drawdown(equity)
    total_return = (equity.iloc[-1] / equity.iloc[0] - 1)
    days = (equity.index[-1] - equity.index[0]).days

    # Sector breakdown
    sector_weights = {}
    for t in tickers:
        s = get_sector(t)
        sector_weights[s] = sector_weights.get(s, 0) + holdings[t]

    # ── Build the PDF ────────────────────────────────────────────────
    fig = plt.figure(figsize=(11.69, 8.27), facecolor="white")  # A4 landscape
    gs = GridSpec(
        5, 4, figure=fig,
        hspace=0.8, wspace=0.5,
        left=0.06, right=0.94, top=0.92, bottom=0.06,
    )

    # ── Header ───────────────────────────────────────────────────────
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.axis("off")
    month_label = equity.index[-1].strftime("%B %Y")
    ax_header.text(
        0.0, 0.8, f"JD Quant  ·  {meta['display_name']}",
        fontsize=22, fontweight="bold", color=DARK, transform=ax_header.transAxes,
    )
    ax_header.text(
        0.0, 0.3, meta["tagline"],
        fontsize=11, color="#555", transform=ax_header.transAxes,
    )
    ax_header.text(
        0.0, -0.1, f"Monthly Factsheet  ·  {month_label}",
        fontsize=10, color="#888", transform=ax_header.transAxes,
    )
    # Right side: key stats
    ax_header.text(
        1.0, 0.8, f"Since Inception: {total_return:+.2%}",
        fontsize=14, fontweight="bold",
        color=GREEN if total_return >= 0 else RED,
        ha="right", transform=ax_header.transAxes,
    )
    ax_header.text(
        1.0, 0.3, f"Rebalance: {meta['rebalance']}  ·  Positions: {len(tickers)}",
        fontsize=10, color="#555", ha="right", transform=ax_header.transAxes,
    )
    ax_header.text(
        1.0, -0.1, f"Inception: {equity.index[0].strftime('%d %b %Y')}  ·  Track record: {days}d",
        fontsize=10, color="#888", ha="right", transform=ax_header.transAxes,
    )
    # Separator line
    ax_header.plot([0, 1], [-0.4, -0.4], color=ACCENT, linewidth=2,
                   transform=ax_header.transAxes, clip_on=False)

    # ── Equity Curve ─────────────────────────────────────────────────
    ax_eq = fig.add_subplot(gs[1:3, :2])
    ax_eq.plot(equity.index, (equity - 1) * 100, color=DARK, linewidth=2, label=meta["display_name"])
    if not bm.empty:
        ax_eq.plot(bm.index, (bm - 1) * 100, color="#999", linewidth=1.5,
                   linestyle="--", label=meta["benchmark"], alpha=0.7)
    ax_eq.axhline(0, color="#ccc", linewidth=0.8)
    ax_eq.set_title("Performance (%)", fontsize=11, fontweight="bold", loc="left")
    ax_eq.set_ylabel("Return (%)")
    ax_eq.legend(fontsize=8, loc="upper left")
    ax_eq.tick_params(labelsize=8)
    ax_eq.tick_params(axis="x", rotation=20)
    import matplotlib.dates as mdates
    ax_eq.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax_eq.grid(True, alpha=0.3)

    # ── Risk Metrics Table ──────────────────────────────────────────
    ax_metrics = fig.add_subplot(gs[1, 2:])
    ax_metrics.axis("off")
    ax_metrics.set_title("Risk Metrics", fontsize=11, fontweight="bold", loc="left")

    metrics_data = [
        ["Total Return", f"{total_return:+.2%}"],
        ["CAGR", f"{cagr(equity):.2%}" if days > 30 else "N/A (<1mo)"],
        ["Volatility (ann.)", f"{annualized_volatility(returns):.2%}"],
        ["Sharpe Ratio", f"{sharpe(returns, 0.06):.2f}"],
        ["Sortino Ratio", f"{sortino(returns, 0.06):.2f}"],
        ["Max Drawdown", f"{dd_val:.2%}"],
        ["Calmar Ratio", f"{calmar(equity):.2f}" if days > 30 else "N/A"],
    ]
    table1 = ax_metrics.table(
        cellText=metrics_data, colLabels=["Metric", "Value"],
        cellLoc="left", loc="upper left",
        colWidths=[0.55, 0.35],
    )
    table1.auto_set_font_size(False)
    table1.set_fontsize(9)
    for (r, c), cell in table1.get_celld().items():
        cell.set_edgecolor("#ddd")
        if r == 0:
            cell.set_facecolor(DARK)
            cell.set_text_props(color="white", fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f8f8f8")
        cell.set_height(0.12)

    # ── Sector Allocation ───────────────────────────────────────────
    ax_sector = fig.add_subplot(gs[2, 2:])
    sectors_sorted = sorted(sector_weights.items(), key=lambda x: x[1])
    labels = [s for s, _ in sectors_sorted]
    sizes = [w * 100 for _, w in sectors_sorted]
    colors_bar = plt.cm.Set3(np.linspace(0, 1, len(labels)))
    bars = ax_sector.barh(labels, sizes, color=colors_bar, edgecolor="white", height=0.7)
    for bar, val in zip(bars, sizes):
        ax_sector.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                       f"{val:.0f}%", va="center", fontsize=7)
    ax_sector.set_title("Sector Allocation", fontsize=11, fontweight="bold", loc="left")
    ax_sector.set_xlim(0, max(sizes) * 1.4)
    ax_sector.tick_params(labelsize=7, pad=2)
    ax_sector.xaxis.set_visible(False)
    ax_sector.spines["top"].set_visible(False)
    ax_sector.spines["right"].set_visible(False)
    ax_sector.spines["bottom"].set_visible(False)

    # ── Holdings Table ──────────────────────────────────────────────
    ax_hold = fig.add_subplot(gs[3:, :])
    ax_hold.axis("off")
    ax_hold.set_title("Current Holdings", fontsize=11, fontweight="bold", loc="left")

    # Build table data: two columns of holdings side by side
    hold_list = [(t, f"{w:.1%}", get_sector(t)) for t, w in holdings.items()]
    mid = (len(hold_list) + 1) // 2
    left_half = hold_list[:mid]
    right_half = hold_list[mid:]
    # Pad right half
    while len(right_half) < len(left_half):
        right_half.append(("", "", ""))

    table_data = []
    for l, r in zip(left_half, right_half):
        table_data.append([l[0], l[1], l[2], r[0], r[1], r[2]])

    col_labels = ["Ticker", "Weight", "Sector", "Ticker", "Weight", "Sector"]
    table2 = ax_hold.table(
        cellText=table_data, colLabels=col_labels,
        cellLoc="left", loc="upper left",
        colWidths=[0.14, 0.08, 0.14, 0.14, 0.08, 0.14],
    )
    table2.auto_set_font_size(False)
    table2.set_fontsize(8)
    for (r, c), cell in table2.get_celld().items():
        cell.set_edgecolor("#ddd")
        if r == 0:
            cell.set_facecolor(DARK)
            cell.set_text_props(color="white", fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f8f8f8")
        cell.set_height(0.1)

    # ── Footer ───────────────────────────────────────────────────────
    fig.text(
        0.5, 0.01,
        "Past performance is not indicative of future results. This is not investment advice. "
        "For informational purposes only.  ·  jdquant.in",
        ha="center", fontsize=7, color="#999",
    )

    # ── Save ─────────────────────────────────────────────────────────
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    date_str = equity.index[-1].strftime("%Y%m")
    filename = f"{meta['display_name'].lower()}_{date_str}.pdf"
    filepath = out_path / filename
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Factsheet saved: {filepath}")
    return filepath


if __name__ == "__main__":
    strategies = sys.argv[1:] if len(sys.argv) > 1 else list(STRATEGY_META.keys())
    for s in strategies:
        if s not in STRATEGY_META:
            print(f"Unknown strategy: {s}")
            continue
        generate_factsheet(s)
