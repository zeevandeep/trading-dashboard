"""JD Quant — Live Trading Dashboard (/live).

Private page. Shows real portfolio performance, positions, and orders
for both live strategies side-by-side with a combined NAV chart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR  # noqa: E402

LIVE_DIR = DATA_DIR / "live"
PAPER_DIR = DATA_DIR / "paper"

ASCENT_DIR  = LIVE_DIR / "smallcap_momentum_v2_live"
BEDROCK_DIR = LIVE_DIR / "value_quality_v1_live"
TF_DIR      = PAPER_DIR / "ascent_trend_filtered"

# ── Colors ────────────────────────────────────────────────────────────────────
C = {
    "bg":      "#06080d",
    "card":    "#111820",
    "card2":   "#1a2332",
    "border":  "#1e2a3a",
    "text":    "#f0f4f8",
    "muted":   "#64748b",
    "sub":     "#94a3b8",
    "green":   "#10b981",
    "red":     "#ef4444",
    "blue":    "#3b82f6",
    "purple":  "#a78bfa",
    "orange":  "#f59e0b",
    "teal":    "#06b6d4",
}

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="JD Quant | Live",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

* {{ font-family: 'DM Sans', system-ui, sans-serif !important; }}
code {{ font-family: 'JetBrains Mono', monospace !important; }}
.stApp {{ background: {C["bg"]}; }}
[data-testid="stSidebar"] {{ display: none; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.5rem; max-width: 1280px; }}

.private-badge {{
    background: {C["orange"]}12;
    border: 1px solid {C["orange"]}30;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    color: {C["orange"]};
    font-size: 0.75rem;
    font-weight: 600;
    text-align: center;
    margin-bottom: 1.2rem;
    letter-spacing: 0.02em;
}}

.page-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    padding-bottom: 1.2rem;
    border-bottom: 1px solid {C["border"]};
}}
.page-header h1 {{
    font-size: 1.4rem; font-weight: 800; color: {C["text"]};
    letter-spacing: -0.03em; margin: 0;
}}
.page-header .back-link {{
    color: {C["sub"]}; text-decoration: none; font-size: 0.8rem;
    font-weight: 500;
}}
.page-header .back-link:hover {{ color: {C["text"]}; }}

/* Regime banner */
.regime-banner {{
    border-radius: 12px;
    padding: 0.9rem 1.4rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    font-size: 0.82rem;
}}
.regime-banner.risk-off {{
    background: {C["red"]}0d;
    border: 1px solid {C["red"]}30;
}}
.regime-banner.risk-on {{
    background: {C["green"]}0d;
    border: 1px solid {C["green"]}30;
}}
.regime-badge {{
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; padding: 0.25rem 0.7rem; border-radius: 20px;
    margin-right: 0.8rem;
}}
.regime-badge.off {{ background: {C["red"]}20; color: {C["red"]}; }}
.regime-badge.on  {{ background: {C["green"]}20; color: {C["green"]}; }}
.regime-label {{ font-weight: 700; font-size: 0.9rem; }}
.regime-label.off {{ color: {C["red"]}; }}
.regime-label.on  {{ color: {C["green"]}; }}
.regime-meta {{ color: {C["sub"]}; font-size: 0.78rem; }}

/* Strategy header cards */
.strat-header {{
    background: {C["card"]};
    border: 1px solid {C["border"]};
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
}}
.strat-header .strat-name {{
    font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: {C["sub"]}; margin-bottom: 0.3rem;
}}
.strat-header .strat-nav {{
    font-size: 2rem; font-weight: 800; letter-spacing: -0.04em; line-height: 1.1;
}}
.strat-header .strat-nav.up {{ color: {C["green"]}; }}
.strat-header .strat-nav.dn {{ color: {C["red"]}; }}
.strat-header .strat-daily {{
    font-size: 0.8rem; font-weight: 600; margin-left: 0.6rem;
    padding: 0.15rem 0.5rem; border-radius: 6px;
}}
.strat-header .strat-daily.up {{ background: {C["green"]}15; color: {C["green"]}; }}
.strat-header .strat-daily.dn {{ background: {C["red"]}15; color: {C["red"]}; }}
.strat-meta-row {{
    display: flex; gap: 1.5rem; margin-top: 0.8rem;
}}
.strat-meta-item {{ }}
.strat-meta-item .val {{
    font-size: 1rem; font-weight: 700; color: {C["text"]};
}}
.strat-meta-item .lbl {{
    font-size: 0.6rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: {C["muted"]}; margin-top: 0.1rem;
}}

/* Section header */
.section-label {{
    font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: {C["muted"]};
    margin: 1.6rem 0 0.8rem;
}}

/* Positions table */
.pos-table {{ width: 100%; border-collapse: collapse; }}
.pos-table th {{
    text-align: left; color: {C["muted"]}; font-size: 0.58rem;
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em;
    padding: 0 0.5rem 0.5rem; border-bottom: 1px solid {C["border"]};
}}
.pos-table td {{
    padding: 0.45rem 0.5rem;
    border-bottom: 1px solid {C["border"]}55;
    font-size: 0.8rem; color: {C["text"]};
}}
.pos-table tr:last-child td {{ border-bottom: none; }}
.pos-sym {{ font-weight: 700; font-family: 'JetBrains Mono', monospace !important; }}
.pos-up  {{ color: {C["green"]}; font-weight: 600; }}
.pos-dn  {{ color: {C["red"]}; font-weight: 600; }}
.pos-neu {{ color: {C["sub"]}; }}

div[data-testid="stMetric"] {{
    background: {C["card2"]}; border: 1px solid {C["border"]};
    border-radius: 12px; padding: 0.7rem 1rem;
}}
div[data-testid="stMetric"] label {{
    color: {C["muted"]} !important; font-size: 0.6rem !important;
    text-transform: uppercase; letter-spacing: 0.08em;
}}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    font-size: 1.1rem !important; font-weight: 700 !important;
}}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_equity(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def load_positions(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    latest = df["date"].max()
    return df[df["date"] == latest].sort_values("pnl_pct", ascending=False).reset_index(drop=True)


def nav_pct(nav: float) -> float:
    return (nav - 1.0) * 100


def fmt(v: float, prefix="", pct=False, sign=True) -> str:
    s = "+" if sign and v >= 0 else ""
    if pct:
        return f"{s}{v:.2f}%"
    return f"{s}{prefix}{v:,.0f}"


# ── Load data ─────────────────────────────────────────────────────────────────

ascent_eq  = load_equity(ASCENT_DIR / "equity.csv")
bedrock_eq = load_equity(BEDROCK_DIR / "equity.csv")
tf_eq      = load_equity(TF_DIR / "equity.csv")

ascent_pos  = load_positions(ASCENT_DIR / "positions.csv")
bedrock_pos = load_positions(BEDROCK_DIR / "positions.csv")

# Latest rows
a_last = ascent_eq.iloc[-1]  if not ascent_eq.empty  else None
b_last = bedrock_eq.iloc[-1] if not bedrock_eq.empty else None
a_prev = ascent_eq.iloc[-2]  if len(ascent_eq) > 1   else None
b_prev = bedrock_eq.iloc[-2] if len(bedrock_eq) > 1  else None
tf_last = tf_eq.iloc[-1] if not tf_eq.empty else None

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="private-badge">Private — Do not share this URL</div>
<div class="page-header">
    <h1>Live Trading Console</h1>
    <a href="/" class="back-link" target="_self">← Back to home</a>
</div>
""", unsafe_allow_html=True)

