"""Private live trading dashboard — accessible at /live.

Shows real portfolio, order history, P&L, and broker state.
Not linked from the main dashboard — only accessible by direct URL.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR, OUTPUTS_DIR  # noqa: E402

LIVE_DIR = DATA_DIR / "live"
PAPER_DIR = DATA_DIR / "paper"

# ─── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="JD Quant | Live",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Colors ────────────────────────────────────────────────────────────────────

C = {
    "bg": "#0e1117",
    "card": "#161b22",
    "card2": "#1c2333",
    "border": "#21262d",
    "text": "#e6edf3",
    "muted": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "blue": "#58a6ff",
    "purple": "#bc8cff",
    "orange": "#d29922",
}

# ─── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .stApp {{ background: {C["bg"]}; font-family: 'Inter', system-ui, sans-serif; }}
    [data-testid="stSidebar"] {{ display: none; }}

    .page-header {{
        background: linear-gradient(135deg, #1a1f35 0%, #161b22 100%);
        border: 1px solid {C["border"]};
        border-radius: 14px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .page-header h1 {{
        margin: 0; font-size: 1.5rem; font-weight: 800;
        color: {C["text"]}; letter-spacing: -0.02em;
    }}
    .page-header .status {{
        background: {C["red"]}18;
        color: {C["red"]};
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        border: 1px solid {C["red"]}33;
    }}

    .card {{
        background: {C["card"]};
        border: 1px solid {C["border"]};
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
    }}
    .card h3 {{
        font-size: 0.95rem; font-weight: 700; color: {C["text"]};
        margin: 0 0 0.8rem 0;
    }}

    .order-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.6rem 0;
        border-bottom: 1px solid {C["border"]}66;
        font-size: 0.88rem;
    }}
    .order-row:last-child {{ border-bottom: none; }}

    .private-badge {{
        background: {C["orange"]}15;
        border: 1px solid {C["orange"]}33;
        border-radius: 8px;
        padding: 0.6rem 1rem;
        color: {C["orange"]};
        font-size: 0.8rem;
        margin-bottom: 1rem;
        text-align: center;
    }}

    div[data-testid="stMetric"] {{
        background: {C["card2"]};
        border: 1px solid {C["border"]};
        border-radius: 12px;
        padding: 0.8rem 1rem;
    }}
    div[data-testid="stMetric"] label {{
        color: {C["muted"]} !important;
        font-size: 0.7rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-size: 1.3rem !important;
        font-weight: 700 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Header ───────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="private-badge">
        This page is private. Do not share this URL.
    </div>
    <div class="page-header">
        <h1>Live Trading Console</h1>
        <div class="status">PRIVATE</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Load data ─────────────────────────────────────────────────────────────────

# Find all live strategies
live_strategies = []
if LIVE_DIR.exists():
    live_strategies = [
        p.name for p in LIVE_DIR.iterdir()
        if p.is_dir() and (p / "orders.csv").exists()
    ]

if not live_strategies:
    st.warning("No live trading data found.")
    st.stop()

selected_strategy = st.selectbox("Strategy", sorted(live_strategies), label_visibility="collapsed")
live_dir = LIVE_DIR / selected_strategy

# ─── Orders ───────────────────────────────────────────────────────────────────

orders_df = pd.read_csv(live_dir / "orders.csv")

if orders_df.empty:
    st.info("No orders yet.")
    st.stop()

placed = orders_df[orders_df["status"] == "placed"]
failed = orders_df[orders_df["status"].str.startswith("failed")] if "status" in orders_df.columns else pd.DataFrame()

# ─── Live P&L (from equity.csv) ──────────────────────────────────────────────

equity_path = live_dir / "equity.csv"
positions_path = live_dir / "positions.csv"

has_equity = equity_path.exists()
if has_equity:
    eq_df = pd.read_csv(equity_path)
    latest = eq_df.iloc[-1] if not eq_df.empty else None
else:
    latest = None

total_invested = latest["invested"] if latest is not None else (placed["estimated_value"].sum() if not placed.empty else 0)
mkt_value = latest["market_value"] if latest is not None else total_invested
pnl = latest["pnl"] if latest is not None else 0
pnl_pct = latest["pnl_pct"] if latest is not None else 0
n_stocks = int(latest["n_positions"]) if latest is not None else len(placed)
trade_date = placed["timestamp"].iloc[0][:10] if not placed.empty and "timestamp" in placed.columns else "—"
last_mark = latest["date"] if latest is not None else "—"

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Invested", f"Rs. {total_invested:,.0f}")
m2.metric("Market Value", f"Rs. {mkt_value:,.0f}")
pnl_str = f"Rs. {pnl:+,.0f}" if pnl != 0 else "Rs. 0"
m3.metric("P&L", pnl_str)
m4.metric("Return", f"{pnl_pct:+.2f}%")
m5.metric("Last Marked", str(last_mark))

# ─── Position Details (from positions.csv) ───────────────────────────────────

if positions_path.exists():
    pos_df = pd.read_csv(positions_path)
    latest_date = pos_df["date"].max()
    latest_pos = pos_df[pos_df["date"] == latest_date].sort_values("pnl_pct", ascending=False)

    st.markdown("")
    rows_html = ""
    for _, row in latest_pos.iterrows():
        sym = row["symbol"]
        qty = int(row["quantity"])
        cost = row["cost_basis"]
        price = row["price"]
        mval = row["market_value"]
        rpnl = row["pnl"]
        rpct = row["pnl_pct"]
        color = C["green"] if rpnl >= 0 else C["red"]
        sign = "+" if rpnl >= 0 else ""
        rows_html += (
            f'<div class="order-row">'
            f'<span style="font-weight:700;color:{C["text"]};min-width:100px">{sym}</span>'
            f'<span style="color:{C["muted"]}">{qty} @ Rs.{price:,.1f}</span>'
            f'<span style="color:{C["muted"]}">Cost: Rs.{cost:,.0f}</span>'
            f'<span style="color:{C["blue"]};font-weight:600">Rs.{mval:,.0f}</span>'
            f'<span style="color:{color};font-weight:600;min-width:100px;text-align:right">{sign}Rs.{rpnl:,.0f} ({sign}{rpct:.1f}%)</span>'
            f'</div>'
        )

    total_mval = latest_pos["market_value"].sum()
    total_pnl = latest_pos["pnl"].sum()
    total_color = C["green"] if total_pnl >= 0 else C["red"]
    total_sign = "+" if total_pnl >= 0 else ""

    st.markdown(
        f"""
        <div class="card">
            <h3>Positions (as of {latest_date})</h3>
            {rows_html}
            <div style="display:flex;justify-content:space-between;padding:0.8rem 0 0;
            border-top:1px solid {C["border"]};margin-top:0.4rem;font-size:0.95rem;">
                <span style="font-weight:700;color:{C["text"]}">Total</span>
                <span style="font-weight:700;color:{total_color}">{total_sign}Rs. {total_pnl:,.0f} | Mkt: Rs. {total_mval:,.0f}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

