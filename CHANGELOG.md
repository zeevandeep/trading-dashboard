# Changelog

All notable changes to JD Quant are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Post-rebalance auto-safeguards (2026-10-13)

#### Added
- **`scripts/monthly_live_rebalance.py`** + **`scripts/bedrock_live_rebalance.py`** — `_post_rebalance_cleanup()` runs automatically after every real execution (skipped on dry-run). Does three things:
  1. **orders.csv validation** — detects NaN timestamps (symptom of column-shift bug) and prints a loud warning immediately instead of failing silently days later.
  2. **Snapshot refresh** — saves current (pre-rebalance) holdings to `kite_snapshot.json` / `holdings_snapshot.json` with `date = yesterday`. This guarantees today's placed orders are always applied on top by `compute_holdings` (which uses strict `>`). Eliminates the "snapshot dated same day as rebalance → orders silently excluded" bug.
  3. **Immediate daily mark** — runs `mark_live_strategy()` right after orders log, so equity.csv reflects the new holdings without waiting for the nightly cron.
- **`scripts/kite_portfolio_sync.py`** — `fetch_and_save_snapshot()` now accepts an optional `kite=` parameter (avoids a second login when called from the rebalance script). Snapshot date also changed to yesterday consistently.

### Universe cleanup + proxy firewall + Bedrock capital + Ascent holdings fix (2026-10-13)

#### Fixed
- **`data/live/smallcap_momentum_v2_live/orders.csv`** — Repaired 66 corrupt rows from prior rebalances: orders placed via `place_orders_remote()` were written with 7 columns (missing `estimated_value`), causing a column shift that put the limit price in the `status` slot and the timestamp in `limit_price`. All rows corrected via column rotation.
- **`data/live/smallcap_momentum_v2_live/kite_snapshot.json`** — Changed `date` from `2026-10-01` to `2026-09-30` so that Oct 1 rebalance orders (ADANIPOWER SELL 64, CUB SELL 58 + 3 new entries) are applied by `compute_holdings`. Previously, the strict `>` comparison excluded same-day orders from the snapshot, leaving stale pre-rebalance holdings (ADANIPOWER, CUB) in all Oct marks.
- **`src/trading/execution/kite.py`** — `place_orders_remote()` now includes `estimated_value` in results dict (was missing, causing column-shift bug in `log_orders`). `log_orders()` now enforces a fixed 8-column schema via `reindex()` — same fix previously applied to `angel.py`.

#### Added
- **`data/live/value_quality_v1_live/capital_events.csv`** — Initial Rs 66,035.79 capital event on 2026-09-27. Required for NAV computation to correctly separate investment returns from capital additions.
- **`data/universe/nse500_starter.csv`** — Removed 8 confirmed-dead yfinance tickers (CENTURYTEX, GUJGASLTD, IBULHSGFIN, KALPATPOWR, L&TFH, MINDTREE, PEL, ZOMATO — all return "possibly delisted, no data found"). Added KPIL (Kalpataru Projects International) as replacement for KALPATPOWR. Universe: 220 → 213 tickers.

#### Infrastructure
- **Port 8001 on 167.71.227.66** — Restricted to JD's IP (49.43.5.199) only. Previously open to the world; now only accessible from known-good address. API key auth (PROXY_API_KEY) remains as second factor.
- **Ascent equity recomputed** — Oct 1–13 marks regenerated with correct 15-position post-rebalance holdings. Oct 1 NAV reset correctly shows the rebalance transition.

### BSE exchange support + daily mark price fill-forward + equity.csv guard (2026-10-13)