# ── Regime Banner ─────────────────────────────────────────────────────────────

if tf_last is not None:
    regime     = tf_last.get("regime", "UNKNOWN")
    nifty_10m  = float(tf_last.get("nifty_10m_ret", 0))
    tf_date    = tf_last.get("date", "")
    if hasattr(tf_date, "strftime"):
        tf_date = tf_date.strftime("%b %d, %Y")

    is_on      = regime == "RISK_ON"
    cls        = "risk-on" if is_on else "risk-off"
    badge_cls  = "on" if is_on else "off"
    icon       = "▲" if is_on else "▼"
    label_txt  = "RISK-ON: Ascent fully deployed" if is_on else "RISK-OFF: Trend filter in cash"
    nifty_txt  = f"NIFTY 10-month return: {nifty_10m:+.1f}%"
    tf_nav_pct = nav_pct(float(tf_last.get("nav", 1.0)))

    st.markdown(f"""
    <div class="regime-banner {cls}">
        <div style="display:flex;align-items:center;">
            <span class="regime-badge {badge_cls}">{icon} {regime.replace("_", "-")}</span>
            <span class="regime-label {badge_cls}">{label_txt}</span>
        </div>
        <div class="regime-meta">{nifty_txt} &nbsp;·&nbsp; Filter NAV: {tf_nav_pct:+.2f}% since Jun &nbsp;·&nbsp; {tf_date}</div>
    </div>
    """, unsafe_allow_html=True)

