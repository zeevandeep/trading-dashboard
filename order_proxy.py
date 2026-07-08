"""Lightweight order proxy — forwards Kite API calls from a fixed-IP server.

Deployed on Render alongside the Streamlit dashboard. The local rebalance
script sends orders here (with the Kite access_token obtained via browser
login), and this proxy forwards them to Kite from Render's whitelisted IP.

Security:
    - PROXY_API_KEY env var required in Authorization header
    - Access token is per-request, never stored
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

    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=req.kite_api_key)
    kite.set_access_token(req.access_token)

    results = []
    for order in req.orders:
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
                variety=KiteConnect.VARIETY_REGULAR,
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
