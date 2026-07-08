"""Rebalance — Private action page for monthly/quarterly portfolio changes.

Shows what changed at last rebalance, what actions are needed for live
portfolio, and copy-ready order lists. Accessible at /Rebalance.
Not linked from the public site.
"""

from __future__ import annotations

import json
import sys
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dashboard_shared import (
    DATA_DIR,
    PAPER_DIR,
    inject_css,
    render_disclaimer,
)

st.set_page_config(
    page_title="Rebalance Actions | JD Quant",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

LIVE_DIR = DATA_DIR / "live"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_state(strategy_dir: Path) -> dict | None:
    p = strategy_dir / "state.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def load_trades(strategy_dir: Path) -> pd.DataFrame:
    p = strategy_dir / "trades.csv"
    if p.exists():
        return pd.read_csv(p)
    return pd.DataFrame()


def load_equity(strategy_dir: Path) -> pd.DataFrame:
    p = strategy_dir / "equity.csv"
    if p.exists():
        return pd.read_csv(p)
    return pd.DataFrame()


def load_live_orders(strategy_dir: Path) -> pd.DataFrame:
    p = strategy_dir / "orders.csv"
    if p.exists():
        return pd.read_csv(p)
    return pd.DataFrame()


def days_to_month_end() -> int:
    t = date.today()
    _, ld = monthrange(t.year, t.month)
    return max(0, (date(t.year, t.month, ld) - t).days)


def days_to_quarter_end() -> int:
    t = date.today()
    qtr_months = [3, 6, 9, 12]
    next_qtr = next(m for m in qtr_months if m >= t.month)
    _, ld = monthrange(t.year, next_qtr)
    target = date(t.year, next_qtr, ld)
    return max(0, (target - t).days)


def compute_live_holdings(orders_df: pd.DataFrame) -> dict[str, int]:
    """Net buys and sells to get current holdings {symbol: quantity}."""
    holdings: dict[str, int] = {}
    placed = orders_df[orders_df["status"] == "placed"]
    for _, row in placed.iterrows():
        sym = row["symbol"]
        qty = int(row["quantity"])
        if sym not in holdings:
            holdings[sym] = 0
        if row["side"] == "BUY":
            holdings[sym] += qty
        elif row["side"] == "SELL":
            holdings[sym] -= qty
    return {s: q for s, q in holdings.items() if q > 0}


# ─── Load Data ────────────────────────────────────────────────────────────────

ascent_dir = PAPER_DIR / "smallcap_momentum_v2"
bedrock_dir = PAPER_DIR / "value_quality_v1"

ascent_state = load_state(ascent_dir)
bedrock_state = load_state(bedrock_dir)

ascent_trades = load_trades(ascent_dir)
bedrock_trades = load_trades(bedrock_dir)

ascent_equity = load_equity(ascent_dir)
bedrock_equity = load_equity(bedrock_dir)

# Live portfolio
live_strategy = "smallcap_momentum_v2_live"
live_dir = LIVE_DIR / live_strategy
live_orders = load_live_orders(live_dir)
live_equity = load_equity(live_dir)


# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown(f"""
<div class="navbar">
    <a href="/" target="_self" style="text-decoration:none;color:inherit;">
    <div class="logo">
        <div class="logo-mark">JD</div>
        JD Quant
    </div>
    </a>
    <div class="nav-status">
        <div class="live-dot"></div>
        Rebalance &middot; {datetime.now().strftime("%d %b %Y")}
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">Action Center</div>
    <h1>Rebalance <span>Actions</span></h1>
    <div class="tagline">
        What changed, what to do next, and copy-ready order lists.
    </div>
</div>
""", unsafe_allow_html=True)


# ── Countdown Bar ─────────────────────────────────────────────────────────────

d_ascent = days_to_month_end()
d_bedrock = days_to_quarter_end()

ascent_last = ascent_state.get("last_rebalance", "—") if ascent_state else "—"
bedrock_last = bedrock_state.get("last_rebalance", "—") if bedrock_state else "—"

st.markdown(f"""
<div class="stat-row">
    <div class="stat-cell">
        <div class="val accent">{d_ascent}</div>
        <div class="lbl">Days to Ascent rebalance</div>
    </div>
    <div class="stat-cell">
        <div class="val purple">{d_bedrock}</div>
        <div class="lbl">Days to Bedrock rebalance</div>
    </div>
    <div class="stat-cell">
        <div class="val" style="color:var(--text-secondary)">{ascent_last}</div>
        <div class="lbl">Ascent last rebalanced</div>
    </div>
    <div class="stat-cell">
        <div class="val" style="color:var(--text-secondary)">{bedrock_last}</div>
        <div class="lbl">Bedrock last rebalanced</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Last Rebalance Trades ─────────────────────────────────────────────────────

col_a, col_b = st.columns(2, gap="large")

for col, name, trades_df, state, badge_bg, badge_color in [
    (col_a, "Ascent", ascent_trades, ascent_state, "var(--accent-dim)", "var(--accent)"),
    (col_b, "Bedrock", bedrock_trades, bedrock_state, "var(--purple-dim)", "var(--purple)"),
]:
    with col:
        if trades_df.empty or state is None:
            st.markdown(f"""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">{name} — Last Rebalance</div>
                </div>
                <div class="card-desc">No trades yet.</div>
            </div>
            """, unsafe_allow_html=True)
            continue

        last_date = state.get("last_rebalance", "")
        last_trades = trades_df[trades_df["date"] == last_date]

        buys = last_trades[last_trades["side"] == "buy"]
        sells = last_trades[last_trades["side"] == "sell"]

        buy_list = ", ".join(sorted(buys["ticker"].tolist())) if not buys.empty else "—"
        sell_list = ", ".join(sorted(sells["ticker"].tolist())) if not sells.empty else "—"

        if last_trades.empty:
            trade_summary = "No changes — holdings unchanged."
        else:
            trade_summary = f"{len(buys)} buys, {len(sells)} sells"

        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">{name} — Last Rebalance</div>
                <div class="card-badge" style="background:{badge_bg};color:{badge_color};">{last_date}</div>
            </div>
            <div class="card-desc">{trade_summary}</div>
        """, unsafe_allow_html=True)

        if not sells.empty:
            st.markdown(f"""
            <div style="margin:0.75rem 0 0.25rem;color:var(--red);font-weight:600;font-size:0.85rem;">SOLD</div>
            <div style="color:var(--text-secondary);font-size:0.9rem;line-height:1.8;">{sell_list}</div>
            """, unsafe_allow_html=True)

        if not buys.empty:
            st.markdown(f"""
            <div style="margin:0.75rem 0 0.25rem;color:var(--green);font-weight:600;font-size:0.85rem;">BOUGHT</div>
            <div style="color:var(--text-secondary);font-size:0.9rem;line-height:1.8;">{buy_list}</div>
            """, unsafe_allow_html=True)

        # Current holdings
        holdings = state.get("holdings", {})
        if holdings:
            tickers = sorted(holdings.keys())
            st.markdown(f"""
            <div style="margin:1rem 0 0.25rem;color:var(--text-tertiary);font-weight:600;font-size:0.85rem;">CURRENT ({len(tickers)} positions)</div>
            <div style="color:var(--text-secondary);font-size:0.9rem;line-height:1.8;">{", ".join(tickers)}</div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


# ── Live Portfolio Actions ────────────────────────────────────────────────────

st.markdown("""
<div class="card-v2" style="margin-top:2rem;">
    <div class="card-header">
        <div class="card-title">Live Portfolio — Actions Needed</div>
        <div class="card-badge" style="background:var(--gold-dim);color:var(--gold);">Kite</div>
    </div>
</div>
""", unsafe_allow_html=True)

if live_orders.empty:
    st.info("No live portfolio found.")
else:
    live_holdings = compute_live_holdings(live_orders)

    if live_holdings:
        # Show current live holdings
        hold_rows = ""
        for sym in sorted(live_holdings.keys()):
            qty = live_holdings[sym]
            hold_rows += f'<tr><td style="color:var(--text-tertiary);font-weight:600;">HOLD</td><td class="sym">{sym}</td><td style="text-align:right">{qty} shares</td></tr>'
        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Current Holdings ({len(live_holdings)} positions)</div>
            </div>
            <table class="htable">{hold_rows}</table>
        </div>
        """, unsafe_allow_html=True)

        # Last rebalance date from orders
        last_date = live_orders["timestamp"].max()[:10] if "timestamp" in live_orders.columns else "—"
        st.markdown(f"""
        <div class="card-v2" style="margin-top:1rem;">
            <div class="card-header">
                <div class="card-title">Execute</div>
                <div class="card-badge" style="background:var(--accent-dim);color:var(--accent);">Last: {last_date}</div>
            </div>
            <div class="card-desc">Run during market hours (9:15 AM - 3:30 PM IST):</div>
            <pre style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:1rem;color:#e2e8f0;font-size:0.85rem;overflow-x:auto;">
# Step 1: Preview orders
python scripts/monthly_live_rebalance.py --capital 100000 --dry-run

# Step 2: Execute
python scripts/monthly_live_rebalance.py --capital 100000</pre>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="padding:1rem;color:var(--green);font-weight:600;">
            No active holdings.
        </div>
        """, unsafe_allow_html=True)


# ── Live P&L Snapshot ─────────────────────────────────────────────────────────

if not live_equity.empty:
    latest = live_equity.iloc[-1]
    pnl = latest.get("pnl", 0)
    pnl_pct = latest.get("pnl_pct", 0)
    invested = latest.get("invested", 0)
    mkt_val = latest.get("market_value", 0)
    mark_date = latest.get("date", "—")
    pnl_color = "var(--green)" if pnl >= 0 else "var(--red)"
    pnl_sign = "+" if pnl >= 0 else ""

    st.markdown(f"""
    <div class="card-v2" style="margin-top:1rem;">
        <div class="card-header">
            <div class="card-title">Live P&L</div>
            <div class="card-badge" style="background:var(--gold-dim);color:var(--gold);">{mark_date}</div>
        </div>
        <div class="stat-row">
            <div class="stat-cell">
                <div class="val" style="color:var(--text-secondary)">Rs. {invested:,.0f}</div>
                <div class="lbl">Invested</div>
            </div>
            <div class="stat-cell">
                <div class="val" style="color:var(--text-secondary)">Rs. {mkt_val:,.0f}</div>
                <div class="lbl">Market Value</div>
            </div>
            <div class="stat-cell">
                <div class="val" style="color:{pnl_color}">{pnl_sign}Rs. {abs(pnl):,.0f}</div>
                <div class="lbl">P&L</div>
            </div>
            <div class="stat-cell">
                <div class="val" style="color:{pnl_color}">{pnl_sign}{pnl_pct:.2f}%</div>
                <div class="lbl">Return</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

render_disclaimer()