# ── Strategy Summary Cards ─────────────────────────────────────────────────────

col_a, col_b = st.columns(2, gap="large")

def render_strat_card(col, label, color, eq_last, eq_prev, n_pos_override=None):
    with col:
        if eq_last is None:
            st.markdown(f'<div class="strat-header"><div class="strat-name">{label}</div><div style="color:{C["muted"]}">No data</div></div>', unsafe_allow_html=True)
            return

        nav    = float(eq_last["nav"])
        total  = nav_pct(nav)
        mv     = float(eq_last.get("market_value", 0))
        inv    = float(eq_last.get("invested", 0))
        pnl    = float(eq_last.get("pnl", 0))
        n_pos  = n_pos_override or int(eq_last.get("n_positions", 0))
        last_d = eq_last["date"]
        if hasattr(last_d, "strftime"):
            last_d = last_d.strftime("%b %d, %Y")

        daily = 0.0
        if eq_prev is not None:
            prev_nav = float(eq_prev["nav"])
            daily = (nav / prev_nav - 1) * 100 if prev_nav > 0 else 0

        up = total >= 0
        cls_nav   = "up" if up else "dn"
        cls_daily = "up" if daily >= 0 else "dn"
        sign_d    = "+" if daily >= 0 else ""
        sign_t    = "+" if total >= 0 else ""

        pnl_sign  = "+" if pnl >= 0 else ""
        pnl_color = C["green"] if pnl >= 0 else C["red"]

        st.markdown(f"""
        <div class="strat-header" style="border-top: 3px solid {color};">
            <div class="strat-name">{label}</div>
            <div style="display:flex;align-items:baseline;gap:0.3rem;">
                <span class="strat-nav {cls_nav}">{sign_t}{total:.2f}%</span>
                <span class="strat-daily {cls_daily}">{sign_d}{daily:.2f}% today</span>
            </div>
            <div class="strat-meta-row">
                <div class="strat-meta-item">
                    <div class="val">₹{mv:,.0f}</div>
                    <div class="lbl">Market Value</div>
                </div>
                <div class="strat-meta-item">
                    <div class="val">₹{inv:,.0f}</div>
                    <div class="lbl">Invested</div>
                </div>
                <div class="strat-meta-item">
                    <div class="val" style="color:{pnl_color}">{pnl_sign}₹{abs(pnl):,.0f}</div>
                    <div class="lbl">P&L</div>
                </div>
                <div class="strat-meta-item">
                    <div class="val">{n_pos}</div>
                    <div class="lbl">Positions</div>
                </div>
                <div class="strat-meta-item">
                    <div class="val" style="font-size:0.8rem;color:{C['sub']}">{last_d}</div>
                    <div class="lbl">Last Marked</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

render_strat_card(col_a, "Ascent",  C["blue"],   a_last, a_prev)
render_strat_card(col_b, "Bedrock", C["purple"], b_last, b_prev)

# ── Combined NAV Chart ────────────────────────────────────────────────────────

st.markdown('<div class="section-label">NAV Performance (since inception)</div>', unsafe_allow_html=True)

fig = go.Figure()

# Normalize all series to start at 100 for visual comparison
def nav_to_100(df, col="nav"):
    s = df[col].astype(float)
    return s / s.iloc[0] * 100

if not ascent_eq.empty:
    fig.add_trace(go.Scatter(
        x=ascent_eq["date"],
        y=nav_to_100(ascent_eq),
        mode="lines",
        name="Ascent (live)",
        line=dict(color=C["blue"], width=2.5),
        hovertemplate="%{x|%b %d}: %{y:.1f}<extra>Ascent</extra>",
    ))

if not bedrock_eq.empty:
    fig.add_trace(go.Scatter(
        x=bedrock_eq["date"],
        y=nav_to_100(bedrock_eq),
        mode="lines",
        name="Bedrock (live)",
        line=dict(color=C["purple"], width=2.5),
        hovertemplate="%{x|%b %d}: %{y:.1f}<extra>Bedrock</extra>",
    ))

if not tf_eq.empty:
    fig.add_trace(go.Scatter(
        x=tf_eq["date"],
        y=nav_to_100(tf_eq),
        mode="lines",
        name="Ascent + Trend Filter (paper)",
        line=dict(color=C["teal"], width=1.5, dash="dot"),
        hovertemplate="%{x|%b %d}: %{y:.1f}<extra>Trend Filter</extra>",
    ))

# Baseline
if not ascent_eq.empty:
    fig.add_hline(y=100, line=dict(color=C["muted"], width=1, dash="dot"), opacity=0.4)

fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, system-ui", color=C["sub"], size=11),
    margin=dict(l=40, r=20, t=10, b=40),
    height=320,
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        bgcolor="rgba(0,0,0,0)", font=dict(size=11),
    ),
    hovermode="x unified",
)
fig.update_xaxes(gridcolor=C["border"], linecolor=C["border"], zeroline=False)
fig.update_yaxes(
    gridcolor=C["border"], linecolor=C["border"], zeroline=False,
    ticksuffix="", tickformat=".0f",
)

st.plotly_chart(fig, use_container_width=True)

# ── Positions ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Current Positions</div>', unsafe_allow_html=True)

col_a2, col_b2 = st.columns(2, gap="large")

def render_positions(col, label, pos_df):
    with col:
        if pos_df.empty:
            st.markdown(f'<p style="color:{C["muted"]};font-size:0.8rem;">No positions data</p>', unsafe_allow_html=True)
            return

        rows = ""
        for _, r in pos_df.iterrows():
            sym    = r["symbol"]
            qty    = int(r["quantity"])
            price  = float(r["price"])
            cost   = float(r["cost_basis"])
            mval   = float(r["market_value"])
            pnl    = float(r["pnl"])
            pct    = float(r["pnl_pct"])
            sign   = "+" if pnl >= 0 else ""
            cls    = "pos-up" if pnl >= 0 else "pos-dn"
            rows += f"""
            <tr>
                <td class="pos-sym">{sym}</td>
                <td class="pos-neu">{qty}</td>
                <td class="pos-neu">₹{cost:,.0f}</td>
                <td class="pos-neu">₹{price:,.1f}</td>
                <td>₹{mval:,.0f}</td>
                <td class="{cls}">{sign}{pct:.1f}%</td>
            </tr>"""

        total_mval = pos_df["market_value"].sum()
        total_pnl  = pos_df["pnl"].sum()
        total_pct  = (total_pnl / pos_df["cost_basis"].sum() * 100) if pos_df["cost_basis"].sum() > 0 else 0
        tot_cls    = "pos-up" if total_pnl >= 0 else "pos-dn"
        tot_sign   = "+" if total_pnl >= 0 else ""

        st.markdown(f"""
        <div style="font-size:0.72rem;font-weight:700;color:{C["sub"]};text-transform:uppercase;
             letter-spacing:0.1em;margin-bottom:0.5rem;">{label}</div>
        <table class="pos-table">
            <thead>
                <tr>
                    <th>Symbol</th><th>Qty</th><th>Cost</th>
                    <th>Price</th><th>Value</th><th>P&L</th>
                </tr>
            </thead>
            <tbody>
                {rows}
                <tr style="border-top:1px solid {C["border"]};">
                    <td colspan="4" style="font-weight:700;color:{C["text"]};">Total</td>
                    <td style="font-weight:700;">₹{total_mval:,.0f}</td>
                    <td class="{tot_cls}" style="font-weight:700;">{tot_sign}{total_pct:.1f}%</td>
                </tr>
            </tbody>
        </table>
        """, unsafe_allow_html=True)

render_positions(col_a2, "Ascent Positions",  ascent_pos)
render_positions(col_b2, "Bedrock Positions", bedrock_pos)

# ── Order Log ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Recent Orders</div>', unsafe_allow_html=True)

tab_a, tab_b = st.tabs(["Ascent", "Bedrock"])

for tab, strat_dir, label in [
    (tab_a, ASCENT_DIR,  "Ascent"),
    (tab_b, BEDROCK_DIR, "Bedrock"),
]:
    with tab:
        orders_path = strat_dir / "orders.csv"
        if not orders_path.exists():
            st.info(f"No orders for {label}")
            continue
        orders_df = pd.read_csv(orders_path)
        if "timestamp" in orders_df.columns:
            orders_df = orders_df.sort_values("timestamp", ascending=False)
        st.dataframe(orders_df.head(30), use_container_width=True, hide_index=True)
