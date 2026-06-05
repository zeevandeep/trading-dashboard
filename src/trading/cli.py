"""Command-line entrypoint.

Usage:
    python main.py backtest --config configs/smallcap_momentum_v1.yaml
    python main.py backtest --config configs/smallcap_momentum_v1.yaml --smoke
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import click
import pandas as pd

from trading.backtest.costs import CostConfig
from trading.backtest.engine import run_backtest
from trading.config import OUTPUTS_DIR, ensure_dirs, load_strategy_config
from trading.data.loader import fetch_benchmark, fetch_many, to_price_panel
from trading.data.universe import nifty50_tickers, nse500_starter_tickers, smallcap_universe
from trading.portfolio.constructor import resample_to_rebalance_dates, top_n_equal_weight
from trading.reporting.metrics import format_summary, summary
from trading.reporting.plots import (
    plot_drawdown,
    plot_equity_curve,
    plot_monthly_heatmap,
    plot_rolling_sharpe,
)
from trading.signals.momentum import absolute_trend_filter, momentum_n_m
from trading.signals.value_quality import (
    compute_historical_scores,
    fetch_historical_fundamentals,
    score_value_quality,
    fetch_fundamentals,
)
from trading.utils.logging import setup_logging


@click.group()
def main() -> None:
    """Trading CLI."""
    pass


@main.command()
@click.option("--config", "-c", required=True, help="Path to strategy YAML config.")
@click.option("--smoke", is_flag=True, help="Run smoke test on small universe subset.")
@click.option("--force-refresh", is_flag=True, help="Re-download all price data.")
@click.option("--survivorship-free", is_flag=True, help="Include dead/delisted stocks to remove survivorship bias.")
def backtest(config: str, smoke: bool, force_refresh: bool, survivorship_free: bool) -> None:
    """Run a full backtest from a YAML config file."""
    ensure_dirs()
    log = setup_logging("backtest")

    cfg = load_strategy_config(config)
    log.info(f"Loaded config: {cfg.get('name', 'unnamed')}")

    # Override survivorship-free from config if not set via CLI
    if not survivorship_free:
        survivorship_free = cfg.get("universe", {}).get("include_dead", False)

    # Universe selection
    universe_mode = cfg.get("universe", {}).get("mode", "nse500_ex_nifty50")
    is_trend_follow = universe_mode == "nifty_etf"

    start = cfg.get("data", {}).get("start", "2010-01-01")
    end = cfg.get("data", {}).get("end", None)
    bench_symbol = cfg.get("benchmark", {}).get("symbol", "^NSEI")

    if is_trend_follow:
        # Single-instrument trend-following — use benchmark as the traded asset
        log.info("Mode: Nifty trend-following (single instrument)")
        bench_df = fetch_benchmark(bench_symbol, start=start)
        if bench_df.empty:
            raise click.ClickException(f"No benchmark data for {bench_symbol}")

        # Build a single-column price panel from the benchmark
        prices = bench_df[["adj_close"]].rename(columns={"adj_close": "NIFTY"})
        log.info(f"Price panel: {len(prices)} days x 1 instrument")

        sig_cfg = cfg.get("signal", {})
        signal_type = sig_cfg.get("type", "trend_follow")
        freq = cfg.get("portfolio", {}).get("rebalance_freq", "ME")

        if signal_type == "trend_follow_momentum":
            # Momentum-based: risk-on when N-month return is positive
            lookback = sig_cfg.get("lookback_months", 10)
            lookback_days = lookback * 21  # trading days
            mom_return = bench_df["adj_close"] / bench_df["adj_close"].shift(lookback_days) - 1
            risk_on = mom_return > 0
            risk_on = risk_on.fillna(False)
            risk_on_pct = risk_on.sum() / len(risk_on)
            log.info(f"Trend signal: {lookback}-month momentum, risk-on {risk_on_pct:.0%} of the time")
        else:
            # SMA-based: risk-on when price above SMA
            sma_window = sig_cfg.get("sma_window", 200)
            risk_on = absolute_trend_filter(bench_df["adj_close"], sma_window=sma_window)
            risk_on_pct = risk_on.sum() / len(risk_on)
            log.info(f"Trend signal: {sma_window}-day SMA, risk-on {risk_on_pct:.0%} of the time")

        # Build target weights: 100% NIFTY when risk-on, 0% when risk-off
        daily_weights = pd.DataFrame(0.0, index=prices.index, columns=["NIFTY"])
        daily_weights.loc[risk_on, "NIFTY"] = 1.0
        rebal_weights = resample_to_rebalance_dates(daily_weights, frequency=freq)
        log.info(f"Target weights built: trend-follow, rebalance={freq}")
    else:
        if universe_mode == "nse500_ex_nifty50":
            tickers = smallcap_universe(include_dead=survivorship_free)
        elif universe_mode == "nse500":
            tickers = nse500_starter_tickers()
        elif universe_mode == "nifty50":
            tickers = nifty50_tickers()
        else:
            raise click.BadParameter(f"Unknown universe mode: {universe_mode}")

        if smoke:
            tickers = tickers[:20]
            log.info(f"SMOKE TEST mode — using first {len(tickers)} tickers")

        bias_label = "SURVIVORSHIP-FREE" if survivorship_free else "survivor-only"
        log.info(f"Universe: {len(tickers)} tickers ({bias_label})")

        # Data
        price_dict = fetch_many(tickers, start=start, end=end, force_refresh=force_refresh)
        prices = to_price_panel(price_dict, field="adj_close")
        log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

        # Benchmark
        bench_df = fetch_benchmark(bench_symbol, start=start)

        trend_cfg = cfg.get("trend_filter", {})
        trend_enabled = bool(trend_cfg.get("enabled", False))

        if not trend_enabled:
            log.info("Trend filter: DISABLED (config)")
            risk_on = None
        elif bench_df.empty:
            log.warning(f"No benchmark data for {bench_symbol} — trend filter disabled.")
            risk_on = None
        else:
            sma_window = trend_cfg.get("sma_window", 200)
            risk_on = absolute_trend_filter(bench_df["adj_close"], sma_window=sma_window)
            log.info(f"Trend filter: ENABLED — {bench_symbol} above {sma_window}-day SMA")

        # Signal
        sig_cfg = cfg.get("signal", {})
        signal_type = sig_cfg.get("type", "momentum_n_m")

        # Portfolio
        port_cfg = cfg.get("portfolio", {})
        top_n = port_cfg.get("top_n", 15)
        freq = port_cfg.get("rebalance_freq", "ME")

        if signal_type == "value_quality":
            # V+Q: fetch historical fundamentals and compute scores at each rebalance date
            from trading.config import CACHE_DIR
            cache_dir = CACHE_DIR / "fundamentals"
            hist_fund = fetch_historical_fundamentals(tickers, max_workers=15, cache_dir=cache_dir)

            # Generate quarterly rebalance dates from price index
            rebal_dates = prices.resample(freq).last().index
            scores = compute_historical_scores(hist_fund, prices, rebal_dates)

            if scores.empty:
                raise click.ClickException("No valid V+Q scores — insufficient fundamental data")
            log.info(f"V+Q scores: {len(scores)} rebalance dates")

            # Trim prices to start from the first valid scoring date
            # (avoids 10+ years of flat equity from missing fundamental data)
            first_score_date = scores.index[0]
            trim_start = first_score_date - pd.DateOffset(months=1)
            prices = prices.loc[trim_start:]
            log.info(f"Trimmed prices to {prices.index[0].date()} — {prices.index[-1].date()}")

            # For V+Q, scores are already at rebalance dates — build weights directly
            daily_weights = top_n_equal_weight(scores, top_n=top_n, risk_on=risk_on)
        else:
            lookback = sig_cfg.get("lookback_months", 12)
            skip = sig_cfg.get("skip_months", 1)
            scores = momentum_n_m(prices, lookback_months=lookback, skip_months=skip)
            log.info(f"Momentum: {lookback}m-{skip}m computed")
            daily_weights = top_n_equal_weight(scores, top_n=top_n, risk_on=risk_on)
        rebal_weights = resample_to_rebalance_dates(daily_weights, frequency=freq)
        log.info(f"Target weights built: top-{top_n} equal-weight, rebalance={freq}")

    # Costs
    cost_cfg_dict = cfg.get("costs", {})
    cost_config = CostConfig(
        slippage_per_side=cost_cfg_dict.get("slippage_per_side", 0.003)
    )

    # Run
    log.info("Running backtest...")
    result = run_backtest(
        prices=prices,
        target_weights_at_rebal=rebal_weights,
        cost_config=cost_config,
        initial_capital=cfg.get("initial_capital", 1.0),
    )
    log.info("Backtest complete")

    # Metrics
    rfr = cfg.get("risk_free_rate", 0.06)  # India 10Y yield proxy
    sm = summary(result.equity_curve, result.returns, risk_free_rate=rfr)
    print()
    print(format_summary(sm))
    print(f"\nCost drag (annualized est.): {result.cost_drag_annualized:.2%}")
    print(f"Rebalances: {len(result.rebalance_dates)}")
    print(f"Average turnover per rebalance: {result.turnover.mean():.1%}")

    # Outputs
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_sfree" if survivorship_free else ""
    out_dir = OUTPUTS_DIR / f"{cfg.get('name', 'run')}{suffix}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result.equity_curve.to_csv(out_dir / "equity_curve.csv")
    result.returns.to_csv(out_dir / "returns.csv")
    result.turnover.to_csv(out_dir / "turnover.csv")
    result.weights.to_csv(out_dir / "weights.csv")

    with open(out_dir / "summary.json", "w") as f:
        json.dump(sm, f, indent=2, default=str)

    # Plots
    bench_price = bench_df["adj_close"] if not bench_df.empty else None
    plot_equity_curve(result.equity_curve, bench_price, out_dir / "equity_curve.png")
    plot_drawdown(result.equity_curve, out_dir / "drawdown.png")
    plot_monthly_heatmap(result.returns, out_dir / "monthly_heatmap.png")
    plot_rolling_sharpe(result.returns, 252, out_dir / "rolling_sharpe.png")

    log.info(f"Results saved to: {out_dir}")
    print(f"\nOutputs: {out_dir}")


@main.command()
@click.option("--config", "-c", required=True, help="Path to strategy YAML config.")
@click.option("--force-refresh", is_flag=True, help="Re-download all price data.")
@click.option("--dry-run", is_flag=True, help="Show what would trade without executing.")
def paper(config: str, force_refresh: bool, dry_run: bool) -> None:
    """Run one paper-trading rebalance cycle.

    Uses the same signal/portfolio pipeline as backtest, but against current
    market data. Persists state between runs so a monthly cron can drive it.
    """
    from trading.execution.paper import (
        PaperState,
        append_equity,
        append_trades,
        rebalance,
        save_signals,
    )

    ensure_dirs()
    log = setup_logging("paper")

    cfg = load_strategy_config(config)
    strategy_name = cfg.get("name", "unnamed")
    log.info(f"Paper trade — strategy: {strategy_name}")

    # Load or create state
    state = PaperState.load(strategy_name)
    is_fresh = state.last_rebalance is None
    log.info(
        f"State: equity={state.equity:.4f}, positions={len(state.holdings)}, "
        f"last_rebalance={state.last_rebalance or 'never'}"
    )

    # Universe
    universe_mode = cfg.get("universe", {}).get("mode", "nse500_ex_nifty50")
    if universe_mode == "nse500_ex_nifty50":
        tickers = smallcap_universe()
    elif universe_mode == "nse500":
        tickers = nse500_starter_tickers()
    elif universe_mode == "nifty50":
        tickers = nifty50_tickers()
    else:
        raise click.BadParameter(f"Unknown universe mode: {universe_mode}")
    log.info(f"Universe: {len(tickers)} tickers")

    # Signal type
    sig_cfg = cfg.get("signal", {})
    signal_type = sig_cfg.get("type", "momentum_n_m")

    # Fetch recent data — need enough history for signal
    lookback = sig_cfg.get("lookback_months", 12)
    history_months = lookback + 2
    start_date = pd.Timestamp.now() - pd.DateOffset(months=history_months)
    start = start_date.strftime("%Y-%m-%d")

    log.info(f"Fetching prices from {start}...")
    price_dict = fetch_many(tickers, start=start, force_refresh=force_refresh)
    prices = to_price_panel(price_dict, field="adj_close")
    log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

    # Benchmark + trend filter
    bench_symbol = cfg.get("benchmark", {}).get("symbol", "^NSEI")
    bench_df = fetch_benchmark(bench_symbol, start=start)

    trend_cfg = cfg.get("trend_filter", {})
    trend_enabled = bool(trend_cfg.get("enabled", False))

    if not trend_enabled:
        risk_on = None
    elif bench_df.empty:
        log.warning(f"No benchmark data for {bench_symbol} — trend filter disabled.")
        risk_on = None
    else:
        sma_window = trend_cfg.get("sma_window", 200)
        risk_on = absolute_trend_filter(bench_df["adj_close"], sma_window=sma_window)
        latest_risk = bool(risk_on.iloc[-1]) if not risk_on.empty else True
        log.info(f"Trend filter: {'RISK-ON' if latest_risk else 'RISK-OFF'}")

    # Signal
    if signal_type == "value_quality":
        # V+Q: use current fundamentals for paper trading picks
        fund = fetch_fundamentals(tickers, max_workers=15)
        latest_scores = score_value_quality(fund)
        if latest_scores.empty:
            log.error("No valid V+Q scores — insufficient fundamental data?")
            raise click.Abort()
    else:
        skip = sig_cfg.get("skip_months", 1)
        scores = momentum_n_m(prices, lookback_months=lookback, skip_months=skip)
        latest_scores = scores.iloc[-1].dropna()
        if latest_scores.empty:
            log.error("No valid momentum scores — insufficient price history?")
            raise click.Abort()

    # Portfolio target
    port_cfg = cfg.get("portfolio", {})
    top_n = port_cfg.get("top_n", 15)

    # Check trend filter for today
    if risk_on is not None and not risk_on.empty and not bool(risk_on.iloc[-1]):
        log.info("RISK-OFF: trend filter says go to cash")
        target_weights = {}
    else:
        picks = latest_scores.nlargest(top_n)
        per_name = 1.0 / top_n
        target_weights = {t: per_name for t in picks.index}
        log.info(f"Target: top-{top_n} picks: {list(picks.index)}")

    # Save signals for audit
    today = datetime.now().date()
    save_signals(state, latest_scores, today)

    if dry_run:
        print("\n=== DRY RUN ===")
        print(f"Strategy: {strategy_name}")
        print(f"Current equity: {state.equity:.4f}")
        print(f"Current positions: {len(state.holdings)}")
        print(f"\nTarget portfolio ({len(target_weights)} names):")
        for t, w in sorted(target_weights.items(), key=lambda x: -x[1]):
            held = "  (held)" if t in state.holdings else "  NEW"
            print(f"  {t}: {w:.2%}{held}")

        # Show exits
        exits = [t for t in state.holdings if t not in target_weights]
        if exits:
            print(f"\nExits: {exits}")
        print("\nRun without --dry-run to execute.")
        return

    # Execute rebalance
    cost_cfg_dict = cfg.get("costs", {})
    cost_config = CostConfig(
        slippage_per_side=cost_cfg_dict.get("slippage_per_side", 0.003)
    )

    trades = rebalance(
        state=state,
        target_weights=target_weights,
        prices=prices,
        rebalance_date=today,
        cost_config=cost_config,
    )

    # Persist
    append_trades(state, trades)
    append_equity(state)
    state.save()

    # Print summary
    print(f"\n{'='*50}")
    print(f"Paper rebalance complete — {strategy_name}")
    print(f"{'='*50}")
    print(f"Date: {today}")
    print(f"Trades: {len(trades)}")
    print(f"Equity: {state.equity:.4f}")
    print(f"Positions: {len(state.holdings)}")
    print(f"Cash weight: {state.cash_weight:.2%}")
    if trades:
        total_cost = sum(t.cost for t in trades)
        print(f"Transaction costs: {total_cost:.4%}")
        print(f"\nTrades:")
        for t in trades:
            print(f"  {t.side.upper():4s} {t.ticker}: {t.old_weight:.2%} -> {t.new_weight:.2%}")
    print(f"\nState saved to: {state.state_dir()}")


@main.command()
@click.option("--config", "-c", required=True, help="Path to strategy YAML config.")
def paper_status(config: str) -> None:
    """Show current paper-trading state and performance."""
    from trading.execution.paper import PaperState

    cfg = load_strategy_config(config)
    strategy_name = cfg.get("name", "unnamed")
    state = PaperState.load(strategy_name)

    print(f"\n{'='*50}")
    print(f"Paper Trading Status — {strategy_name}")
    print(f"{'='*50}")
    print(f"Created: {state.created}")
    print(f"Last rebalance: {state.last_rebalance or 'never'}")
    print(f"Equity: {state.equity:.4f}")
    print(f"Total trades: {state.trade_count}")
    print(f"Positions: {len(state.holdings)}")
    print(f"Cash weight: {state.cash_weight:.2%}")

    if state.holdings:
        print(f"\nCurrent holdings:")
        for t, w in sorted(state.holdings.items(), key=lambda x: -x[1]):
            print(f"  {t}: {w:.2%}")

    # Show trade history if available
    trades_path = state.state_dir() / "trades.csv"
    if trades_path.exists():
        trades = pd.read_csv(trades_path)
        print(f"\nRecent trades (last 20):")
        print(trades.tail(20).to_string(index=False))

    # Show equity history if available
    equity_path = state.state_dir() / "equity.csv"
    if equity_path.exists():
        eq = pd.read_csv(equity_path)
        print(f"\nEquity history:")
        print(eq.to_string(index=False))


@main.command()
@click.option("--config", "-c", required=True, help="Path to strategy YAML config.")
@click.option("--force-refresh", is_flag=True, help="Re-download all price data.")
def paper_compare(config: str, force_refresh: bool) -> None:
    """Compare paper trading results against a backtest over the same period.

    This is the Phase 1 graduation gate: paper must track backtest within ±3%.
    """
    from trading.execution.tracker import (
        format_comparison,
        run_comparison,
        save_comparison,
    )

    ensure_dirs()
    log = setup_logging("tracker")

    cfg = load_strategy_config(config)
    strategy_name = cfg.get("name", "unnamed")
    log.info(f"Paper vs backtest comparison — {strategy_name}")

    # Universe
    universe_mode = cfg.get("universe", {}).get("mode", "nse500_ex_nifty50")
    if universe_mode == "nse500_ex_nifty50":
        tickers = smallcap_universe()
    elif universe_mode == "nse500":
        tickers = nse500_starter_tickers()
    elif universe_mode == "nifty50":
        tickers = nifty50_tickers()
    else:
        raise click.BadParameter(f"Unknown universe mode: {universe_mode}")

    # Fetch data — need full history for signals
    sig_cfg = cfg.get("signal", {})
    lookback = sig_cfg.get("lookback_months", 12)
    history_months = lookback + 2
    start_date = pd.Timestamp.now() - pd.DateOffset(months=history_months)
    start = start_date.strftime("%Y-%m-%d")

    log.info(f"Fetching prices from {start}...")
    price_dict = fetch_many(tickers, start=start, force_refresh=force_refresh)
    prices = to_price_panel(price_dict, field="adj_close")

    # Benchmark + trend filter
    bench_symbol = cfg.get("benchmark", {}).get("symbol", "^NSEI")
    bench_df = fetch_benchmark(bench_symbol, start=start)

    trend_cfg = cfg.get("trend_filter", {})
    trend_enabled = bool(trend_cfg.get("enabled", False))

    if not trend_enabled:
        risk_on = None
    elif bench_df.empty:
        risk_on = None
    else:
        sma_window = trend_cfg.get("sma_window", 200)
        risk_on = absolute_trend_filter(bench_df["adj_close"], sma_window=sma_window)

    # Signal + portfolio weights (same pipeline as backtest)
    skip = sig_cfg.get("skip_months", 1)
    scores = momentum_n_m(prices, lookback_months=lookback, skip_months=skip)

    port_cfg = cfg.get("portfolio", {})
    top_n = port_cfg.get("top_n", 15)
    freq = port_cfg.get("rebalance_freq", "ME")

    daily_weights = top_n_equal_weight(scores, top_n=top_n, risk_on=risk_on)
    rebal_weights = resample_to_rebalance_dates(daily_weights, frequency=freq)

    # Cost config
    cost_cfg_dict = cfg.get("costs", {})
    cost_config = CostConfig(
        slippage_per_side=cost_cfg_dict.get("slippage_per_side", 0.003)
    )

    rfr = cfg.get("risk_free_rate", 0.06)

    # Run comparison
    report = run_comparison(
        strategy_name=strategy_name,
        prices=prices,
        target_weights_at_rebal=rebal_weights,
        cost_config=cost_config,
        risk_free_rate=rfr,
    )

    if report is None:
        print("Cannot compare — no paper trading history yet.")
        print("Run at least one paper rebalance first.")
        return

    # Save and display
    save_comparison(strategy_name, report)

    print(f"\n{'='*50}")
    print(f"Paper vs Backtest — {strategy_name}")
    print(f"{'='*50}")
    print()
    print(format_comparison(report))

    if report.passes_gate:
        print(f"\nGate: PASS — paper tracks backtest within ±{report.gate_threshold:.0%}")
    else:
        print(f"\nGate: FAIL — CAGR difference {report.cagr_diff:.2%} exceeds ±{report.gate_threshold:.0%}")

    if report.days_tracked < 90:
        remaining = 90 - report.days_tracked
        print(f"\nNote: only {report.days_tracked} days tracked. Need 90+ days for graduation ({remaining} more).")


@main.command()
@click.option("--config", "-c", required=True, help="Path to strategy YAML config.")
@click.option("--capital", type=float, required=True, help="Total capital to deploy (in INR).")
@click.option("--dry-run", is_flag=True, help="Show orders without placing them.")
@click.option("--force-refresh", is_flag=True, help="Re-download all price data.")
def live(config: str, capital: float, dry_run: bool, force_refresh: bool) -> None:
    """Run a live rebalance via Kite Connect (real money).

    Computes target portfolio from signals, fetches current holdings from
    broker, calculates order deltas, and places CNC market orders.

    SAFETY: Always use --dry-run first to review orders before executing.
    """
    from trading.execution.kite import (
        compute_orders,
        get_holdings,
        get_ltp,
        log_orders,
        login,
        place_orders,
    )

    ensure_dirs()
    log = setup_logging("live")

    cfg = load_strategy_config(config)
    strategy_name = cfg.get("name", "unnamed")

    # Safety gate: require explicit confirmation for live trading
    if not dry_run:
        print(f"\n{'!'*50}")
        print(f"  LIVE TRADING — REAL MONEY")
        print(f"  Strategy: {strategy_name}")
        print(f"  Capital: ₹{capital:,.0f}")
        print(f"{'!'*50}")
        if not click.confirm("\nAre you sure you want to place real orders?"):
            print("Aborted.")
            return

    log.info(f"Live rebalance — {strategy_name}, capital=₹{capital:,.0f}")

    # Authenticate with Kite
    kite = login()

    # Universe
    universe_mode = cfg.get("universe", {}).get("mode", "nse500_ex_nifty50")
    if universe_mode == "nse500_ex_nifty50":
        tickers = smallcap_universe()
    elif universe_mode == "nse500":
        tickers = nse500_starter_tickers()
    elif universe_mode == "nifty50":
        tickers = nifty50_tickers()
    else:
        raise click.BadParameter(f"Unknown universe mode: {universe_mode}")
    log.info(f"Universe: {len(tickers)} tickers")

    # Signal pipeline (same as backtest/paper)
    sig_cfg = cfg.get("signal", {})
    lookback = sig_cfg.get("lookback_months", 12)
    history_months = lookback + 2
    start_date = pd.Timestamp.now() - pd.DateOffset(months=history_months)
    start = start_date.strftime("%Y-%m-%d")

    log.info(f"Fetching prices from {start}...")
    price_dict = fetch_many(tickers, start=start, force_refresh=force_refresh)
    prices = to_price_panel(price_dict, field="adj_close")
    log.info(f"Price panel: {prices.shape[0]} days x {prices.shape[1]} tickers")

    # Benchmark + trend filter
    bench_symbol = cfg.get("benchmark", {}).get("symbol", "^NSEI")
    bench_df = fetch_benchmark(bench_symbol, start=start)

    trend_cfg = cfg.get("trend_filter", {})
    trend_enabled = bool(trend_cfg.get("enabled", False))

    if not trend_enabled:
        risk_on = None
    elif bench_df.empty:
        risk_on = None
    else:
        sma_window = trend_cfg.get("sma_window", 200)
        risk_on = absolute_trend_filter(bench_df["adj_close"], sma_window=sma_window)
        latest_risk = bool(risk_on.iloc[-1]) if not risk_on.empty else True
        log.info(f"Trend filter: {'RISK-ON' if latest_risk else 'RISK-OFF'}")

    # Signal
    skip = sig_cfg.get("skip_months", 1)
    scores = momentum_n_m(prices, lookback_months=lookback, skip_months=skip)
    latest_scores = scores.iloc[-1].dropna()

    if latest_scores.empty:
        log.error("No valid momentum scores.")
        raise click.Abort()

    # Target weights
    port_cfg = cfg.get("portfolio", {})
    top_n = port_cfg.get("top_n", 15)

    if risk_on is not None and not risk_on.empty and not bool(risk_on.iloc[-1]):
        log.info("RISK-OFF: trend filter says go to cash")
        target_weights = {}
    else:
        picks = latest_scores.nlargest(top_n)
        per_name = 1.0 / top_n
        target_weights = {t: per_name for t in picks.index}
        log.info(f"Target: top-{top_n} picks: {list(picks.index)}")

    # Current broker state
    current_holdings = get_holdings(kite)
    log.info(f"Current broker holdings: {len(current_holdings)} positions")

    # Get live prices — try Kite LTP first, fall back to yfinance close prices
    all_symbols = list(set(
        list(target_weights.keys()) + list(current_holdings.keys())
    ))
    try:
        live_prices = get_ltp(kite, all_symbols) if all_symbols else {}
        log.info(f"Fetched LTP from Kite for {len(live_prices)} symbols")
    except Exception as e:
        log.warning(f"Kite LTP failed ({e}), using yfinance close prices")
        # Fall back to last available close from the price panel (handles weekends/holidays)
        last_valid = prices[prices.columns.intersection(all_symbols)].ffill().iloc[-1]
        live_prices = {s: float(last_valid[s]) for s in last_valid.index if pd.notna(last_valid[s])}
        log.info(f"Using yfinance close prices for {len(live_prices)} symbols")

    # Compute orders
    orders = compute_orders(
        target_weights=target_weights,
        current_holdings=current_holdings,
        prices=live_prices,
        total_capital=capital,
    )

    if not orders:
        print("\nNo orders needed — portfolio already at target.")
        return

    # Display order plan
    print(f"\n{'='*60}")
    print(f"Order Plan — {strategy_name}")
    print(f"Capital: ₹{capital:,.0f}")
    print(f"{'='*60}")

    total_buy = sum(o["estimated_value"] for o in orders if o["side"] == "BUY")
    total_sell = sum(o["estimated_value"] for o in orders if o["side"] == "SELL")

    sells = [o for o in orders if o["side"] == "SELL"]
    buys = [o for o in orders if o["side"] == "BUY"]

    if sells:
        print(f"\nSELLS ({len(sells)} orders, ~₹{total_sell:,.0f}):")
        for o in sells:
            price = live_prices.get(o["symbol"], 0)
            print(f"  SELL {o['quantity']:>5d} x {o['symbol']:<15s} @ ₹{price:>10,.2f} = ₹{o['estimated_value']:>12,.0f}")

    if buys:
        print(f"\nBUYS ({len(buys)} orders, ~₹{total_buy:,.0f}):")
        for o in buys:
            price = live_prices.get(o["symbol"], 0)
            print(f"  BUY  {o['quantity']:>5d} x {o['symbol']:<15s} @ ₹{price:>10,.2f} = ₹{o['estimated_value']:>12,.0f}")

    print(f"\nNet cash flow: ₹{total_sell - total_buy:,.0f}")

    if dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — no orders placed.")
        print("Run without --dry-run to execute.")
        return

    # Place orders
    print(f"\nPlacing {len(orders)} orders...")
    results = place_orders(kite, orders, dry_run=False)

    # Log results
    log_path = DATA_DIR / "live" / strategy_name / "orders.csv"
    log_orders(results, log_path)

    # Summary
    placed = [r for r in results if r["status"] == "placed"]
    failed = [r for r in results if r["status"].startswith("failed")]

    print(f"\n{'='*60}")
    print(f"Execution complete")
    print(f"{'='*60}")
    print(f"Placed: {len(placed)}/{len(orders)}")
    if failed:
        print(f"Failed: {len(failed)}")
        for f_ in failed:
            print(f"  {f_['side']} {f_['symbol']}: {f_['status']}")
    print(f"\nOrder log: {log_path}")


if __name__ == "__main__":
    main()
