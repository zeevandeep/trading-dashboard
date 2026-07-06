"""Kite Connect broker adapter — real order execution on NSE via Zerodha.

Login flow:
    1. Open browser to Kite login URL
    2. User logs in, Kite redirects to localhost with request_token
    3. Exchange request_token for access_token
    4. Access token cached in data/paper/.kite_session.json for the day

Order execution:
    - CNC (delivery) orders only — matches our monthly rebalance strategy
    - Market orders at close (or LIMIT near LTP for better fills)
    - All orders logged to trades CSV for audit
"""

from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from trading.config import DATA_DIR, Secrets
from trading.utils.logging import setup_logging


def _import_kite():
    from kiteconnect import KiteConnect
    return KiteConnect

log = setup_logging("kite")

SESSION_FILE = DATA_DIR / "paper" / ".kite_session.json"
REDIRECT_PORT = 5927
REDIRECT_URL = f"http://127.0.0.1:{REDIRECT_PORT}/callback"


def _load_session() -> dict | None:
    """Load cached session if it exists and is from today."""
    if not SESSION_FILE.exists():
        return None
    with open(SESSION_FILE) as f:
        session = json.load(f)
    if session.get("login_date") != date.today().isoformat():
        log.info("Cached session is from a previous day — need fresh login.")
        return None
    return session


def _save_session(session: dict) -> None:
    """Cache session for the rest of the day."""
    session["login_date"] = date.today().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump(session, f, indent=2, default=str)


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the request_token from Kite's redirect."""

    request_token: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "request_token" in params:
            _CallbackHandler.request_token = params["request_token"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Login successful!</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        elif "status" in params and params["status"][0] == "cancelled":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Login cancelled.</h2></body></html>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress HTTP logs


def login(api_key: str | None = None, api_secret: str | None = None):
    """Authenticate with Kite Connect. Returns a ready-to-use KiteConnect instance.

    Tries cached session first, falls back to browser OAuth flow.
    """
    KiteConnect = _import_kite()

    if not api_key:
        secrets = Secrets.from_env()
        api_key = secrets.kite_api_key
        api_secret = secrets.kite_api_secret

    if not api_key or not api_secret:
        raise ValueError(
            "Kite API key and secret required. Set KITE_API_KEY and "
            "KITE_API_SECRET in your .env file."
        )

    kite = KiteConnect(api_key=api_key)

    # Try cached session
    cached = _load_session()
    if cached and cached.get("access_token"):
        kite.set_access_token(cached["access_token"])
        try:
            profile = kite.profile()
            log.info(f"Reusing cached session for {profile['user_name']}")
            return kite
        except Exception:
            log.info("Cached session expired, re-authenticating...")

    # Browser login flow
    login_url = kite.login_url()

    # Start local callback server (serve_forever so it handles favicon/preflight too)
    _CallbackHandler.request_token = None
    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Try to open browser
    log.info(f"Opening browser for Kite login...")
    try:
        import subprocess
        subprocess.run(["open", login_url], check=True)
    except Exception:
        webbrowser.open(login_url)

    print(f"\n{'='*60}")
    print(f"  LOGIN URL (open in browser if it didn't open):")
    print(f"  {login_url}")
    print(f"{'='*60}\n")

    # Wait for callback (up to 300 seconds)
    log.info("Waiting for login callback (5 min timeout)...")
    for _ in range(300):
        if _CallbackHandler.request_token:
            break
        time.sleep(1)

    server.shutdown()

    if not _CallbackHandler.request_token:
        raise TimeoutError("Kite login timed out — no callback received within 5 minutes.")

    # Exchange request_token for access_token
    session_data = kite.generate_session(
        _CallbackHandler.request_token, api_secret=api_secret
    )
    access_token = session_data["access_token"]
    kite.set_access_token(access_token)

    # Cache for the day
    _save_session({
        "access_token": access_token,
        "user_id": session_data.get("user_id"),
        "user_name": session_data.get("user_name"),
    })

    log.info(f"Logged in as {session_data.get('user_name')} ({session_data.get('user_id')})")
    return kite


def get_holdings(kite) -> dict[str, dict]:
    """Get current holdings as {tradingsymbol: {quantity, average_price, last_price, pnl}}."""
    raw = kite.holdings()
    holdings = {}
    for h in raw:
        if h["quantity"] > 0:
            holdings[h["tradingsymbol"]] = {
                "quantity": h["quantity"],
                "average_price": h["average_price"],
                "last_price": h["last_price"],
                "pnl": h["pnl"],
                "instrument_token": h["instrument_token"],
                "exchange": h["exchange"],
            }
    return holdings


def get_ltp(kite, symbols: list[str], exchange: str = "NSE") -> dict[str, float]:
    """Get last traded prices for a list of symbols.

    Uses yfinance as the primary source (free, no Kite Quote subscription needed).
    Falls back to Kite LTP if yfinance fails and kite is provided.

    Returns {symbol: price}.
    """
    if not symbols:
        return {}

    # Primary: yfinance
    prices = _get_ltp_yfinance(symbols)
    if prices:
        log.info(f"LTP from yfinance for {len(prices)}/{len(symbols)} symbols")
        missing = [s for s in symbols if s not in prices]
        if missing:
            log.warning(f"yfinance missing prices for: {missing}")
        return prices

    # Fallback: Kite quote API (requires paid subscription)
    if kite is not None:
        log.info("yfinance failed, trying Kite LTP...")
        instruments = [f"{exchange}:{s}" for s in symbols]
        raw = kite.ltp(instruments)
        return {
            s: raw[f"{exchange}:{s}"]["last_price"]
            for s in symbols
            if f"{exchange}:{s}" in raw
        }

    return {}


def _get_ltp_yfinance(symbols: list[str]) -> dict[str, float]:
    """Fetch last traded prices from yfinance.

    Handles NSE ticker format: strips .NS suffix from our internal symbols
    and adds it for yfinance lookup.
    """
    import yfinance as yf

    # Map internal symbols to yfinance tickers
    # Our symbols may be like "RELIANCE" (NSE) — yfinance needs "RELIANCE.NS"
    yf_map = {}
    for s in symbols:
        if s.endswith(".NS") or s.endswith(".BO"):
            yf_map[s] = s
        else:
            yf_map[s] = f"{s}.NS"

    yf_tickers = list(yf_map.values())
    reverse_map = {v: k for k, v in yf_map.items()}

    try:
        data = yf.download(yf_tickers, period="5d", progress=False, threads=True)
        if data.empty:
            return {}

        # yf.download returns MultiIndex columns when multiple tickers
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]]
            close.columns = yf_tickers

        # Use the last valid price for each ticker
        last_prices = close.ffill().iloc[-1]

        prices = {}
        for yf_ticker, price in last_prices.items():
            if pd.notna(price) and price > 0:
                internal = reverse_map.get(yf_ticker, yf_ticker)
                prices[internal] = float(price)
        return prices
    except Exception as e:
        log.warning(f"yfinance LTP fetch failed: {e}")
        return {}


