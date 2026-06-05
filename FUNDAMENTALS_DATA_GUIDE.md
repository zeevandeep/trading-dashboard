# Fundamentals Data Guide

Context for building a loader that reads the historical fundamentals in this repo
and feeds the Value+Quality (V+Q) pipeline. Read this before writing the loader.

## Data inventory (all paths relative to repo root)

| Source | Path | Coverage | Statement type | Units |
|--------|------|----------|----------------|-------|
| Moneycontrol | `data/mc_exports/{TICKER}.json` (168 files) | ~2004–2026, avg ~19.7 yrs | **Standalone** | **Crores (₹ Cr)** |
| Screener (cache) | `data/cache/fundamentals/historical_fundamentals.parquet` | ~2014–2026 | **Consolidated** | **Rupees** |
| Screener (raw backup) | `outputs/fundamentals_raw.json` | same as parquet | Consolidated | Crores (per-ticker raw) |

`src/trading/signals/value_quality.py` already contains the live scrapers and
`compute_historical_scores`. Its `_extract_from_moneycontrol` was patched on
2026-06-05 to read the financials code from `link_src`'s trailing segment (not
`sc_id`), which had been silently dropping ~5% of tickers.

## Moneycontrol JSON format

```json
{"ticker":"ABB","data":{"Dec 04":{"net_profit":154.32,"equity_capital":42.38,"reserves":682.28,"borrowings_lt":1.49,"borrowings_st":0}, ...}}
```

Critical facts — do not assume:
- **Values are in Crores.** The parquet is in **Rupees**. Multiply MC values by `1e7` to match.
- **Year keys are `"Mon YY"` with a 2-digit year** (`"Mar 04"` = March 2004). Parse `year = 2000 + int(YY)`, month from the 3-letter name, date = last calendar day of that month.
- **Month varies and can change mid-series.** Most are `Mar`; some are `Dec`/`Jun`; a few companies switched fiscal year-end partway (e.g. Ambuja: `Dec` through 2022, then `Mar`). Treat each key as its own fiscal-year-end; never hardcode March.
- These are **standalone** statements; `revenue` is not present.
- `null` = missing → keep as NaN (treat null borrowings as 0 when summing debt).

## Target schema (match `fetch_historical_fundamentals`)

Return `dict[str, pd.DataFrame]`, each DataFrame indexed by fiscal-year-end date,
columns `net_income, equity, total_debt, shares, revenue`, all in **Rupees**:

- `net_income   = net_profit * 1e7`
- `equity       = (equity_capital + reserves) * 1e7`
- `total_debt   = (borrowings_lt + borrowings_st) * 1e7`   (null → 0)
- `shares       = equity_capital * 1e7 / face_value`,  default `face_value = 10`
- `revenue      = NaN`

## What to build

1. `load_mc_fundamentals(cache_dir="data/mc_exports") -> dict[str, pd.DataFrame]`
   — reads the JSON **offline** (no network), returns the schema above. Drop-in
   for `compute_historical_scores`.
2. A merge function: Moneycontrol for deep history, Screener parquet (consolidated)
   for recent years — Screener takes precedence where both exist; MC fills
   everything before Screener's earliest date per ticker. Mirror the existing
   `_extract_fundamentals` merge logic.

## Caveat to handle explicitly (not silently smooth over)

The merge splices **standalone (old) under consolidated (recent)**, creating a
discontinuity around 2014–2017 (consolidated PAT/equity is usually larger than
standalone). For ranking signals (ROE, earnings growth) this is often acceptable,
but flag it — and consider offering a MC-standalone-throughout mode for a
consistent single-basis series.