#### Fixed
- **`order_proxy.py`** — token_cache now stores the actual `tradingsymbol` from `searchScrip` results (not constructed as `SYM-EQ`). Fixes AB1019 "symbol/token mismatch" errors on BSE, where the trading symbol is plain `IEX` not `IEX-EQ`. Correct symbol is now used in order params for both NSE and BSE.
- **`order_proxy.py`** — `amo` flag now correctly sets `variety: "AMO"` instead of always `"NORMAL"`.
- **`scripts/daily_live_mark.py`** — Price availability check now fills forward (uses last known price) instead of skipping the whole day when one symbol has no data. If ALL symbols are missing → market holiday (silent skip). If only some symbols missing → warns and skips day. Prevents ADANIPOWER's missing data from silently blocking all subsequent marks.

#### Added
- **`.git/hooks/pre-commit`** — Guard that prevents `equity.csv` files from going backwards in a commit. Detects when the staged version's last date is older than HEAD, blocking the commit with a clear error message.

#### Investigated (no fix available)
- IEX (SELL 13) and BAJAJHLDNG (BUY 1) remain blocked by AB4036 on NSE, BSE, AMO, and browser automation (device fingerprint block CA-101). Exchange-level cautionary listing — no programmatic workaround.

### Fix double-Bearer JWT header + Oct 12 rebalance corrections complete (2026-10-13)

#### Fixed
- **`order_proxy.py`** — `_place_order_raw()` was prepending `"Bearer "` to the JWT token, but `session["data"]["jwtToken"]` already includes the `"Bearer "` prefix. This caused `"Bearer Bearer eyJ..."` → AngelOne returned `"Invalid Token"` for all direct HTTP orders. Fixed by using `auth_token` directly in the `Authorization` header (not wrapped in `f"Bearer {auth_token}"`).
- Same double-prefix bug fixed in `/api/angel/check-tradeable` stub order headers.

#### Changed
- **`scripts/retry_failed_orders.py`** — PENDING_ORDERS cleared: IOB SELL 142 and AUBANK BUY 4 are confirmed placed. IEX SELL 13 and BAJAJHLDNG BUY 1 are documented as exchange-blocked (NSE cautionary listing AB4036) — no API workaround exists.

#### Investigated
- IEX (SELL 13) and BAJAJHLDNG (BUY 1) both return AB4036: "The order cannot be processed as the token is categorised under cautionary listings by the exchange." NSE has placed both stocks on its cautionary/surveillance listing. Neither can be traded via AngelOne API.

### AngelOne idempotency fix + CSV column fix (2026-10-13)

#### Fixed
- **`order_proxy.py`** — AngelOne proxy now fetches the order book upfront before placing any orders. If an order for the same symbol/side/quantity already exists (non-rejected/cancelled), it is skipped and the existing order_id is returned. This prevents double-buying when the API returns "no response" but the order was actually placed.
- **`order_proxy.py`** — After a "no response", proxy now re-checks the order book before marking as failed. If the order landed silently, it is returned as `placed` instead of triggering a retry.
- **`src/trading/execution/angel.py`** — `log_orders()` now enforces a fixed 9-column schema via `reindex()`. Previously, orders placed via the proxy (missing `estimated_value`) wrote 8-column rows, shifting all subsequent columns and breaking CSV parsing.
- **`scripts/check_order_fills.py`** — `pd.to_datetime(..., errors="coerce")` prevents crash on malformed timestamp values in existing CSV rows.

#### Changed
- **`scripts/retry_failed_orders.py`** — updated pending orders to reflect Oct 12 rebalance corrections: SELL IOB 142 (double-buy unwind), SELL IEX 13 (failed sell), BUY AUBANK 4, BUY BAJAJHLDNG 1. Added `--dry-run` flag, order confirmation prompt, and CSV logging.

### Proxy default + secrets cleanup (2026-10-12)

#### Changed
- **`scripts/bedrock_live_rebalance.py`** — proxy is now always the default. Removed `--remote` flag; added `--local` escape hatch for the rare case of a whitelisted IP. Running without flags now correctly routes via DO proxy.
- **`scripts/retry_failed_orders.py`** — credentials now loaded from `.env` via `Secrets.from_env()` instead of hardcoded strings.

### Order fill cron + AngelOne GH secrets (2026-10-12)

