"""Backtest engine — monthly rebalance simulation with transaction costs.

Simple but honest model:
- At each rebalance date, compute target weights from signals.
- Trade the delta from current weights to target. Cost each side of the delta.
- Between rebalance dates, portfolio drifts with returns (no intra-month trading).
- Turnover is tracked for diagnostics.

Assumptions documented in the output so we never forget the backtest's limits:
- Prices are close-to-close; fills assumed at close of rebalance day.
- Slippage modeled as a fixed bps per trade (CostConfig.slippage_per_side).
- No intraday behavior, no partial fills, no capacity constraints.
- Universe is static (survivorship-biased); point-in-time universe is future work.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading.backtest.costs import CostConfig, one_way_cost


@dataclass
class BacktestResult:
    """Container for backtest outputs."""

    equity_curve: pd.Series            # Portfolio value over time (starts at 1.0)
    returns: pd.Series                 # Daily net returns (after costs, post-drift)
    weights: pd.DataFrame              # Daily weights held
    turnover: pd.Series                # Per-rebalance turnover (one-sided, 0 to 1)
    rebalance_dates: pd.DatetimeIndex
    cost_drag_annualized: float        # Approximate annualized cost drag
    config_snapshot: dict              # For reproducibility


def run_backtest(
    prices: pd.DataFrame,
    target_weights_at_rebal: pd.DataFrame,
    cost_config: CostConfig | None = None,
    initial_capital: float = 1.0,
) -> BacktestResult:
    """Run a monthly-rebalance backtest given daily prices and target weights at each rebalance date.

    Parameters
    ----------
    prices: wide DataFrame (date x ticker) of adjusted close prices (daily).
    target_weights_at_rebal: DataFrame indexed by rebalance dates, columns = tickers,
                             values = target weights summing to <= 1.0 per row.
                             Rows of zeros mean "go to cash."
    cost_config: cost parameters; uses defaults if None.
    initial_capital: starting capital (default 1.0 for unit-scaled results).
    """
    if cost_config is None:
        cost_config = CostConfig()

    # Align
    prices = prices.sort_index()
    prices = prices.ffill(limit=5)  # tolerate small data gaps
    rebal_dates = target_weights_at_rebal.index.sort_values()

    # Build daily weights by forward-filling target weights between rebalance dates
    full_dates = prices.index
    rebal_on_prices = [d for d in rebal_dates if d in full_dates]
    if not rebal_on_prices:
        # Snap each rebal date to the nearest prior price date
        snapped = []
        for d in rebal_dates:
            later = full_dates[full_dates <= d]
            if len(later) > 0:
                snapped.append(later[-1])
        rebal_on_prices = pd.DatetimeIndex(sorted(set(snapped)))

    # Initialize weights DataFrame
    columns = prices.columns
    weights = pd.DataFrame(0.0, index=full_dates, columns=columns)

    # Daily simple returns
    rets = prices.pct_change().fillna(0.0)

    # Walk forward rebalance-by-rebalance
    current_weights = pd.Series(0.0, index=columns)
    equity = initial_capital
    equity_curve = []
    port_returns = []
    turnover_series = {}

    # Ensure target weights are aligned to our columns
    tw = target_weights_at_rebal.reindex(columns=columns, fill_value=0.0).fillna(0.0)

    # Prepare an iterator over rebalance dates mapped to actual price dates
    rebal_map = {}
    for orig, snapped_date in zip(rebal_dates, [
        full_dates[full_dates <= d][-1] if len(full_dates[full_dates <= d]) > 0 else None
        for d in rebal_dates
    ]):
        if snapped_date is not None:
            rebal_map[snapped_date] = orig

    rebal_dates_effective = pd.DatetimeIndex(sorted(rebal_map.keys()))
    rebal_idx_ptr = 0

    for i, dt in enumerate(full_dates):
        # 1) Apply today's market return to held positions (drift)
        if i > 0:
            daily_ret = float((current_weights * rets.loc[dt]).sum())
            equity *= 1.0 + daily_ret
            # Update weights with drift (they renormalize naturally as equity changes)
            if current_weights.abs().sum() > 0:
                drifted = current_weights * (1.0 + rets.loc[dt])
                # Keep sum the same as current allocation (allow cash residual implicitly)
                # We don't renormalize because cash should stay cash
                current_weights = drifted
            port_returns.append(daily_ret)
        else:
            port_returns.append(0.0)

        # 2) If this is a rebalance date, trade to new target
        if dt in rebal_map:
            target = tw.loc[rebal_map[dt]]
            # Rescale current weights so they represent current % of equity (not drifted notional)
            gross = current_weights.abs().sum()
            if gross > 0:
                current_pct = current_weights / gross * (current_weights.sum() / max(current_weights.sum(), 1e-12))
            # Simpler + more correct: current weights already represent % of *initial* capital.
            # We track current allocation as a vector that sums to whatever fraction is invested.
            # To compute trade deltas correctly, we rebase current to fractions-of-current-equity.
            invested_frac = current_weights.sum()
            if invested_frac > 0:
                current_pct = current_weights / max(invested_frac, 1e-12) * invested_frac
            else:
                current_pct = current_weights.copy()

            # Trade delta: target minus current (both as fractions of current equity)
            delta = target - current_pct
            buys = delta[delta > 0].sum()
            sells = -delta[delta < 0].sum()

            # Cost per side on gross turnover
            buy_cost = buys * one_way_cost("buy", cost_config)
            sell_cost = sells * one_way_cost("sell", cost_config)
            total_cost = buy_cost + sell_cost

            # Apply costs as an equity haircut
            equity *= 1.0 - total_cost

            # Record turnover (one-sided)
            turnover_series[dt] = float((buys + sells) / 2.0)

            # Set new weights
            current_weights = target.copy()

        weights.loc[dt] = current_weights
        equity_curve.append(equity)

    equity_series = pd.Series(equity_curve, index=full_dates, name="equity")
    returns_series = pd.Series(port_returns, index=full_dates, name="net_return")
    turnover_ser = pd.Series(turnover_series, name="turnover").sort_index()

    # Annualized cost drag estimate: mean turnover per rebalance * rebalances/yr * round-trip cost
    if len(turnover_ser) > 1:
        span_years = (turnover_ser.index.max() - turnover_ser.index.min()).days / 365.25
        rebal_per_yr = len(turnover_ser) / max(span_years, 1e-9)
        avg_turnover = float(turnover_ser.mean())
        rt_cost = one_way_cost("buy", cost_config) + one_way_cost("sell", cost_config)
        cost_drag = avg_turnover * rebal_per_yr * rt_cost
    else:
        cost_drag = 0.0

    return BacktestResult(
        equity_curve=equity_series,
        returns=returns_series,
        weights=weights,
        turnover=turnover_ser,
        rebalance_dates=pd.DatetimeIndex(rebal_dates_effective),
        cost_drag_annualized=cost_drag,
        config_snapshot={
            "cost_config": cost_config.__dict__,
            "initial_capital": initial_capital,
            "n_rebalances": len(rebal_dates_effective),
        },
    )