elif not placed.empty:
    st.markdown("")
    holdings_html = '<div class="card"><h3>Current Holdings (cost basis)</h3>'
    for _, row in placed.iterrows():
        symbol = row["symbol"]
        qty = row["quantity"]
        value = row["estimated_value"]
        holdings_html += (
            f'<div class="order-row">'
            f'<span style="font-weight:700;color:{C["text"]};min-width:120px">{symbol}</span>'
            f'<span style="color:{C["muted"]}">{qty} shares</span>'
            f'<span style="color:{C["blue"]};font-weight:600">Rs. {value:,.0f}</span>'
            f'</div>'
        )
    holdings_html += '</div>'
    st.markdown(holdings_html, unsafe_allow_html=True)

# ─── Equity Curve ────────────────────────────────────────────────────────────

if has_equity and len(eq_df) > 1:
    st.markdown("")
    st.markdown(f'<div class="card"><h3>Portfolio Value Over Time</h3></div>', unsafe_allow_html=True)

    eq_df["date"] = pd.to_datetime(eq_df["date"])
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=eq_df["date"], y=eq_df["market_value"],
        mode="lines+markers", name="Market Value",
        line=dict(color=C["blue"], width=2), marker=dict(size=5),
        hovertemplate="%{x|%Y-%m-%d}: Rs. %{y:,.0f}<extra></extra>",
    ))
    fig_eq.add_trace(go.Scatter(
        x=eq_df["date"], y=eq_df["invested"],
        mode="lines", name="Cost Basis",
        line=dict(color=C["muted"], width=1, dash="dash"),
        hovertemplate="%{x|%Y-%m-%d}: Rs. %{y:,.0f}<extra></extra>",
    ))
    fig_eq.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=C["text"], size=12), margin=dict(l=40, r=20, t=20, b=40),
        height=280, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig_eq.update_xaxes(gridcolor=C["border"], linecolor=C["border"], zeroline=False)
    fig_eq.update_yaxes(gridcolor=C["border"], linecolor=C["border"], zeroline=False, tickprefix="Rs. ")
    st.plotly_chart(fig_eq, use_container_width=True)

