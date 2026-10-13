"""Pre-rebalance GSM (Graded Surveillance Measure) check for AngelOne.

Detects stocks under NSE's Trade-for-Trade / GSM surveillance BEFORE
placing rebalance orders, so you're not surprised mid-execution.

Detection method: If a stock has an NSE '-BE' series in AngelOne's
searchScrip results, it's in the Trade-for-Trade segment — a reliable
proxy for GSM listing. AngelOne blocks API orders on these with AB4036.

Usage:
    # Check the current Bedrock target portfolio
    python scripts/check_gsm_flags.py

    # Check arbitrary symbols
    python scripts/check_gsm_flags.py --symbols IEX NMDC VEDL

    # Run automatically before rebalance (called by bedrock_live_rebalance.py)
    python scripts/check_gsm_flags.py --config configs/value_quality_v1_live.yaml
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.utils.logging import setup_logging

log = setup_logging("gsm_check")


def check_gsm_via_angel(symbols: list[str], obj=None) -> dict[str, str]:
    """
    Check GSM status via AngelOne searchScrip.

    Returns {symbol: "gsm" | "ok" | "error"}.
    A stock with '-BE' series on NSE is in Trade-for-Trade segment (GSM proxy).

    Pass an existing AngelOne session as `obj` to avoid an extra login.
    """
    if obj is None:
        from trading.execution.angel import login
        obj = login()
    results: dict[str, str] = {}

    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(1.2)  # AngelOne searchScrip rate limit
        try:
            search = obj.searchScrip("NSE", sym)
            data = search.get("data") or []
            series = [d.get("tradingsymbol", "") for d in data]
            # '-BE' = Trade-for-Trade segment = GSM indicator
            if f"{sym}-BE" in series or f"{sym}-BL" in series:
                results[sym] = "gsm"
                log.warning(f"  {sym}: GSM/T+T (series: {[s for s in series if s.startswith(sym)]})")
            elif any(d.get("tradingsymbol") == f"{sym}-EQ" for d in data):
                results[sym] = "ok"
                log.info(f"  {sym}: OK")
            else:
                results[sym] = "unknown"
                log.warning(f"  {sym}: no EQ series found — {series}")
        except Exception as e:
            results[sym] = "error"
            log.error(f"  {sym}: error — {e}")

    return results


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", help="Symbols to check")
    parser.add_argument("--config", help="Strategy config YAML to load target universe from")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    elif args.config:
        import yaml
        cfg = yaml.safe_load(Path(args.config).read_text())
        symbols = cfg.get("universe", [])
        log.info(f"Loaded {len(symbols)} symbols from {args.config}")
    else:
        # Default: check all current Bedrock holdings
        from trading.execution.angel import login, get_holdings
        obj = login()
        holdings = get_holdings(obj)
        symbols = [s.replace("-EQ", "") for s in holdings.keys()]
        log.info(f"Checking {len(symbols)} current holdings")

    log.info(f"Checking GSM status for {len(symbols)} symbols...")
    _obj = obj if "obj" in locals() else None
    results = check_gsm_via_angel(symbols, obj=_obj)

    gsm = [s for s, v in results.items() if v == "gsm"]
    ok = [s for s, v in results.items() if v == "ok"]
    errors = [s for s, v in results.items() if v in ("error", "unknown")]

    print(f"\n{'='*50}")
    print(f"GSM Pre-Check Results ({len(symbols)} symbols)")
    print(f"{'='*50}")
    if gsm:
        print(f"\n⚠  GSM/CAUTIONARY ({len(gsm)}) — AngelOne will BLOCK orders:")
        for s in gsm:
            print(f"   {s}")
    else:
        print(f"\n✓  No GSM flags found")

    print(f"\n✓  Tradeable: {len(ok)} symbols")

    if errors:
        print(f"\n?  Could not verify ({len(errors)}): {errors}")

    print(f"{'='*50}\n")

    if gsm:
        sys.exit(1)  # Non-zero so callers can detect GSM flags


if __name__ == "__main__":
    main()
