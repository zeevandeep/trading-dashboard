#!/usr/bin/env python3
"""Refresh Value + Quality scores and save to disk.

Run on a schedule (e.g. daily) so the dashboard loads instantly
instead of making ~450 yfinance API calls on page load.

Usage:
    python -m scripts.refresh_vq_scores
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR
from trading.data.universe import smallcap_universe
from trading.signals.value_quality import fetch_fundamentals, score_value_quality
from trading.utils.logging import setup_logging

log = setup_logging("refresh_vq_scores")

OUTPUT_PATH = DATA_DIR / "vq_scores_latest.json"


def main():
    log.info("Starting V+Q score refresh...")
    tickers = smallcap_universe()
    log.info(f"Universe: {len(tickers)} tickers")

    fund = fetch_fundamentals(tickers, max_workers=15)
    if fund.empty:
        log.error("No fundamentals fetched — aborting")
        sys.exit(1)

    scores = score_value_quality(fund)
    if scores.empty:
        log.error("Scoring returned empty — aborting")
        sys.exit(1)

    # Build output: top 15 picks with fundamentals + full scores
    top_15 = scores.head(15)
    picks = []
    for ticker, score in top_15.items():
        row = fund.loc[ticker]
        picks.append({
            "ticker": ticker,
            "score": round(float(score), 4),
            "pe": round(float(row.get("pe", 0)), 2),
            "roe": round(float(row.get("roe", 0)), 4),
            "de": round(float(row.get("de", 0)), 2),
            "earnings_growth": round(float(row.get("earnings_growth", 0)), 4) if row.get("earnings_growth") is not None else None,
        })

    payload = {
        "updated_at": datetime.now().isoformat(),
        "n_scored": len(scores),
        "n_universe": len(tickers),
        "top_15": picks,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    log.info(f"Saved {len(picks)} picks to {OUTPUT_PATH}")
    log.info(f"Top 5: {[p['ticker'] for p in picks[:5]]}")


if __name__ == "__main__":
    main()
