"""Paper vs backtest comparison tracker.

Runs the backtest engine over the same period as paper trading and compares
results. This is the core Phase 1 graduation gate: paper must track backtest
within ±3% annualized return difference.

Outputs a comparison report with:
- Equity curves (paper vs backtest) over the paper period
- Return correlation and tracking error
- Holdings overlap at each rebalance
- Go/no-go assessment against graduation criteria
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from trading.backtest.costs import CostConfig
from trading.backtest.engine import run_backtest
from trading.config import OUTPUTS_DIR
from trading.execution.paper import PAPER_DIR, PaperState
from trading.utils.logging import setup_logging

log = setup_logging("tracker")


@dataclass
class ComparisonReport:
    """Results of comparing paper trading against a backtest over the same period."""

    paper_start: str
    paper_end: str
    paper_return: float  # total return
    backtest_return: float
    return_diff: float  # paper - backtest (annualized)
    paper_cagr: float
    backtest_cagr: float
    cagr_diff: float
    tracking_error_annualized: float
    return_correlation: float
    holdings_overlap_pct: float  # average % of holdings in common at rebalances
    days_tracked: int
    passes_gate: bool  # |cagr_diff| < 3%
    gate_threshold: float

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def run_comparison(
    strategy_name: str,
    prices: pd.DataFrame,
    target_weights_at_rebal: pd.DataFrame,
    cost_config: CostConfig,
    risk_free_rate: float = 0.06,
    gate_threshold: float = 0.03,
) -> ComparisonReport | None:
    """Compare paper trading results against a fresh backtest over the paper period.

    Parameters
    ----------
    strategy_name: name of the strategy (used to find paper state).
    prices: full price panel (daily, date x ticker).
    target_weights_at_rebal: target weights at rebalance dates (from signal pipeline).
    cost_config: transaction cost model.
    risk_free_rate: for Sharpe calculations.
    gate_threshold: max allowed |CAGR difference| (default 3%).

    Returns ComparisonReport, or None if paper trading hasn't started.
    """
    state = PaperState.load(strategy_name)
    paper_dir = PAPER_DIR / strategy_name

    # Load paper equity history
    equity_path = paper_dir / "equity.csv"
    if not equity_path.exists():
        log.warning("No paper equity history found — run at least one rebalance first.")
        return None

    paper_equity = pd.read_csv(equity_path)
    if paper_equity.empty:
        log.warning("Paper equity history is empty.")
        return None

    paper_equity["date"] = pd.to_datetime(paper_equity["date"])
    paper_equity = paper_equity.set_index("date").sort_index()

    paper_start = paper_equity.index.min()
    paper_end = paper_equity.index.max()

    # Run backtest over the paper period
    bt_prices = prices.loc[
        (prices.index >= paper_start - pd.DateOffset(days=5)) &
        (prices.index <= paper_end + pd.DateOffset(days=5))
    ]

    # Filter target weights to the paper period
    bt_weights = target_weights_at_rebal.loc[
        (target_weights_at_rebal.index >= paper_start - pd.DateOffset(months=1)) &
        (target_weights_at_rebal.index <= paper_end + pd.DateOffset(days=5))
    ]

    if bt_weights.empty:
        log.warning("No rebalance dates fall within the paper period.")
        return None

    bt_result = run_backtest(
        prices=bt_prices,
        target_weights_at_rebal=bt_weights,
        cost_config=cost_config,
    )

    # Align equity curves
    bt_equity = bt_result.equity_curve
    # Normalize both to start at 1.0
    bt_equity_norm = bt_equity / bt_equity.iloc[0]

    paper_eq_series = paper_equity["equity"]
    paper_eq_norm = paper_eq_series / paper_eq_series.iloc[0]

    # Total returns
    paper_total_return = float(paper_eq_norm.iloc[-1] / paper_eq_norm.iloc[0] - 1)
    bt_total_return = float(bt_equity_norm.iloc[-1] / bt_equity_norm.iloc[0] - 1)

    # CAGR
    days = (paper_end - paper_start).days
    years = max(days / 365.25, 1 / 365.25)  # avoid div by zero for very short periods

    paper_cagr = (1 + paper_total_return) ** (1 / years) - 1
    bt_cagr = (1 + bt_total_return) ** (1 / years) - 1
    cagr_diff = paper_cagr - bt_cagr

    # Daily returns for correlation / tracking error
    # For short periods we may only have monthly snapshots, so handle gracefully
    if len(paper_eq_series) > 1:
        paper_rets = paper_eq_series.pct_change().dropna()
        # Align backtest returns to paper dates
        bt_rets_aligned = bt_result.returns.reindex(paper_rets.index, method="nearest")

        if len(paper_rets) > 1 and len(bt_rets_aligned.dropna()) > 1:
            common = paper_rets.index.intersection(bt_rets_aligned.dropna().index)
            if len(common) > 1:
                corr = float(paper_rets.loc[common].corr(bt_rets_aligned.loc[common]))
                tracking_diff = paper_rets.loc[common] - bt_rets_aligned.loc[common]
                te = float(tracking_diff.std() * np.sqrt(252))
            else:
                corr = float("nan")
                te = float("nan")
        else:
            corr = float("nan")
            te = float("nan")
    else:
        corr = float("nan")
        te = float("nan")

    # Holdings overlap — compare paper holdings vs backtest weights at rebalances
    trades_path = paper_dir / "trades.csv"
    if trades_path.exists():
        trades = pd.read_csv(trades_path)
        rebal_dates = trades["date"].unique()
        overlaps = []
        for dt_str in rebal_dates:
            dt = pd.Timestamp(dt_str)
            # Paper holdings after this rebalance
            paper_held = set(
                trades[(trades["date"] == dt_str) & (trades["new_weight"].astype(float) > 0.001)]["ticker"]
            )
            # Backtest target at nearest date
            if not bt_weights.empty:
                nearest_idx = bt_weights.index[bt_weights.index.get_indexer([dt], method="nearest")]
                if len(nearest_idx) > 0:
                    bt_held = set(bt_weights.loc[nearest_idx[0]][bt_weights.loc[nearest_idx[0]] > 0.001].index)
                    if paper_held or bt_held:
                        overlap = len(paper_held & bt_held) / max(len(paper_held | bt_held), 1)
                        overlaps.append(overlap)
        avg_overlap = float(np.mean(overlaps)) if overlaps else float("nan")
    else:
        avg_overlap = float("nan")

    passes = abs(cagr_diff) < gate_threshold

    report = ComparisonReport(
        paper_start=str(paper_start.date()),
        paper_end=str(paper_end.date()),
        paper_return=paper_total_return,
        backtest_return=bt_total_return,
        return_diff=paper_total_return - bt_total_return,
        paper_cagr=paper_cagr,
        backtest_cagr=bt_cagr,
        cagr_diff=cagr_diff,
        tracking_error_annualized=te,
        return_correlation=corr,
        holdings_overlap_pct=avg_overlap,
        days_tracked=days,
        passes_gate=passes,
        gate_threshold=gate_threshold,
    )

    log.info(
        f"Comparison: paper CAGR={paper_cagr:.2%}, backtest CAGR={bt_cagr:.2%}, "
        f"diff={cagr_diff:.2%}, gate={'PASS' if passes else 'FAIL'}"
    )

    return report


def save_comparison(strategy_name: str, report: ComparisonReport) -> Path:
    """Save comparison report to the paper trading directory."""
    out_dir = PAPER_DIR / strategy_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "comparison.json"
    with open(path, "w") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    log.info(f"Comparison saved to {path}")
    return path


def format_comparison(report: ComparisonReport) -> str:
    """Pretty-print comparison report."""
    from tabulate import tabulate

    pct = lambda x: f"{x:.2%}" if not np.isnan(x) else "—"
    num = lambda x: f"{x:.4f}" if not np.isnan(x) else "—"

    gate_status = "PASS" if report.passes_gate else "FAIL"
    gate_color = gate_status

    rows = [
        ("Period", f"{report.paper_start} → {report.paper_end}"),
        ("Days tracked", str(report.days_tracked)),
        ("", ""),
        ("Paper total return", pct(report.paper_return)),
        ("Backtest total return", pct(report.backtest_return)),
        ("Return difference", pct(report.return_diff)),
        ("", ""),
        ("Paper CAGR", pct(report.paper_cagr)),
        ("Backtest CAGR", pct(report.backtest_cagr)),
        ("CAGR difference", pct(report.cagr_diff)),
        ("", ""),
        ("Tracking error (ann.)", pct(report.tracking_error_annualized)),
        ("Return correlation", num(report.return_correlation)),
        ("Holdings overlap", pct(report.holdings_overlap_pct)),
        ("", ""),
        ("Gate threshold", f"±{report.gate_threshold:.0%}"),
        ("Gate status", gate_status),
    ]
    return tabulate(rows, headers=["Metric", "Value"], tablefmt="simple")
