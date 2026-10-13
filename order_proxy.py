"""Lightweight order proxy — forwards broker API calls from a fixed-IP server.

Deployed on Render alongside the Streamlit dashboard. Supports both:
  - Kite (Ascent) via /api/place-orders
  - AngelOne (Bedrock) via /api/angel/place-orders

The local rebalance script sends orders here, and this proxy forwards them
from Render's whitelisted static IP.

Security:
    - PROXY_API_KEY env var required in Authorization header
    - Credentials are per-request, never stored
    - HTTPS provided by Render
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="JD Quant Order Proxy", docs_url=None, redoc_url=None)

PROXY_API_KEY = os.environ.get("PROXY_API_KEY", "")


def _check_auth(authorization: str | None):
    if not PROXY_API_KEY:
        raise HTTPException(500, "PROXY_API_KEY not configured on server")
    if not authorization or authorization != f"Bearer {PROXY_API_KEY}":
        raise HTTPException(401, "Invalid API key")


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/outbound-ip")
def outbound_ip():
    """Check what IP this server uses for outbound requests."""
    import httpx
    resp = httpx.get("https://api.ipify.org?format=json", timeout=10)
    return resp.json()


# ── Place orders ─────────────────────────────────────────────────────────────

class Order(BaseModel):
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    estimated_value: float = 0.0


class PlaceOrdersRequest(BaseModel):
    kite_api_key: str
    access_token: str
    orders: list[Order]
    prices: dict[str, float]  # {symbol: ltp}
    exchange: str = "NSE"
    limit_buffer_pct: float = 0.5
    amo: bool = False


class OrderResult(BaseModel):
    symbol: str
    side: str
    quantity: int
    order_id: Optional[str] = None
    status: str
    limit_price: float = 0.0


@app.post("/api/place-orders")
def place_orders(
    req: PlaceOrdersRequest,
    authorization: str = Header(None),
) -> list[OrderResult]:
    _check_auth(authorization)

    import time
    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=req.kite_api_key)
    kite.set_access_token(req.access_token)

    variety = KiteConnect.VARIETY_AMO if req.amo else KiteConnect.VARIETY_REGULAR

    results = []
    for i, order in enumerate(req.orders):
        if i > 0:
            time.sleep(0.4)  # stay well under Kite's 3 orders/sec limit

        ltp = req.prices.get(order.symbol, 0)
        tick = 0.50 if ltp >= 5000 else (0.10 if ltp >= 1000 else 0.05)

        if order.side == "BUY":
            raw_price = ltp * (1 + req.limit_buffer_pct / 100)
            limit_price = round(round(raw_price / tick) * tick, 2)
        else:
            raw_price = ltp * (1 - req.limit_buffer_pct / 100)
            limit_price = round(round(raw_price / tick) * tick, 2)

        transaction = (
            KiteConnect.TRANSACTION_TYPE_BUY
            if order.side == "BUY"
            else KiteConnect.TRANSACTION_TYPE_SELL
        )

        try:
            order_id = kite.place_order(
                variety=variety,
                exchange=req.exchange,
                tradingsymbol=order.symbol,
                transaction_type=transaction,
                quantity=order.quantity,
                product=KiteConnect.PRODUCT_CNC,
                order_type=KiteConnect.ORDER_TYPE_LIMIT,
                price=limit_price,
                validity=KiteConnect.VALIDITY_DAY,
            )
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=str(order_id), status="placed", limit_price=limit_price,
            ))
        except Exception as e:
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=None, status=f"failed: {e}", limit_price=limit_price,
            ))

    return results


# ── AngelOne orders ─────────────────────────────────────────────────────────

class AngelPlaceOrdersRequest(BaseModel):
    angel_api_key: str
    angel_client_id: str
    angel_password: str
    angel_totp_secret: str
    orders: list[Order]
    prices: dict[str, float]
    exchange: str = "NSE"
    limit_buffer_pct: float = 0.5
    amo: bool = False  # After-Market Order (use outside 9:15–3:30 IST)


@app.post("/api/angel/place-orders")
def angel_place_orders(
    req: AngelPlaceOrdersRequest,
    authorization: str = Header(None),
) -> list[OrderResult]:
    _check_auth(authorization)

    import pyotp
    from SmartApi import SmartConnect

    # Login
    obj = SmartConnect(api_key=req.angel_api_key)
    totp = pyotp.TOTP(req.angel_totp_secret).now()
    session = obj.generateSession(req.angel_client_id, req.angel_password, totp)
    if not session.get("status"):
        raise HTTPException(500, f"AngelOne login failed: {session.get('message', session)}")

    import time
    import logging
    logger = logging.getLogger("angel_proxy")

    # Build symbol → token cache upfront with rate-limit-safe delays (1s each)
    all_symbols = list({o.symbol for o in req.orders})
    token_cache: dict[str, str] = {}
    for sym in all_symbols:
        try:
            search = obj.searchScrip(req.exchange, sym)
            logger.info(f"searchScrip({sym}): {search}")
            if search and search.get("data"):
                # Prefer exact -EQ match (delivery), then exact, then first result
                token = None
                for item in search["data"]:
                    if item.get("tradingsymbol") == f"{sym}-EQ":
                        token = item["symboltoken"]
                        break
                if not token:
                    for item in search["data"]:
                        if item.get("tradingsymbol") == sym:
                            token = item["symboltoken"]
                            break
                if not token:
                    token = search["data"][0].get("symboltoken")
                if token:
                    token_cache[sym] = token
                    logger.info(f"  → token {token}")
                else:
                    logger.warning(f"  → no token found in results: {[x.get('tradingsymbol') for x in search['data'][:5]]}")
            else:
                logger.warning(f"  → empty/null result")
        except Exception as exc:
            logger.error(f"  → exception: {exc}")
        time.sleep(1.0)  # stay under AngelOne's searchScrip rate limit

    # Fetch today's order book ONCE upfront — used to skip already-placed orders
    # and to verify "no response" cases (AngelOne sometimes executes silently).
    today_orders: list[dict] = []
    try:
        ob = obj.orderBook()
        today_orders = ob.get("data") or []
        logger.info(f"Order book fetched: {len(today_orders)} orders")
    except Exception as exc:
        logger.warning(f"Could not fetch order book upfront: {exc}")

    def _find_in_book(book: list[dict], symbol: str, side: str, qty: int) -> dict | None:
        """Return first non-rejected/cancelled order matching symbol+side+qty."""
        sym_eq = f"{symbol}-EQ"
        for o in book:
            if (
                o.get("tradingsymbol") in (symbol, sym_eq)
                and o.get("transactiontype", "").upper() == side.upper()
                and int(o.get("quantity", 0)) == qty
                and o.get("status", "").lower() not in ("rejected", "cancelled")
            ):
                return o
        return None

    results = []
    for i, order in enumerate(req.orders):
        if i > 0:
            time.sleep(1)  # stay under AngelOne's placeOrder rate limit

        ltp = req.prices.get(order.symbol, 0)
        tick = 0.50 if ltp >= 5000 else (0.10 if ltp >= 1000 else 0.05)

        if order.side == "BUY":
            limit_price = round(round(ltp * (1 + req.limit_buffer_pct / 100) / tick) * tick, 2)
        else:
            limit_price = round(round(ltp * (1 - req.limit_buffer_pct / 100) / tick) * tick, 2)

        token = token_cache.get(order.symbol)
        if not token:
            logger.error(f"No token for {order.symbol} — available tokens: {list(token_cache.keys())}")
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=None, status="failed: no symbol token", limit_price=limit_price,
            ))
            continue

        # ── Idempotency check: skip if already in today's order book ──────────
        existing = _find_in_book(today_orders, order.symbol, order.side, order.quantity)
        if existing:
            existing_id = existing.get("orderid", "unknown")
            logger.info(f"SKIP {order.side} {order.quantity} {order.symbol} — already in order book (id={existing_id}, status={existing.get('status')})")
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=str(existing_id), status="placed (already exists)", limit_price=limit_price,
            ))
            continue

        params = {
            "variety": "NORMAL",  # AngelOne API only supports NORMAL/STOPLOSS/ROBO; NORMAL orders placed after hours are queued as AMO automatically
            "tradingsymbol": f"{order.symbol}-EQ",
            "symboltoken": token,
            "transactiontype": order.side,
            "exchange": req.exchange,
            "ordertype": "LIMIT",
            "producttype": "DELIVERY",
            "duration": "DAY",
            "price": str(limit_price),
            "quantity": str(order.quantity),
        }
        logger.info(f"placeOrder params: {params}")
        try:
            resp = obj.placeOrder(params)
            logger.info(f"placeOrder resp: {resp!r}")
            if resp:
                results.append(OrderResult(
                    symbol=order.symbol, side=order.side, quantity=order.quantity,
                    order_id=str(resp), status="placed", limit_price=limit_price,
                ))
            else:
                # "No response" from API — AngelOne sometimes executes silently.
                # Re-check the order book before declaring failure.
                logger.warning(f"No response for {order.side} {order.quantity} {order.symbol} — re-checking order book...")
                time.sleep(2)
                try:
                    ob2 = obj.orderBook()
                    fresh_book = ob2.get("data") or []
                    verified = _find_in_book(fresh_book, order.symbol, order.side, order.quantity)
                    if verified:
                        verified_id = verified.get("orderid", "unknown")
                        logger.info(f"  → found in order book after retry (id={verified_id}) — marking as placed")
                        results.append(OrderResult(
                            symbol=order.symbol, side=order.side, quantity=order.quantity,
                            order_id=str(verified_id), status="placed", limit_price=limit_price,
                        ))
                    else:
                        logger.error(f"  → not found in order book — genuinely failed")
                        results.append(OrderResult(
                            symbol=order.symbol, side=order.side, quantity=order.quantity,
                            order_id=None, status="failed: no response after retry", limit_price=limit_price,
                        ))
                except Exception as ob_exc:
                    logger.error(f"  → order book re-check failed: {ob_exc}")
                    results.append(OrderResult(
                        symbol=order.symbol, side=order.side, quantity=order.quantity,
                        order_id=None, status="failed: no response after retry", limit_price=limit_price,
                    ))
        except Exception as e:
            logger.error(f"placeOrder exception: {e}")
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=None, status=f"failed: {e}", limit_price=limit_price,
            ))

    return results


class AngelCancelRequest(BaseModel):
    angel_api_key: str
    angel_client_id: str
    angel_password: str
    angel_totp_secret: str
    order_id: str
    variety: str = "NORMAL"


@app.post("/api/angel/cancel-order")
def angel_cancel_order(
    req: AngelCancelRequest,
    authorization: str = Header(None),
):
    _check_auth(authorization)
    import pyotp
    from SmartApi import SmartConnect

    obj = SmartConnect(api_key=req.angel_api_key)
    totp = pyotp.TOTP(req.angel_totp_secret).now()
    session = obj.generateSession(req.angel_client_id, req.angel_password, totp)
    if not session.get("status"):
        raise HTTPException(500, f"AngelOne login failed: {session.get('message', session)}")

    try:
        resp = obj.cancelOrder(req.order_id, req.variety)
        return {"order_id": req.order_id, "status": "cancelled", "response": str(resp)}
    except Exception as e:
        raise HTTPException(500, f"Cancel failed: {e}")