#### Added
- **`scripts/check_order_fills.py`** — runs at 9:45 AM IST after any rebalance. Checks placed orders against actual broker holdings. Sends Telegram alert if any orders are unfilled. Supports both Bedrock (AngelOne live login) and Ascent (kite_snapshot.json). Exits with code 1 on failures so GH Actions marks the run as warning.
- **`.github/workflows/daily-mark.yml`** — added 4:15 UTC cron trigger (9:45 AM IST). Fill check runs on morning trigger; mark-to-market runs on evening trigger. Skips non-applicable steps via `if: github.event.schedule`.
- **GitHub secrets** — added `ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET` to `zeevandeep/trading-dashboard` for use in fill check and future automated rebalance.

### Bedrock Q4 rebalance partial execution (2026-10-12)

#### Infrastructure
- Fixed broken `SmartApi` local install — conflicting `SmartAPI 1.1.0` package shadowed `smartapi-python 1.5.5` on case-insensitive macOS filesystem. Removed conflict, force-reinstalled, added missing `logzero` dep.
- Fixed `SmartApi/__init__.py` import casing (`SmartAPI` → `SmartApi`).

#### Execution
- **Q4 rebalance executed via DO proxy** — 11/13 orders placed at Rs. 65,000 capital (Rs. 47K cash available after Oct 6 buy orders expired unfilled).
- **Placed:** MCX SELL, AUBANK BUY, CANBK BUY, CANFINHOME BUY, CHOLAFIN BUY, ESCORTS BUY, HDFCAMC BUY, IOB BUY, LICI BUY, NATIONALUM BUY, RECLTD BUY
- **Pending (2 orders — retry post-close):**
  - SELL 13 x IEX — "no response" near market close
  - BUY 1 x BAJAJHLDNG — "no response" near market close

### Bedrock Q3 rebalance executed + proxy overhaul (2026-10-06)

#### Fixed
- **`order_proxy.py` (AngelOne endpoint)** — rebuilt with rate-limit-safe token lookup (1s sleep per symbol, pre-fetched in batch), proper error logging, NORMAL variety (AngelOne API does not accept "AMO" variety — NORMAL orders placed after hours are queued as AMO automatically). Added `/api/angel/cancel-order` endpoint.
- **`src/trading/execution/angel.py`** — added `amo: bool = False` param to `place_orders_remote()`, passed in payload.
- **`scripts/bedrock_live_rebalance.py`** — added `--amo` flag (pass-through to proxy), correct mode label.
- **DO droplet (167.71.227.66)** — installed missing `logzero` and `websocket-client` deps for SmartApi. Switched proxy from nohup to systemd (`order-proxy.service`) for clean restarts.

#### Infrastructure
- **Bedrock Q3 rebalance executed** — 19/22 orders placed via DO proxy as AMO. 19 placed, 3 failed (IEX SELL 14, MCX SELL 1, BAJAJHLDNG BUY 1 — all blocked by AngelOne AB4036 "cautionary listing" / ASM surveillance restrictions). Net ~Rs 3,791 released.
- **3 cautionary stocks to handle manually via AngelOne app:**
  - SELL 14 IEX (reduce from 54 → 40 shares)
  - SELL 1 MCX (reduce from 2 → 1 share)
  - BUY 1 BAJAJHLDNG @ ~Rs 10,666 (new position)
- **New Bedrock target (active after fills):** AUBANK, BAJAJHLDNG, CANBK, CANFINHOME, CHOLAFIN, ESCORTS, GESHIP(2), HDFCAMC, IEX(40), IOB, LICI, MCX(1), MUTHOOTFIN(1), NATIONALUM, RECLTD

### Bedrock fundamentals infrastructure + dry-run (2026-10-05)

