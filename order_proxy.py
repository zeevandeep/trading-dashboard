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
    import requests as _requests
    from SmartApi import SmartConnect

    # Login
    obj = SmartConnect(api_key=req.angel_api_key)
    totp = pyotp.TOTP(req.angel_totp_secret).now()
    session = obj.generateSession(req.angel_client_id, req.angel_password, totp)
    if not session.get("status"):
        raise HTTPException(500, f"AngelOne login failed: {session.get('message', session)}")

    # jwtToken already includes "Bearer " prefix from AngelOne — use as-is
    _auth_token = session["data"]["jwtToken"]

    def _place_order_raw(params: dict) -> tuple[str | None, str]:
        """
        Place an order via direct HTTP call (not SmartApi wrapper).
        Returns (order_id_or_None, status_string).
        SmartApi's placeOrder returns None for failures — we need the raw response
        to read the actual AngelOne error code (e.g. AB4036 for GSM).
        """
        headers = {
            "Content-type": "application/json",
            "Authorization": _auth_token,
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "Accept": "application/json",
            "X-PrivateKey": req.angel_api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB",
        }
        try:
            r = _requests.post(
                "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder",
                json=params,
                headers=headers,
                timeout=15,
            )
            data = r.json()
            if data.get("status") and data.get("data", {}).get("orderid"):
                return data["data"]["orderid"], "placed"
            else:
                msg = data.get("message", "")
                code = data.get("errorcode", "")
                if code == "AB4036" or "cautionary" in msg.lower():
                    return None, "failed: GSM cautionary listing (AB4036)"
                elif code == "AB8051" or "suspended" in msg.lower():
                    return None, "failed: stock suspended (AB8051)"
                else:
                    return None, f"failed: {msg} ({code})" if code else f"failed: {msg or 'no response'}"
        except Exception as e:
            return None, f"failed: {e}"

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
        order_id, status = _place_order_raw(params)
        logger.info(f"placeOrder result: order_id={order_id} status={status}")

        if order_id:
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=order_id, status="placed", limit_price=limit_price,
            ))
        elif status.startswith("failed: GSM") or status.startswith("failed: stock suspended"):
            # Hard block — don't re-check order book
            results.append(OrderResult(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_id=None, status=status, limit_price=limit_price,
            ))
        else:
            # Ambiguous failure — AngelOne sometimes executes silently.
            # Re-check the order book before declaring failure.
            logger.warning(f"Ambiguous response for {order.side} {order.quantity} {order.symbol} — re-checking order book...")
            time.sleep(2)
            try:
                ob2 = obj.orderBook()
                fresh_book = ob2.get("data") or []
                verified = _find_in_book(fresh_book, order.symbol, order.side, order.quantity)
                if verified:
                    verified_id = verified.get("orderid", "unknown")
                    logger.info(f"  → found in order book (id={verified_id}) — marking as placed")
                    results.append(OrderResult(
                        symbol=order.symbol, side=order.side, quantity=order.quantity,
                        order_id=str(verified_id), status="placed", limit_price=limit_price,
                    ))
                else:
                    logger.error(f"  → not found in order book — genuinely failed: {status}")
                    results.append(OrderResult(
                        symbol=order.symbol, side=order.side, quantity=order.quantity,
                        order_id=None, status=status, limit_price=limit_price,
                    ))
            except Exception as ob_exc:
                logger.error(f"  → order book re-check failed: {ob_exc}")
                results.append(OrderResult(
                    symbol=order.symbol, side=order.side, quantity=order.quantity,
                    order_id=None, status=status, limit_price=limit_price,
                ))

    return results


class AngelCheckTradeableRequest(BaseModel):
    angel_api_key: str
    angel_client_id: str
    angel_password: str
    angel_totp_secret: str
    symbols: list[str]
    exchange: str = "NSE"


class TradeableResult(BaseModel):
    symbol: str
    status: str   # "ok" | "gsm" | "suspended" | "error"
    reason: str = ""


