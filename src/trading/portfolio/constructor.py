"""Portfolio construction — ranked signal + top-N equal weight + trend filter gate."""

from __future__ import annotations

import pandas as pd


def top_n_equal_weight(
    scores: pd.DataFrame,
    top_n: int = 15,
    risk_on: pd.Series | None = None,
) -> pd.DataFrame:
    """Build target weights from momentum scores.

    Parameters
    ----------
    scores: wide DataFrame (date x ticker) of momentum scores (higher = better).
    top_n: how many names to hold each rebalance.
    risk_on: optional boolean Series (date-indexed). If False at a given date,
             the portfolio goes to cash (all weights zero at that date).

    Returns
    -------
    Wide DataFrame (date x ticker) of target weights. Weights on held names
    are 1/top_n; unheld names are 0. Rows sum to 1.0 on risk-on dates, 0.0 on
    risk-off dates. NaN scores are excluded from selection.
    """
    weights = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)

    # Align risk_on to scores index, filling gaps with True (risk-on) as default
    if risk_on is not None:
        risk_on = risk_on.reindex(scores.index).ffill().fillna(True)
    else:
        risk_on = pd.Series(True, index=scores.index)

    per_name = 1.0 / top_n

    for dt in scores.index:
        if not bool(risk_on.loc[dt]):
            continue  # leave as zeros -> cash
        row = scores.loc[dt].dropna()
        if row.empty:
            continue
        picks = row.nlargest(top_n).index
        weights.loc[dt, picks] = per_name

    return weights


def resample_to_rebalance_dates(
    weights: pd.DataFrame, frequency: str = "ME"
) -> pd.DataFrame:
    """Reduce a full-history weights panel to just the rebalance dates.

    frequency: pandas offset alias. 'ME' = month-end, 'W-FRI' = weekly Friday, 'QE' = quarter-end.
    Takes the last available weight row on or before each rebalance date.
    """
    # Build rebalance schedule
    rebal_dates = pd.date_range(
        start=weights.index.min(), end=weights.index.max(), freq=frequency
    )
    # Use reindex with method='pad' to pick the last available weights on/before each rebalance date
    rebal = weights.reindex(rebal_dates, method="pad")
    rebal.index.name = "rebalance_date"
    return rebal