def compute_orders(
    target_weights: dict[str, float],
    current_holdings: dict[str, dict],
    prices: dict[str, float],
    total_capital: float,
) -> list[dict]:
    """Compute the orders needed to go from current holdings to target weights.

    Returns list of order dicts: {symbol, side, quantity, estimated_value}.
    """
    orders = []

    # Current positions in terms of quantities
    current_qty = {s: h["quantity"] for s, h in current_holdings.items()}

    # Target quantities
    target_qty = {}
    for symbol, weight in target_weights.items():
        if symbol not in prices or prices[symbol] <= 0:
            log.warning(f"No price for {symbol}, skipping")
            continue
        target_value = total_capital * weight
        qty = int(target_value / prices[symbol])  # floor to whole shares
        if qty > 0:
            target_qty[symbol] = qty

    # Sells first (frees up capital)
    all_symbols = set(list(current_qty.keys()) + list(target_qty.keys()))
    for symbol in sorted(all_symbols):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur

        if delta == 0:
            continue

        price = prices.get(symbol, 0)
        if delta < 0:
            orders.append({
                "symbol": symbol,
                "side": "SELL",
                "quantity": abs(delta),
                "estimated_value": abs(delta) * price,
            })

    # Then buys
    for symbol in sorted(all_symbols):
        cur = current_qty.get(symbol, 0)
        tgt = target_qty.get(symbol, 0)
        delta = tgt - cur

        if delta <= 0:
            continue

        price = prices.get(symbol, 0)
        orders.append({
            "symbol": symbol,
            "side": "BUY",
            "quantity": delta,
            "estimated_value": delta * price,
        })

    return orders


