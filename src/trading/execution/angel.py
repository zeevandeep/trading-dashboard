"""AngelOne SmartAPI broker adapter — order execution on NSE.

Login is fully automated via TOTP — no browser needed.
Can be run from cron without manual intervention.

Usage:
    from trading.execution.angel import login, get_holdings, place_orders
    obj = login()
    holdings = get_holdings(obj)
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyotp


def _smart_connect():
    from SmartApi.smartConnect import SmartConnect
    return SmartConnect

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

    SmartConnect = _smart_connect()
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


def _get_symbol_token(obj: SmartConnect, symbol: str, exchange: str = "NSE") -> tuple[str, str] | tuple[None, None]:
    """Look up the AngelOne symbol token and trading symbol for an equity.

    Returns (tradingsymbol, symboltoken) — prefers -EQ variant for delivery orders.
    Both must be sent together in the order request.
    """
    try:
        result = obj.searchScrip(exchange, symbol)
        if result and result.get("data"):
            # Prefer exact -EQ match (required for delivery orders)
            for item in result["data"]:
                if item.get("tradingsymbol") == f"{symbol}-EQ":
                    return item["tradingsymbol"], item["symboltoken"]
            # Fallback: exact match without suffix
            for item in result["data"]:
                if item.get("tradingsymbol") == symbol:
                    return item["tradingsymbol"], item["symboltoken"]
            # Last resort: first result
            first = result["data"][0]
            return first.get("tradingsymbol"), first.get("symboltoken")
    except Exception as e:
        log.warning(f"Token lookup failed for {symbol}: {e}")
    return None, None


def _get_order_book(obj) -> list[dict]:
    """Fetch today's order book from AngelOne."""
    try:
        resp = obj.orderBook()
        return resp.get("data") or []
    except Exception as e:
        log.warning(f"Could not fetch order book: {e}")
        return []


def _find_in_order_book(order_book: list[dict], trading_symbol: str, side: str, quantity: int) -> dict | None:
    """Check if an order for this symbol/side/qty already exists in today's order book.

    Used to verify placement after a 'no response' — avoids duplicate orders.
    Returns the order book entry if found, None otherwise.
    """
    side_map = {"BUY": "BUY", "SELL": "SELL"}
    for entry in order_book:
        if (
            entry.get("tradingsymbol", "").startswith(trading_symbol.replace("-EQ", ""))
            and entry.get("transactiontype") == side_map.get(side)
            and int(entry.get("quantity", 0)) == quantity
            and entry.get("status") not in ("CANCELLED", "REJECTED")
        ):
            return entry
    return None


def place_orders(
    obj,
    orders: list[dict],
    prices: dict[str, float] | None = None,
    exchange: str = "NSE",
    dry_run: bool = False,
    limit_buffer_pct: float = 0.5,
) -> list[dict]:
    """Place CNC LIMIT orders on AngelOne with verify-then-retry logic.

    Safe against the common AngelOne 'no response' issue:
      1. Place order
      2. If no response, check order book before retrying
      3. If already in order book, mark as placed (no duplicate)
      4. If not in order book, retry once
      5. If retry also fails, mark as failed

    Same interface as kite.place_orders for consistency.
    """
    results = []

    if prices is None:
        symbols = [o["symbol"] for o in orders]
        prices = get_ltp(obj, symbols)

    for i, order in enumerate(orders):
        if i > 0:
            time.sleep(1)  # avoid AngelOne rate limiting

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
        trading_symbol, token = _get_symbol_token(obj, symbol, exchange)
        if not token:
            log.error(f"Could not find symbol token for {symbol}")
            results.append({**order, "order_id": None, "status": "failed: no symbol token", "limit_price": limit_price})
            continue

        params = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": token,
            "transactiontype": order["side"],
            "exchange": exchange,
            "ordertype": "LIMIT",
            "producttype": "DELIVERY",
            "duration": "DAY",
            "price": str(limit_price),
            "quantity": str(order["quantity"]),
        }

        order_id = None
        status = None

        for attempt in range(2):  # try once, verify, retry once if needed
            try:
                resp = obj.placeOrder(params)
                if resp:
                    order_id = resp
                    status = "placed"
                    log.info(f"  Placed (attempt {attempt+1}): order_id={order_id}")
                    break
                else:
                    log.warning(f"  No response on attempt {attempt+1} — checking order book...")
            except Exception as e:
                log.warning(f"  Exception on attempt {attempt+1}: {e} — checking order book...")

            # No response or exception — check if order actually landed in order book
            time.sleep(2)
            book = _get_order_book(obj)
            existing = _find_in_order_book(book, trading_symbol, order["side"], order["quantity"])
            if existing:
                order_id = existing.get("orderid", "unknown")
                status = "placed"
                log.info(f"  Verified in order book (order_id={order_id}) — NOT retrying")
                break
            else:
                if attempt == 0:
                    log.warning(f"  Not found in order book — retrying...")
                    time.sleep(2)
                else:
                    status = "failed: no response after retry"
                    log.error(f"  Still no response after retry and order book check")

        results.append({**order, "order_id": order_id, "status": status, "limit_price": limit_price})

    return results


def place_orders_remote(
    orders: list[dict],
    prices: dict[str, float],
    exchange: str = "NSE",
    limit_buffer_pct: float = 0.5,
    amo: bool = False,
) -> list[dict]:
    """Place orders via the Render proxy (fixed IP, no local IP whitelisting needed)."""
    import httpx

    secrets = Secrets.from_env()
    proxy_url = secrets.proxy_url.rstrip("/")
    proxy_key = secrets.proxy_api_key

    if not proxy_url or not proxy_key:
        raise ValueError("PROXY_URL and PROXY_API_KEY must be set in .env")

    payload = {
        "angel_api_key": secrets.angel_api_key,
        "angel_client_id": secrets.angel_client_id,
        "angel_password": secrets.angel_password,
        "angel_totp_secret": secrets.angel_totp_secret,
        "orders": [
            {"symbol": o["symbol"], "side": o["side"], "quantity": o["quantity"],
             "estimated_value": o.get("estimated_value", 0)}
            for o in orders
        ],
        "prices": prices,
        "exchange": exchange,
        "limit_buffer_pct": limit_buffer_pct,
        "amo": amo,
    }

    log.info(f"Sending {len(orders)} orders to proxy at {proxy_url}")
    resp = httpx.post(
        f"{proxy_url}/api/angel/place-orders",
        json=payload,
        headers={"Authorization": f"Bearer {proxy_key}"},
        timeout=120,
    )
    resp.raise_for_status()

    results = []
    for r in resp.json():
        results.append({
            "symbol": r["symbol"],
            "side": r["side"],
            "quantity": r["quantity"],
            "order_id": r.get("order_id"),
            "status": r["status"],
            "limit_price": r.get("limit_price", 0),
        })
        log.info(f"  {r['side']} {r['quantity']} x {r['symbol']} → {r['status']}")

    return results


_LOG_COLS = ["symbol", "side", "quantity", "estimated_value", "order_id", "status", "limit_price", "timestamp", "broker"]


def log_orders(results: list[dict], log_path: Path) -> None:
    """Append order results to a CSV log."""
    if not results:
        return
    df = pd.DataFrame(results)
    df["timestamp"] = datetime.now().isoformat()
    df["broker"] = "angelone"
    df = df.reindex(columns=_LOG_COLS)  # enforce consistent column order/count
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        df.to_csv(log_path, mode="a", header=False, index=False)
    else:
        df.to_csv(log_path, index=False)
