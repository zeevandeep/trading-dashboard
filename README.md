# Trading

Personal systematic trading infrastructure. Indian equities first, US ETFs second, options and commodities later.

## Design principle

One framework, many strategies. The same code runs backtests on historical data, paper trades on live data, and executes real orders on a broker — the only difference is which adapter the execution layer routes to.

## Architecture

```
src/trading/
  data/          - Universe definition, price data fetching, local caching
  signals/       - Factor calculations (momentum, trend filter, etc.)
  portfolio/     - Portfolio construction from ranked signals
  backtest/      - Simulation engine, transaction cost model
  reporting/     - Performance metrics and charts
  execution/     - Broker adapters (paper, Zerodha Kite, Schwab later)
  utils/         - Logging, config loading

configs/         - Strategy configs (YAML, one per strategy)
data/universe/   - Static universe CSVs (Nifty 50, NSE 500)
data/cache/      - Downloaded price data (parquet, gitignored)
outputs/         - Backtest results (charts, CSVs, gitignored)
logs/            - Runtime logs (gitignored)
notebooks/       - Research notebooks
tests/           - Unit tests
```

## Roadmap (phased)

**Phase 0 — Backtest (weeks 1–4).** Build framework. Run Indian smallcap momentum (NSE 500 ex Nifty 50) on 2010–2024. Validate edge exists. Go/no-go: >18% CAGR, <45% max DD, Sharpe >1.0.

**Phase 1 — Paper trade (months 2–7).** Same code, live data, simulated orders. Validate pipeline, signal generation, reliability.

**Phase 2 — Micro-live (months 8–10).** ₹50K–₹1L deployed on simplified 5-position variant. Validate execution quality and psychology.

**Phase 3 — Scale (month 11+).** Graduation-criteria-based capital ramp: ₹1L → ₹5L → ₹15L → ₹30L → ₹50L → ₹1cr.

## First strategy

**Indian Smallcap Monthly Momentum**

- Universe: NSE 500 constituents ex Nifty 50 (~450 names)
- Signal: 12-month-minus-1-month total return (Jegadeesh–Titman)
- Trend filter: Nifty 500 above its 200-day SMA (else cash)
- Portfolio: top 15 names equal-weighted
- Rebalance: monthly, last trading day
- Costs: brokerage + STT + GST + stamp duty + 0.3% slippage

## Setup

### Prerequisites
- Python 3.11+
- `uv` or `pip` for package management

### Install

```bash
cd /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configure secrets

Edit `.env` (never committed) with your Kite Connect API key and secret. `.env.example` shows the template.

### Run first backtest

```bash
python main.py backtest --config configs/smallcap_momentum_v1.yaml
```

Outputs land in `outputs/<run_timestamp>/`: equity curve PNG, drawdown PNG, metrics CSV, trade log CSV.

## Strategy lifecycle gates

New capital is deployed only after earning it. No calendar-based scaling.

| Phase | Capital | Graduation criteria |
|---|---|---|
| Backtest | — | >18% CAGR, <45% DD, Sharpe >1.0 on 2010–2024 |
| Paper | — | 3+ mo live data, paper tracks backtest ±3%, zero code failures 60 days |
| Micro-live | ₹50K–₹1L | Live fills within 0.5% of paper, no manual overrides, one DD event survived |
| Tranche 1 | ₹5L | 6 mo live at ₹1L, Sharpe live ≥ 70% of backtest Sharpe |
| Tranche 2 | ₹15L | Full 15-name strategy tracking, API automation clean |
| Tranche 3 | ₹30L | Second strategy live, options sleeve in paper |
| Tranche 4 | ₹50L | Survived a broad market event (-10%+) |
| Tranche 5 | ₹1cr+ | Full market regime survived, 70% of backtest performance live |

## Target returns (realistic)

- **Years 1–2 (learning, small capital):** 22–28% CAGR target, 35–45% DD tolerance
- **Years 3–4 (de-risking as capital grows):** 20–24%, 30% DD tolerance
- **Year 5+ (mature):** 18–22%, 25% DD tolerance

Benchmark blend target across full stack (Option 1 systematic + Option 2 options + Option 3 concentrated): **20–25% blended CAGR base case.**

## Repo rules

- Never commit secrets. `.env` is in `.gitignore`.
- Every strategy has a YAML config; code is strategy-agnostic.
- Every backtest run is reproducible from its config file.
- Trade logs are append-only; historical results are never overwritten.