def place_orders(
    kite,
    orders: list[dict],
    prices: dict[str, float] | None = None,
    exchange: str = "NSE",
    dry_run: bool = False,
    limit_buffer_pct: float = 0.5,
) -> list[dict]:
    """Place CNC LIMIT orders on Kite Connect.

    Uses LIMIT orders at LTP + buffer (for buys) or LTP - buffer (for sells)
    because Kite API does not allow naked market orders.

    Parameters
    ----------
    prices: {symbol: ltp} — used to set limit price. If None, fetches via yfinance.
    limit_buffer_pct: buffer above/below LTP for limit price (default 0.5%).
    """
    KiteConnect = _import_kite()
    results = []

    if prices is None:
        symbols = [o["symbol"] for o in orders]
        prices = get_ltp(kite, symbols)

    for order in orders:
        transaction = (
            KiteConnect.TRANSACTION_TYPE_BUY
            if order["side"] == "BUY"
            else KiteConnect.TRANSACTION_TYPE_SELL
        )

        ltp = prices.get(order["symbol"], 0)
        # NSE tick size: 0.05 for most stocks, 0.10 for price >= 1000
        tick = 0.10 if ltp >= 1000 else 0.05
        if order["side"] == "BUY":
            raw_price = ltp * (1 + limit_buffer_pct / 100)
            # Round UP to nearest tick for buys (ensures fill)
            limit_price = round(round(raw_price / tick) * tick, 2)
        else:
            raw_price = ltp * (1 - limit_buffer_pct / 100)
            # Round DOWN to nearest tick for sells
            limit_price = round(round(raw_price / tick) * tick, 2)

        log.info(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"{order['side']} {order['quantity']} x {order['symbol']} "
            f"@ limit {limit_price:.2f} (LTP {ltp:.2f})"
        )

        if dry_run:
            results.append({**order, "order_id": None, "status": "dry_run", "limit_price": limit_price})
            continue

        try:
            order_id = kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=order["symbol"],
                transaction_type=transaction,
                quantity=order["quantity"],
                product=KiteConnect.PRODUCT_CNC,
                order_type=KiteConnect.ORDER_TYPE_LIMIT,
                price=limit_price,
                validity=KiteConnect.VALIDITY_DAY,
            )
            log.info(f"  Order placed: {order_id}")
            results.append({**order, "order_id": order_id, "status": "placed", "limit_price": limit_price})
        except Exception as e:
            log.error(f"  Order FAILED: {e}")
            results.append({**order, "order_id": None, "status": f"failed: {e}", "limit_price": limit_price})

    return results


def place_orders_remote(
    access_token: str,
    api_key: str,
    orders: list[dict],
    prices: dict[str, float],
    proxy_url: str,
    proxy_api_key: str,
    exchange: str = "NSE",
    limit_buffer_pct: float = 0.5,
) -> list[dict]:
    """Place orders via the Render proxy (fixed IP).

    Same interface as place_orders() but routes through the remote proxy
    so Kite sees Render's whitelisted IP instead of the local machine's.
    """
    import requests

    payload = {
        "kite_api_key": api_key,
        "access_token": access_token,
        "orders": [
            {"symbol": o["symbol"], "side": o["side"], "quantity": o["quantity"],
             "estimated_value": o.get("estimated_value", 0)}
            for o in orders
        ],
        "prices": prices,
        "exchange": exchange,
        "limit_buffer_pct": limit_buffer_pct,
    }

    url = f"{proxy_url.rstrip('/')}/api/place-orders"
    log.info(f"Sending {len(orders)} orders to proxy at {proxy_url}")

    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {proxy_api_key}"},
        timeout=60,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Proxy returned {resp.status_code}: {resp.text}")

    remote_results = resp.json()
    results = []
    for r in remote_results:
        results.append({
            "symbol": r["symbol"],
            "side": r["side"],
            "quantity": r["quantity"],
            "order_id": r.get("order_id"),
            "status": r["status"],
            "limit_price": r.get("limit_price", 0),
        })
        if r["status"] == "placed":
            log.info(f"  {r['side']} {r['quantity']} x {r['symbol']} — placed (order_id={r['order_id']})")
        else:
            log.error(f"  {r['side']} {r['quantity']} x {r['symbol']} — {r['status']}")

    return results


def log_orders(results: list[dict], log_path: Path) -> None:
    """Append order results to a CSV log."""
    if not results:
        return
    df = pd.DataFrame(results)
    df["timestamp"] = datetime.now().isoformat()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        df.to_csv(log_path, mode="a", header=False, index=False)
    else:
        df.to_csv(log_path, index=False)