#### Added
- **`scripts/refresh_fundamentals_cache.py`** — scrapes Screener.in for all 168 universe tickers and saves to `data/cache/fundamentals/historical_fundamentals.parquet`. Run quarterly before rebalance. Supports auth cookies (SCREENER_CSRFTOKEN + SCREENER_SESSIONID env vars) for faster scraping. `--status` flag to inspect cache. Roadmap: swap to Screener.in Pro API when scaling.
- **`score_value_quality_from_cache()`** in `src/trading/signals/value_quality.py` — live V+Q scoring path that reads from the parquet cache + current yfinance prices instead of hitting yfinance `.info` live (which was unreliable for Indian stocks, returning only 9/168 stocks with valid fundamentals).

#### Fixed
- **`scripts/bedrock_live_rebalance.py`** — replaced `fetch_fundamentals()` (yfinance .info, broken) with `score_value_quality_from_cache()`. AngelOne `-EQ` suffix stripped from holdings before LTP lookup and order delta computation.
- **`src/trading/execution/angel.py`** — rebuilt `place_orders()` with verify-then-retry logic: on "no response", checks order book before retrying to prevent duplicate orders. Added `_get_order_book()` and `_find_in_order_book()` helpers. SmartApi import made lazy (CI-safe). SmartApi installed in `.venv`.

#### Infrastructure
- Bedrock Q4 dry-run successful: 151 tickers scored, 137 valid, top-15 identified (MUTHOOTFIN, LICI, AUBANK, CANFINHOME, IOB, ESCORTS, CANBK, BAJAJHLDNG, NATIONALUM, IEX, RECLTD, MCX, HDFCAMC, CHOLAFIN, GESHIP). 22/22 prices fetched. Awaiting execution.

### Capital events + equity fix + October rebalance (2026-10-01)

#### Added
- **`data/live/smallcap_momentum_v2_live/capital_events.csv`** — source of truth for external cash flows into each strategy. Three historical events recorded: Jun 4 initial (Rs 9,921), Jul 8 1L build-up (Rs 86,834), Aug 26 1L add-on (Rs 72,456). Total deployed: Rs 1,69,212.
- **`scripts/record_capital_event.py`** — script to record capital additions/withdrawals and recompute equity.csv from that date. Usage: `python scripts/record_capital_event.py --strategy <name> --date YYYY-MM-DD --amount <INR> --note "..." --recompute`. Supports `--list` to view all events.

#### Fixed
- **`scripts/daily_live_mark.py`** — `invested` column now sourced from `capital_events.csv` instead of cost_basis sum. Added `load_capital_events()`, `get_cumulative_invested()`, `get_capital_flow()` helpers. NAV cash flow detection now uses explicit capital events (not cost_basis delta) — fixes silent NAV distortion on rebalance days.
- **`compute_holdings()` epoch_start** — snapshot now used for all dates >= `epoch_start` (not just >= snapshot date). Fixes historical backfill using wrong orders-derived holdings after a messy rebalance. `kite_snapshot.json` updated with `epoch_start: 2026-08-26`.
- **equity.csv Aug 26 – Sep 29** — all 25 rows recomputed: `invested` now correctly shows Rs 1,69,212 (was stuck at Rs 96,756), `market_value` reflects full doubled portfolio (~Rs 1.75L), NAV chains correctly through the Aug 26 capital injection.

#### Infrastructure
- **October rebalance executed** — 14 AMO orders placed via DO proxy (167.71.227.66) at 00:39 IST. 14/14 placed, 0 failed. Exits: ADANIPOWER (64), CUB (58). New entries: IPCALAB (5), MOTHERSON (70), OFSS (1). Capital used: Rs 1,68,656.

### Kite snapshot + live mark fix (2026-09-18)
- **`scripts/kite_portfolio_sync.py`** (new) — one-time script to log into Kite, fetch actual holdings, and save `kite_snapshot.json`. Also triggers an immediate equity.csv backfill. Run this after any messy rebalance.
- **`scripts/daily_live_mark.py`** — updated `compute_holdings()` to accept `as_of_date` and `kite_snapshot` params. When a snapshot exists, uses it as ground truth and only applies orders placed after the snapshot date on top. Fixes the Aug 26 duplicate-order problem. `mark_live_strategy()` now computes holdings per-date (so backfill across rebalances works correctly).