# ─── Paper Trading Comparison ────────────────────────────────────────────────

paper_dir = PAPER_DIR / "smallcap_momentum_v2"
if (paper_dir / "state.json").exists():
    with open(paper_dir / "state.json") as f:
        paper_state = json.load(f)

    eq_path = paper_dir / "equity.csv"
    if eq_path.exists():
        eq_df = pd.read_csv(eq_path)
        if not eq_df.empty:
            st.markdown("")
            st.markdown(
                f'<div class="card"><h3>Paper Trading (top 15)</h3></div>',
                unsafe_allow_html=True,
            )

            days_tracked = len(eq_df)
            paper_equity = paper_state.get("equity", 1.0)
            paper_pnl = (paper_equity - 1.0) * 100

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Paper Equity", f"{paper_equity:.4f}")
            p2.metric("Paper P&L", f"{paper_pnl:+.2f}%")
            p3.metric("Days Tracked", str(days_tracked))
            p4.metric("Gate Progress", f"{min(days_tracked, 90)}/90 days")

            # Paper equity chart
            eq_df["date"] = pd.to_datetime(eq_df["date"])
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=eq_df["date"], y=eq_df["equity"],
                    mode="lines+markers",
                    line=dict(color=C["green"], width=2),
                    marker=dict(size=6),
                    hovertemplate="%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>",
                )
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=C["text"], size=12),
                margin=dict(l=40, r=20, t=20, b=40),
                height=250,
                showlegend=False,
            )
            fig.update_xaxes(gridcolor=C["border"], linecolor=C["border"], zeroline=False)
            fig.update_yaxes(gridcolor=C["border"], linecolor=C["border"], zeroline=False)
            st.plotly_chart(fig, use_container_width=True)

            # Paper holdings
            holdings = paper_state.get("holdings", {})
            if holdings:
                sorted_h = sorted(holdings.items(), key=lambda x: -x[1])
                h_html = '<div class="card"><h3>Paper Positions (15 stocks)</h3>'
                for ticker, weight in sorted_h:
                    h_html += (
                        f'<div class="order-row">'
                        f'<span style="font-weight:600;color:{C["text"]}">{ticker}</span>'
                        f'<span style="color:{C["blue"]};font-weight:600">{weight*100:.1f}%</span>'
                        f'</div>'
                    )
                h_html += '</div>'
                st.markdown(h_html, unsafe_allow_html=True)

# ─── Full Order Log ──────────────────────────────────────────────────────────

st.markdown("")
st.markdown(
    f'<div class="card"><h3>Full Order Log</h3></div>',
    unsafe_allow_html=True,
)
st.dataframe(
    orders_df.sort_values("timestamp", ascending=False) if "timestamp" in orders_df.columns else orders_df,
    use_container_width=True,
    hide_index=True,
)
