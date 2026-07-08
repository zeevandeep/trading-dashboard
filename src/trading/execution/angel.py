"""AngelOne SmartAPI broker adapter — order execution on NSE.

Login is fully automated via TOTP — no browser needed.
Can be run from cron without manual intervention.

Usage:
    from trading.execution.angel import login, get_holdings, place_orders
    obj = login()
    holdings = get_holdings(obj)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pyotp
from SmartApi import SmartConnect

from trading.config import DATA_DIR, Secrets
from trading.execution.kite import _get_ltp_yfinance
from trading.utils.logging import setup_logging

log = setup_logging("angel")


def login(
    api_key: str | None = None,
    client_id: str | None = None,
    password: str | None = None,
    totp_secret: str | None = None,
) -> SmartConnect:
    """Authenticate with AngelOne SmartAPI. Fully automated via TOTP."""
    if not api_key:
        secrets = Secrets.from_env()
        api_key = secrets.angel_api_key
        client_id = secrets.angel_client_id
        password = secrets.angel_password
        totp_secret = secrets.angel_totp_secret

    if not all([api_key, client_id, password, totp_secret]):
        raise ValueError(
            "AngelOne credentials required. Set ANGEL_API_KEY, ANGEL_CLIENT_ID, "
            "ANGEL_PASSWORD, ANGEL_TOTP_SECRET in .env"
        )

    obj = SmartConnect(api_key=api_key)
    totp = pyotp.TOTP(totp_secret).now()
    data = obj.generateSession(client_id, password, totp)

    if not data.get("status"):
        raise RuntimeError(f"AngelOne login failed: {data.get('message', data)}")

    profile = obj.getProfile(data["data"]["refreshToken"])
    name = profile.get("data", {}).get("name", client_id)
    log.info(f"Logged in to AngelOne as {name} ({client_id})")

    return obj


def get_holdings(obj: SmartConnect) -> dict[str, dict]:
    """Get current holdings as {symbol: {quantity, average_price, ...}}."""
    raw = obj.holding()
    data = raw.get("data") or []
    holdings = {}
    for h in data:
        qty = h.get("quantity", 0) or 0
        if qty > 0:
            holdings[h["tradingsymbol"]] = {
                "quantity": qty,
                "average_price": float(h.get("averageprice", 0) or 0),
                "last_price": float(h.get("ltp", 0) or 0),
                "pnl": float(h.get("profitandloss", 0) or 0),
                "symboltoken": h.get("symboltoken", ""),
                "exchange": h.get("exchange", "NSE"),
            }
    return holdings


def get_ltp(obj: SmartConnect | None, symbols: list[str]) -> dict[str, float]:
    """Get last traded prices via yfinance (same as Kite adapter)."""
    if not symbols:
        return {}
    prices = _get_ltp_yfinance(symbols)
    if prices:
        log.info(f"LTP from yfinance for {len(prices)}/{len(symbols)} symbols")
    return prices


def _get_symbol_token(obj: SmartConnect, symbol: str, exchange: str = "NSE") -> str | None:
    """Look up the AngelOne symbol token for a trading symbol."""
    try:
        params = {
            "exchange": exchange,
            "searchscrip": symbol,
        }
        result = obj.searchScrip(exchange, symbol)
        if result and result.get("data"):
            for item in result["data"]:
                if item.get("tradingsymbol") == symbol:
                    return item["symboltoken"]
            # If exact match not found, use first result
            return result["data"][0].get("symboltoken")
    except Exception as e:
        log.warning(f"Token lookup failed for {symbol}: {e}")
    return None


def place_orders(
    obj: SmartConnect,
    orders: list[dict],
    prices: dict[str, float] | None = None,
    exchange: str = "NSE",
    dry_run: bool = False,
    limit_buffer_pct: float = 0.5,
) -> list[dict]:
    """Place CNC LIMIT orders on AngelOne.

    Same interface as kite.place_orders for consistency.
    """
    results = []

    if prices is None:
        symbols = [o["symbol"] for o in orders]
        prices = get_ltp(obj, symbols)

    for order in orders:
        symbol = order["symbol"]
        ltp = prices.get(symbol, 0)

        # NSE tick size
        tick = 0.50 if ltp >= 5000 else (0.10 if ltp >= 1000 else 0.05)
        if order["side"] == "BUY":
            limit_price = round(round(ltp * (1 + limit_buffer_pct / 100) / tick) * tick, 2)
        else:
            limit_price = round(round(ltp * (1 - limit_buffer_pct / 100) / tick) * tick, 2)

        log.info(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"{order['side']} {order['quantity']} x {symbol} "
            f"@ limit {limit_price:.2f} (LTP {ltp:.2f})"
        )

        if dry_run:
            results.append({**order, "order_id": None, "status": "dry_run", "limit_price": limit_price})
            continue

        # Look up symbol token
        token = _get_symbol_token(obj, symbol, exchange)
        if not token:
            log.error(f"Could not find symbol token for {symbol}")
            results.append({**order, "order_id": None, "status": f"failed: no symbol token", "limit_price": limit_price})
            continue

        try:
            params = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": order["side"],
                "exchange": exchange,
                "ordertype": "LIMIT",
                "producttype": "DELIVERY",
                "duration": "DAY",
                "price": str(limit_price),
                "quantity": str(order["quantity"]),
            }
            resp = obj.placeOrder(params)
            if resp:
                log.info(f"  Order placed: {resp}")
                results.append({**order, "order_id": resp, "status": "placed", "limit_price": limit_price})
            else:
                log.error(f"  Order returned None")
                results.append({**order, "order_id": None, "status": "failed: no response", "limit_price": limit_price})
        except Exception as e:
            log.error(f"  Order FAILED: {e}")
            results.append({**order, "order_id": None, "status": f"failed: {e}", "limit_price": limit_price})

    return results


def log_orders(results: list[dict], log_path: Path) -> None:
    """Append order results to a CSV log."""
    if not results:
        return
    df = pd.DataFrame(results)
    df["timestamp"] = datetime.now().isoformat()
    df["broker"] = "angelone"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        df.to_csv(log_path, mode="a", header=False, index=False)
    else:
        df.to_csv(log_path, index=False)