@app.post("/api/angel/check-tradeable")
def angel_check_tradeable(
    req: AngelCheckTradeableRequest,
    authorization: str = Header(None),
) -> list[TradeableResult]:
    """
    Pre-rebalance GSM/cautionary check. Places a stub BUY order at Rs 1
    for each symbol. AngelOne validates the cautionary flag (AB4036) before
    price, so blocked stocks are detected immediately. Stub orders that land
    are cancelled right away.
    """
    _check_auth(authorization)

    import pyotp
    import time
    import logging
    from SmartApi import SmartConnect

    logger = logging.getLogger("angel_proxy")
    obj = SmartConnect(api_key=req.angel_api_key)
    totp = pyotp.TOTP(req.angel_totp_secret).now()
    session = obj.generateSession(req.angel_client_id, req.angel_password, totp)
    if not session.get("status"):
        raise HTTPException(500, f"AngelOne login failed: {session.get('message', session)}")

    results = []
    for i, sym in enumerate(req.symbols):
        if i > 0:
            time.sleep(1.2)

        # Get EQ token
        try:
            search = obj.searchScrip(req.exchange, sym)
            data = search.get("data") or []
            token = next(
                (d["symboltoken"] for d in data if d.get("tradingsymbol") == f"{sym}-EQ"),
                None,
            )
            if not token:
                results.append(TradeableResult(symbol=sym, status="error", reason="no EQ token"))
                continue
        except Exception as e:
            results.append(TradeableResult(symbol=sym, status="error", reason=str(e)[:80]))
            continue

        time.sleep(0.5)

        # Stub BUY at Rs 1 via direct HTTP — AB4036 fires before price validation for GSM stocks
        auth_token = session["data"]["jwtToken"]  # already includes "Bearer " prefix
        stub_params = {
            "variety": "NORMAL",
            "tradingsymbol": f"{sym}-EQ",
            "symboltoken": token,
            "transactiontype": "BUY",
            "exchange": req.exchange,
            "ordertype": "LIMIT",
            "producttype": "DELIVERY",
            "duration": "DAY",
            "price": "1.00",
            "quantity": "1",
        }
        import requests as _req
        headers = {
            "Content-type": "application/json",
            "Authorization": auth_token,
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "Accept": "application/json",
            "X-PrivateKey": req.angel_api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB",
        }
        try:
            r = _req.post(
                "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder",
                json=stub_params, headers=headers, timeout=10,
            )
            data = r.json()
            if data.get("status") and data.get("data", {}).get("orderid"):
                order_id = data["data"]["orderid"]
                # Cancel immediately
                try:
                    time.sleep(0.5)
                    obj.cancelOrder(str(order_id), "NORMAL")
                    logger.info(f"  {sym}: OK — stub order {order_id} cancelled")
                except Exception:
                    logger.warning(f"  {sym}: stub {order_id} — cancel failed, cancel manually")
                results.append(TradeableResult(symbol=sym, status="ok"))
            else:
                msg = data.get("message", "")
                code = data.get("errorcode", "")
                if code == "AB4036" or "cautionary" in msg.lower():
                    results.append(TradeableResult(symbol=sym, status="gsm", reason=f"AB4036: {msg}"))
                    logger.warning(f"  {sym}: GSM BLOCKED")
                elif code == "AB8051" or "suspended" in msg.lower():
                    results.append(TradeableResult(symbol=sym, status="suspended", reason=f"AB8051: {msg}"))
                    logger.warning(f"  {sym}: SUSPENDED")
                else:
                    # Price rejected or other non-GSM error — stock is tradeable
                    results.append(TradeableResult(symbol=sym, status="ok"))
                    logger.info(f"  {sym}: OK (stub rejected for price: {msg})")
        except Exception as e:
            results.append(TradeableResult(symbol=sym, status="error", reason=str(e)[:120]))
            logger.error(f"  {sym}: error — {e}")

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
