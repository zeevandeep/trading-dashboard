# JD Quant — Trading Dashboard

Personal quantitative trading system. Two live strategies running real capital.

## Strategies

| Name | Ticker | Broker | Capital | Rebalance |
|------|--------|--------|---------|-----------|
| **Ascent** | smallcap_momentum_v2_live | Zerodha Kite | ~Rs 1L | Monthly (manual, Kite app) |
| **Bedrock** | value_quality_v1_live | AngelOne | ~Rs 1L | Quarterly (automated via GH Actions) |

## CRITICAL RULES

1. **NEVER place buy/sell orders without explicit user confirmation.** Always show a dry-run first and ask "place real orders?" before executing. This is non-negotiable.
2. **ALWAYS update CHANGELOG.md** when making code changes. Never prompt the user to do it — just do it.
3. **Never ask JD to do things manually** if there's a programmatic path.
4. Broker SDK imports (`kiteconnect`, `SmartApi`) must be **lazy** (inside functions) — CI doesn't have them installed.

## Key Files

```
src/trading/
  config.py                    # DATA_DIR, paths
  execution/kite.py            # Kite order placement + log_orders (ORDERS_SCHEMA)
  execution/angel.py           # AngelOne order placement
  signals/value_quality.py     # Bedrock scoring (Screener.in scraper)
  data/loader.py               # Price loading via yfinance

scripts/
  daily_live_mark.py           # Evening mark-to-market for live strategies
  monthly_live_rebalance.py    # Ascent monthly rebalance (Kite)
  bedrock_live_rebalance.py    # Bedrock quarterly rebalance (AngelOne)
  check_order_fills.py         # 9:45 AM IST fill check (GH Actions)
  telegram_summary.py          # Daily Telegram report
  trend_filter_paper_mark.py   # NIFTY 10m filter paper tracker
  refresh_fundamentals_cache.py # Quarterly Screener.in scrape

data/
  live/smallcap_momentum_v2_live/   # Ascent live data
    equity.csv                       # NAV history (never go backwards)
    orders.csv                       # 8-col schema: symbol,side,quantity,estimated_value,order_id,status,limit_price,timestamp
    positions.csv
    kite_snapshot.json               # Pre-rebalance holdings snapshot (date = yesterday)
    capital_events.csv
  live/value_quality_v1_live/       # Bedrock live data (same structure)
  paper/ascent_trend_filtered/      # Trend filter paper portfolio
  universe/nse500_starter.csv       # 213 tickers (NSE 500 minus Nifty 50 + dead tickers removed)
  cache/fundamentals/               # historical_fundamentals.parquet (Screener.in cache)

.github/workflows/
  daily-mark.yml                    # 9:45 AM IST fill check + 6 PM IST daily mark
  quarterly-bedrock-rebalance.yml   # Bedrock rebalance (dry-run default, execute=true for live)
  rebalance-reminders.yml           # Monthly Telegram reminder on 28th
  refresh-fundamentals.yml          # Quarterly Screener.in cache refresh
```

## Infrastructure

- **Order Proxy**: `http://167.71.227.66:8001` (DigitalOcean droplet, klassi.in)
  - Port 8001 restricted to JD's IP (49.43.5.199) + PROXY_API_KEY header
  - Routes Kite orders (Kite requires whitelisted IP, DO IP is whitelisted)
- **Dashboard**: Render.com (auto-deploy from GitHub main)
- **CI**: GitHub Actions (`zeevandeep/trading-dashboard`)
- **Telegram**: Bot alerts for daily marks, fill checks, rebalance previews
- **Secrets needed in GH Actions**: `ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SCREENER_CSRFTOKEN`, `SCREENER_SESSIONID`, `PROXY_API_KEY`

## Known Gotchas

### orders.csv column shift
`log_orders()` enforces a fixed 8-column schema via `reindex(columns=ORDERS_SCHEMA)`. If you add/remove fields from the results dict, **always update ORDERS_SCHEMA** in both `kite.py` and `angel.py`.

### kite_snapshot.json date trap
`compute_holdings()` uses strict `>` comparison: orders placed on the snapshot date are excluded. Snapshot date must always be **yesterday** (not today). `_post_rebalance_cleanup()` handles this automatically after rebalances.

### NAV computation
NAV = `market_value / initial_invested` (capital-event adjusted). NAV starts at 1.0. `equity.csv` rows must never go backwards in date — a pre-commit hook enforces this.

### Kite OAuth
Kite requires browser-based daily login. Cannot be automated in CI. Fill checks send a Telegram reminder for manual verification instead.

### AngelOne AB4036
IEX and BAJAJHLDNG are on NSE cautionary listing. Cannot be traded via API. Must be placed manually in the AngelOne app.

### yfinance dead tickers
8 tickers removed from universe (CENTURYTEX, GUJGASLTD, IBULHSGFIN, KALPATPOWR, L&TFH, MINDTREE, PEL, ZOMATO). If a ticker fails with "possibly delisted", remove it from `data/universe/nse500_starter.csv`.

## NAV / Equity CSV Format

```csv
date,nav,market_value,invested,pnl,n_positions
2026-09-27,1.0,66035.79,66035.79,0,15
```

Trend filter equity has extra columns: `regime,ascent_nav,nifty_10m_ret`

## Pending Items

- SELL 13 × IEX + BUY 1 × BAJAJHLDNG via AngelOne app (exchange-blocked via API)
- Add `SCREENER_CSRFTOKEN` + `SCREENER_SESSIONID` to GitHub Secrets (for fundamentals refresh)