### Bedrock live on AngelOne (pending first execution)
- Script ready: `scripts/bedrock_live_rebalance.py`
- Config: `configs/value_quality_v1_live.yaml` (top 15, Rs 1L, quarterly)
- Dry-run tested — 15 V+Q picks confirmed
- Awaiting execution during market hours

---

## [2026-07-08] — Ascent scale-up, NAV tracking, dashboard overhaul

### Added
- **Order proxy on Render** (`order_proxy.py`) — FastAPI service that forwards Kite API calls from a fixed IP. Avoids needing to whitelist travel IPs. Secured with `PROXY_API_KEY` bearer token. Deployed as `jdquant-proxy` on Render free tier. (`ebcce7a`, `49be93a`)
- **`--remote` flag** on `monthly_live_rebalance.py` — routes order placement through the Render proxy instead of calling Kite directly. (`ebcce7a`)
- **NAV-based strategy return** — time-weighted return unaffected by capital additions/withdrawals, like a mutual fund NAV. Added `nav` column to `equity.csv`, computed automatically by `daily_live_mark.py`. Dashboard shows "Strategy Return %" (NAV) alongside "P&L Rs" (absolute). (`0712555`)
- **Bedrock live rebalance script** (`scripts/bedrock_live_rebalance.py`) — quarterly V+Q rebalance on AngelOne with TOTP auto-login. Config at `configs/value_quality_v1_live.yaml`. (`70283ba`)
- **Outbound IP diagnostic** — `/api/outbound-ip` endpoint on the proxy for discovering Render's egress IP. (`49be93a`)

### Changed
- **Ascent scaled to Rs 1L / top-15** — config updated from top-5 Rs 10K to top-15 Rs 1L. July rebalance executed: 2 sells (RBLBANK, VEDL), 15 buys across momentum picks. All 17 orders filled on Kite. (`e88f923`)
- **NSE tick size logic fixed** — stocks >= Rs 5000 use 0.50 tick (was 0.10). NAVINFLUOR order had failed due to this. Fixed in `kite.py`, `angel.py`, and `order_proxy.py`. (`e2140a3`)
- **Ascent page** — replaced "Paper Trading / Simulation" section with "Live P&L" showing actual broker returns. (`24d5d6c`)
- **Rebalance page** — removed paper state comparison (Ascent is fully live now). Shows current 15 holdings directly. Removed Execute command section per user preference. Moved Live P&L to show NAV-based strategy return. (`a35822f`, `d402212`)
- **NAV reset to 1.0** on July 8 — 15-stock strategy starts with clean baseline. Old 5-stock NAV was meaningless for the new portfolio. (`20cdc67`)

### Fixed
- **Missing NAVINFLUOR order in orders.csv** — manually placed order (after tick size failure) wasn't logged. Dashboard showed 14/15 positions. (`e5687ea`)
- **Rebalance page top-5 hardcode** — was comparing live holdings against top-5 of paper state even though strategy is now top-15. Showed 10 false sell signals. (`2f94eba`)

### Infrastructure
- **Render Blueprint** (`render.yaml`) updated with second service `jdquant-proxy`
- **`requirements-dashboard.txt`** — added `fastapi`, `uvicorn`, `kiteconnect`, `httpx`
- Render proxy shared IP (`74.220.48.20`) already claimed by another Kite user — proxy built but not usable for Kite until dedicated IP is set up

### Known Issues
- Render free tier shared IPs can't be whitelisted on Kite (already claimed). Need dedicated static IP ($7/mo Render paid or Oracle Cloud free tier) for the proxy to work.
- System Python missing `SmartApi` module — must use `.venv/bin/python` for AngelOne scripts.
- NumPy 1.x/2.x compatibility warnings on every script run (cosmetic, doesn't affect execution).
