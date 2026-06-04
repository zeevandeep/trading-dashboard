"""Paper trading adapter — simulated execution against live market prices.

Runs the same signal/portfolio pipeline used in backtesting, but against
fresh price data. Logs simulated fills, tracks equity and holdings over
time, and persists state between runs so a monthly cron can drive it.

State lives in ``data/paper/<strategy>/``:
    state.json      — current holdings, equity, last rebalance date
    trades.csv      — append-only trade log (all simulated fills)
    equity.csv      — daily equity snapshots
    signals.csv     — signal scores at each rebalance (for debugging)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from trading.backtest.costs import CostConfig, one_way_cost
from trading.config import DATA_DIR
from trading.utils.logging import setup_logging

log = setup_logging("paper")

PAPER_DIR = DATA_DIR / "paper"


@dataclass
class PaperState:
    """Persistent state for one paper-trading strategy."""

    strategy: str
    holdings: dict[str, float]  # ticker -> weight (fraction of equity)
    equity: float  # current portfolio value (starts at 1.0)
    cash_weight: float  # fraction of equity in cash
    last_rebalance: str | None  # ISO date of last rebalance
    created: str = ""  # ISO datetime of first run
    trade_count: int = 0

    @classmethod
    def fresh(cls, strategy: str) -> PaperState:
        return cls(
            strategy=strategy,
            holdings={},
            equity=1.0,
            cash_weight=1.0,
            last_rebalance=None,
            created=datetime.now().isoformat(),
        )

    def state_dir(self) -> Path:
        d = PAPER_DIR / self.strategy
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self) -> None:
        path = self.state_dir() / "state.json"
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)
        log.info(f"State saved to {path}")

    @classmethod
    def load(cls, strategy: str) -> PaperState:
        path = PAPER_DIR / strategy / "state.json"
        if not path.exists():
            return cls.fresh(strategy)
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


@dataclass
class Trade:
    """A single simulated trade."""

    date: str
    ticker: str
    side: str  # "buy" or "sell"
    weight_delta: float  # fraction of equity traded
    cost: float  # transaction cost as fraction of equity
    old_weight: float
    new_weight: float


def rebalance(
    state: PaperState,
    target_weights: dict[str, float],
    prices: pd.DataFrame,
    rebalance_date: date,
    cost_config: CostConfig | None = None,
) -> list[Trade]:
    """Execute a paper rebalance: compute trades from current to target weights.

    Parameters
    ----------
    state: current paper state (mutated in place).
    target_weights: {ticker: weight} for the new portfolio. Should sum to <= 1.0.
    prices: recent price panel (used for drift calculation since last rebalance).
    rebalance_date: the date of this rebalance.
    cost_config: transaction cost model.

    Returns list of Trade objects (the simulated fills).
    """
    if cost_config is None:
        cost_config = CostConfig()

    dt_str = rebalance_date.isoformat()
    trades: list[Trade] = []

    # Apply drift since last rebalance using actual price changes
    current = dict(state.holdings)
    if state.last_rebalance and current:
        drift_equity = _apply_drift(state, prices)
    else:
        drift_equity = state.equity

    state.equity = drift_equity

    # Compute deltas
    all_tickers = set(list(current.keys()) + list(target_weights.keys()))
    total_buy_cost = 0.0
    total_sell_cost = 0.0

    for ticker in sorted(all_tickers):
        old_w = current.get(ticker, 0.0)
        new_w = target_weights.get(ticker, 0.0)
        delta = new_w - old_w

        if abs(delta) < 1e-8:
            continue

        if delta > 0:
            side = "buy"
            cost = delta * one_way_cost("buy", cost_config)
            total_buy_cost += cost
        else:
            side = "sell"
            cost = abs(delta) * one_way_cost("sell", cost_config)
            total_sell_cost += cost

        trades.append(Trade(
            date=dt_str,
            ticker=ticker,
            side=side,
            weight_delta=delta,
            cost=cost,
            old_weight=old_w,
            new_weight=new_w,
        ))

    # Apply costs as equity haircut
    total_cost = total_buy_cost + total_sell_cost
    state.equity *= (1.0 - total_cost)

    # Update state
    state.holdings = {t: w for t, w in target_weights.items() if w > 1e-8}
    state.cash_weight = 1.0 - sum(state.holdings.values())
    state.last_rebalance = dt_str
    state.trade_count += len(trades)

    log.info(
        f"Rebalance {dt_str}: {len(trades)} trades, "
        f"cost={total_cost:.4%}, equity={state.equity:.4f}, "
        f"{len(state.holdings)} positions"
    )

    return trades


def _apply_drift(state: PaperState, prices: pd.DataFrame) -> float:
    """Drift holdings using actual price returns since last rebalance.

    Returns the updated equity value.
    """
    last_dt = pd.Timestamp(state.last_rebalance)
    recent = prices.loc[prices.index > last_dt]

    if recent.empty:
        return state.equity

    # Daily returns for held tickers
    held = [t for t in state.holdings if t in prices.columns]
    if not held:
        return state.equity

    rets = prices[held].pct_change().fillna(0.0)
    drift_rets = rets.loc[rets.index > last_dt]

    equity = state.equity
    for dt in drift_rets.index:
        daily_port_ret = sum(
            state.holdings.get(t, 0.0) * drift_rets.loc[dt, t]
            for t in held
        )
        equity *= (1.0 + daily_port_ret)

    return equity


def append_trades(state: PaperState, trades: list[Trade]) -> None:
    """Append trades to the persistent trade log CSV."""
    if not trades:
        return
    path = state.state_dir() / "trades.csv"
    df = pd.DataFrame([
        {
            "date": t.date,
            "ticker": t.ticker,
            "side": t.side,
            "weight_delta": t.weight_delta,
            "cost": t.cost,
            "old_weight": t.old_weight,
            "new_weight": t.new_weight,
        }
        for t in trades
    ])
    if path.exists():
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)
    log.info(f"Appended {len(trades)} trades to {path}")


def append_equity(state: PaperState) -> None:
    """Append today's equity to the equity log."""
    path = state.state_dir() / "equity.csv"
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d"),
        "equity": state.equity,
        "n_positions": len(state.holdings),
        "cash_weight": state.cash_weight,
    }])
    if path.exists():
        row.to_csv(path, mode="a", header=False, index=False)
    else:
        row.to_csv(path, index=False)


def save_signals(state: PaperState, scores: pd.Series, rebalance_date: date) -> None:
    """Save signal scores at rebalance for auditability."""
    path = state.state_dir() / "signals.csv"
    df = scores.dropna().sort_values(ascending=False).to_frame("score")
    df["rebalance_date"] = rebalance_date.isoformat()
    df.index.name = "ticker"
    if path.exists():
        df.to_csv(path, mode="a", header=False)
    else:
        df.to_csv(path)
