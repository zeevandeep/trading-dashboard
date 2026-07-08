# Changelog

All notable changes to JD Quant are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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
