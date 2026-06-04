"""Public-facing trading dashboard for followers.

Clean, intuitive layout designed for people who want to follow the strategy.
Shows what to buy, how it's performing, and when the next rebalance happens.

Run with:
    pip install -e '.[dashboard]'
    streamlit run dashboard.py
"""

from __future__ import annotations

import json
import sys
from calendar import monthrange
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR, OUTPUTS_DIR  # noqa: E402

PAPER_DIR = DATA_DIR / "paper"
LIVE_DIR = DATA_DIR / "live"

# ─── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="JD Quant | Quantitative Strategies",
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
    "yellow": "#e3b341",
}

# ─── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    .stApp {{
        background: {C["bg"]};
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }}

    /* ── Hero ──────────────────────────────── */
    .hero {{
        background: linear-gradient(135deg, #1a1f35 0%, #161b22 50%, #1a2332 100%);
        border: 1px solid {C["border"]};
        border-radius: 16px;
        padding: 2.5rem 3rem;
        margin-bottom: 1.5rem;
        position: relative;
        overflow: hidden;
    }}
    .hero::before {{
        content: '';
        position: absolute;
        top: -50%;
        right: -20%;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, {C["blue"]}08 0%, transparent 70%);
        pointer-events: none;
    }}
    .hero .tag {{
        display: inline-block;
        background: {C["green"]}18;
        color: {C["green"]};
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        margin-bottom: 0.8rem;
        border: 1px solid {C["green"]}33;
    }}
    .hero h1 {{
        font-size: 2.2rem;
        font-weight: 800;
        color: {C["text"]};
        margin: 0 0 0.4rem 0;
        letter-spacing: -0.03em;
        line-height: 1.1;
    }}
    .hero .subtitle {{
        color: {C["muted"]};
        font-size: 1rem;
        margin-bottom: 1.5rem;
        line-height: 1.5;
    }}
    .hero-stats {{
        display: flex;
        gap: 2.5rem;
        flex-wrap: wrap;
    }}
    .hero-stat {{
        text-align: left;
    }}
    .hero-stat .num {{
        font-size: 1.8rem;
        font-weight: 800;
        line-height: 1.1;
    }}
    .hero-stat .num.green {{ color: {C["green"]}; }}
    .hero-stat .num.blue {{ color: {C["blue"]}; }}
    .hero-stat .num.purple {{ color: {C["purple"]}; }}
    .hero-stat .num.orange {{ color: {C["orange"]}; }}
    .hero-stat .lbl {{
        color: {C["muted"]};
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 600;
        margin-top: 0.2rem;
    }}

    /* ── Section ───────────────────────────── */
    .section {{
        background: {C["card"]};
        border: 1px solid {C["border"]};
        border-radius: 14px;
        padding: 1.5rem 1.8rem;
        margin-bottom: 1.2rem;
    }}
    .section h2 {{
        font-size: 1.1rem;
        font-weight: 700;
        color: {C["text"]};
        margin: 0 0 0.3rem 0;
        letter-spacing: -0.01em;
    }}
    .section .desc {{
        color: {C["muted"]};
        font-size: 0.8rem;
        margin-bottom: 1rem;
    }}

    /* ── Portfolio table ───────────────────── */
    .port-table {{
        width: 100%;
        border-collapse: collapse;
    }}
    .port-table th {{
        text-align: left;
        color: {C["muted"]};
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 600;
        padding: 0.5rem 0.8rem;
        border-bottom: 1px solid {C["border"]};
    }}
    .port-table td {{
        padding: 0.7rem 0.8rem;
        border-bottom: 1px solid {C["border"]}88;
        font-size: 0.9rem;
        color: {C["text"]};
    }}
    .port-table tr:last-child td {{
        border-bottom: none;
    }}
    .port-table .ticker {{
        font-weight: 700;
        color: {C["text"]};
    }}
    .port-table .weight {{
        color: {C["blue"]};
        font-weight: 600;
    }}
    .port-table .rank {{
        color: {C["muted"]};
        font-size: 0.8rem;
    }}

    /* ── Live P&L card ─────────────────────── */
    .pnl-card {{
        background: {C["card2"]};
        border: 1px solid {C["border"]};
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        text-align: center;
    }}
    .pnl-card .amount {{
        font-size: 2rem;
        font-weight: 800;
    }}
    .pnl-card .amount.up {{ color: {C["green"]}; }}
    .pnl-card .amount.down {{ color: {C["red"]}; }}
    .pnl-card .label {{
        color: {C["muted"]};
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
        margin-top: 0.3rem;
    }}

    /* ── How it works ──────────────────────── */
    .step {{
        display: flex;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 1rem;
    }}
    .step-num {{
        background: {C["blue"]}18;
        color: {C["blue"]};
        min-width: 32px;
        height: 32px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.85rem;
        border: 1px solid {C["blue"]}33;
    }}
    .step-text {{
        color: {C["text"]};
        font-size: 0.9rem;
        line-height: 1.5;
    }}
    .step-text strong {{
        color: {C["text"]};
    }}
    .step-text span {{
        color: {C["muted"]};
    }}

    /* ── Countdown ─────────────────────────── */
    .countdown {{
        background: linear-gradient(135deg, {C["purple"]}12 0%, {C["blue"]}08 100%);
        border: 1px solid {C["purple"]}33;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        text-align: center;
    }}
    .countdown .days {{
        font-size: 2.5rem;
        font-weight: 800;
        color: {C["purple"]};
        line-height: 1;
    }}
    .countdown .label {{
        color: {C["muted"]};
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
        margin-top: 0.3rem;
    }}

    /* ── Disclaimer ────────────────────────── */
    .disclaimer {{
        background: {C["orange"]}08;
        border: 1px solid {C["orange"]}22;
        border-radius: 8px;
        padding: 0.8rem 1.2rem;
        color: {C["orange"]};
        font-size: 0.75rem;
        line-height: 1.5;
        margin-top: 1.5rem;
    }}

    /* ── Footer ────────────────────────────── */
    .footer {{
        text-align: center;
        color: {C["muted"]};
        font-size: 0.7rem;
        padding: 2rem 0 1rem 0;
        border-top: 1px solid {C["border"]};
        margin-top: 2rem;
    }}

    /* ── Streamlit overrides ───────────────── */
    [data-testid="stSidebar"] {{ display: none; }}
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
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        background: {C["card"]};
        border-radius: 10px;
        padding: 4px;
        border: 1px solid {C["border"]};
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px;
        padding: 0.5rem 1.2rem;
        font-weight: 500;
        font-size: 0.85rem;
        color: {C["muted"]};
    }}
    .stTabs [aria-selected="true"] {{
        background: {C["blue"]}18 !important;
        color: {C["blue"]} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Plotly theme ──────────────────────────────────────────────────────────────

PL = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", color=C["text"], size=12),
    margin=dict(l=40, r=20, t=30, b=40),
    xaxis=dict(gridcolor=C["border"], linecolor=C["border"], zeroline=False),
    yaxis=dict(gridcolor=C["border"], linecolor=C["border"], zeroline=False),
    hoverlabel=dict(bgcolor=C["card"], font_size=12, bordercolor=C["border"]),
)


# ─── Helpers ───────────────────────────────────────────────────────────────────


def list_runs() -> list[Path]:
    if not OUTPUTS_DIR.exists():
        return []
    runs = [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and (p / "summary.json").exists()]
    return sorted(runs, key=lambda p: p.name, reverse=True)


@st.cache_data(show_spinner=False)
def load_summary(run_dir: str) -> dict:
    with open(Path(run_dir) / "summary.json") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_series(run_dir: str, name: str) -> pd.Series:
    df = pd.read_csv(Path(run_dir) / name, index_col=0, parse_dates=True)
    return df.iloc[:, 0]


@st.cache_data(show_spinner=False)
def load_frame(run_dir: str, name: str) -> pd.DataFrame:
    return pd.read_csv(Path(run_dir) / name, index_col=0, parse_dates=True)


def days_until_next_rebalance() -> int:
    today = date.today()
    _, last_day = monthrange(today.year, today.month)
    eom = date(today.year, today.month, last_day)
    delta = (eom - today).days
    return max(0, delta)


def monthly_returns_table(daily_returns: pd.Series) -> pd.DataFrame:
    m = (1 + daily_returns).resample("ME").prod() - 1
    table = m.to_frame(name="ret")
    table["year"] = table.index.year
    table["month"] = table.index.month
    pivot = table.pivot(index="year", columns="month", values="ret").sort_index(ascending=False)
    pivot.columns = [pd.Timestamp(2000, int(c), 1).strftime("%b") for c in pivot.columns]
    return pivot


# ─── Load data ─────────────────────────────────────────────────────────────────

runs = list_runs()

# Find the best backtest run (smallcap_momentum_v2, latest)
primary_run = None
for r in runs:
    if "smallcap_momentum_v2" in r.name and "smoke" not in r.name:
        primary_run = r
        break
if primary_run is None and runs:
    primary_run = runs[0]

if primary_run is None:
    st.error("No backtest data found.")
    st.stop()

summary = load_summary(str(primary_run))
equity = load_series(str(primary_run), "equity_curve.csv")
returns = load_series(str(primary_run), "returns.csv")

# Paper state
paper_state = None
paper_dir = PAPER_DIR / "smallcap_momentum_v2"
if (paper_dir / "state.json").exists():
    with open(paper_dir / "state.json") as f:
        paper_state = json.load(f)

# Live orders
live_orders = None
live_dir = LIVE_DIR / "smallcap_momentum_v2_live"
if (live_dir / "orders.csv").exists():
    live_orders = pd.read_csv(live_dir / "orders.csv")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  HERO BANNER                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

cagr = summary.get("cagr", 0)
sharpe = summary.get("sharpe", 0)
max_dd = summary.get("max_drawdown", 0)
final_eq = summary.get("final_equity", 1)
win_rate = summary.get("win_rate_monthly", 0)

st.markdown(
    f"""
    <div class="hero">
        <div class="tag">LIVE TRADING</div>
        <h1>JD Quant</h1>
        <div class="subtitle">
            A proprietary quantitative strategy that systematically identifies
            high-conviction opportunities in Indian equities. Fully automated,
            rules-based, zero discretion.
        </div>
        <div class="hero-stats">
            <div class="hero-stat">
                <div class="num green">{cagr*100:.1f}%</div>
                <div class="lbl">Annual Return (CAGR)</div>
            </div>
            <div class="hero-stat">
                <div class="num blue">{sharpe:.2f}</div>
                <div class="lbl">Sharpe Ratio</div>
            </div>
            <div class="hero-stat">
                <div class="num orange">{final_eq:.0f}x</div>
                <div class="lbl">Growth of Rs. 1 since 2010</div>
            </div>
            <div class="hero-stat">
                <div class="num purple">{win_rate*100:.0f}%</div>
                <div class="lbl">Profitable Months</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN CONTENT — two columns                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

col_left, col_right = st.columns([3, 2], gap="medium")

# ── LEFT COLUMN ────────────────────────────────────────────────────────────────

with col_left:

    # ── Current Portfolio ──────────────────────────────────────────────────────
    if paper_state and paper_state.get("holdings"):
        holdings = paper_state["holdings"]
        last_rebal = paper_state.get("last_rebalance", "—")
        n_positions = len(holdings)
        sorted_holdings = sorted(holdings.items(), key=lambda x: -x[1])

        rows_html = ""
        for i, (ticker, weight) in enumerate(sorted_holdings, 1):
            pct = f"{weight * 100:.1f}%"
            rows_html += (
                f'<tr><td class="rank">{i}</td>'
                f'<td class="ticker">{ticker}</td>'
                f'<td class="weight">{pct}</td></tr>'
            )

        st.markdown(
            f"""
            <div class="section">
                <h2>Current Portfolio</h2>
                <div class="desc">These are the stocks the strategy currently holds.
                Updated at each monthly rebalance.
                Last rebalanced: {last_rebal} | {n_positions} positions | Equal weight</div>
                <table class="port-table">
                    <thead><tr><th>#</th><th>Stock</th><th>Weight</th></tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("No active positions yet.")

    # ── Equity Curve ───────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="section">
            <h2>Backtest Performance</h2>
            <div class="desc">Growth of Rs. 1 invested in Jan 2010.
            Strategy turned Rs. 1 into Rs. {final_eq:.0f} over {len(equity)//252} years.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=equity.index,
            y=equity.values,
            mode="lines",
            line=dict(color=C["green"], width=2),
            fill="tozeroy",
            fillcolor="rgba(63,185,80,0.06)",
            hovertemplate="%{x|%b %Y}: Rs. %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **PL,
        height=350,
        showlegend=False,
        xaxis_title="",
        yaxis_title="",
        yaxis_type="log",
        yaxis_tickprefix="Rs. ",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Drawdown ───────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="section">
            <h2>Drawdowns</h2>
            <div class="desc">Worst peak-to-trough decline: {max_dd*100:.1f}%.
            Every strategy has bad periods — this shows the pain you'd need to sit through.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    peak = equity.cummax()
    dd = equity / peak - 1
    fig_dd = go.Figure()
    fig_dd.add_trace(
        go.Scatter(
            x=dd.index,
            y=dd.values,
            mode="lines",
            line=dict(color=C["red"], width=1.5),
            fill="tozeroy",
            fillcolor="rgba(248,81,73,0.12)",
            hovertemplate="%{x|%b %Y}: %{y:.1%}<extra></extra>",
        )
    )
    fig_dd.update_layout(
        **PL,
        height=220,
        showlegend=False,
        xaxis_title="",
        yaxis_title="",
        yaxis_tickformat=".0%",
    )
    st.plotly_chart(fig_dd, use_container_width=True)

    # ── Monthly Returns ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="section">
            <h2>Monthly Returns</h2>
            <div class="desc">Color-coded heatmap of monthly returns (%). Green = profit, Red = loss.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        mr = monthly_returns_table(returns) * 100
        years = [str(y) for y in mr.index.tolist()]
        months = mr.columns.tolist()

        fig_hm = go.Figure()
        fig_hm.add_trace(
            go.Heatmap(
                z=mr.values,
                x=months,
                y=years,
                colorscale=[[0, C["red"]], [0.45, "#1e1e1e"], [0.55, "#1e1e1e"], [1, C["green"]]],
                zmid=0,
                showscale=False,
                hovertemplate="%{y} %{x}: %{z:.1f}%<extra></extra>",
            )
        )

        # Add value annotations on each cell
        for i, year in enumerate(years):
            for j, month in enumerate(months):
                val = mr.values[i][j]
                if pd.notna(val):
                    fig_hm.add_annotation(
                        x=month, y=year,
                        text=f"{val:.1f}",
                        showarrow=False,
                        font=dict(size=9, color=C["text"]),
                    )

        fig_hm.update_layout(
            **PL,
            height=max(350, len(mr) * 26),
            xaxis=dict(side="top", dtick=1, gridcolor="rgba(0,0,0,0)"),
            yaxis=dict(autorange="reversed", dtick=1, gridcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig_hm, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not render heatmap: {e}")


# ── RIGHT COLUMN ───────────────────────────────────────────────────────────────

with col_right:

    # ── Next Rebalance ─────────────────────────────────────────────────────────
    days_left = days_until_next_rebalance()
    st.markdown(
        f"""
        <div class="countdown">
            <div class="days">{days_left}</div>
            <div class="label">Days until next rebalance</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("")

    # ── Live P&L ───────────────────────────────────────────────────────────────
    if live_orders is not None and not live_orders.empty:
        placed = live_orders[live_orders["status"] == "placed"]
        if not placed.empty:
            total_invested = placed["estimated_value"].sum()
            n_stocks = len(placed)
            trade_date = placed["timestamp"].iloc[0][:10]

            order_rows = ""
            for _, row in placed.iterrows():
                qty = row["quantity"]
                symbol = row["symbol"]
                value = row["estimated_value"]
                order_rows += (
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:0.4rem 0;border-bottom:1px solid {C["border"]}88;'
                    f'font-size:0.88rem;">'
                    f'<span style="font-weight:600;color:{C["text"]}">{symbol}</span>'
                    f'<span style="color:{C["muted"]}">{qty} shares</span>'
                    f'<span style="color:{C["blue"]};font-weight:600">Rs. {value:,.0f}</span>'
                    f'</div>'
                )

            st.markdown(
                f"""
                <div class="section">
                    <h2>Live Portfolio</h2>
                    <div class="desc">Real money deployed on {trade_date}.
                    {n_stocks} stocks, Rs. {total_invested:,.0f} invested.</div>
                    {order_rows}
                    <div style="display:flex;justify-content:space-between;
                    padding:0.6rem 0 0;font-size:0.9rem;">
                        <span style="font-weight:700;color:{C["text"]}">Total</span>
                        <span style="font-weight:700;color:{C["green"]}">Rs. {total_invested:,.0f}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("")

    # ── How It Works ───────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="section">
            <h2>How It Works</h2>
            <div class="desc">A simple, rules-based process. No stock-picking, no gut feelings.</div>
            <div class="step">
                <div class="step-num">1</div>
                <div class="step-text">
                    <strong>Screen</strong><br>
                    <span>Filter a broad universe of Indian equities through
                    proprietary quantitative criteria to identify candidates.</span>
                </div>
            </div>
            <div class="step">
                <div class="step-num">2</div>
                <div class="step-text">
                    <strong>Score</strong><br>
                    <span>Rank each stock using a multi-factor scoring model
                    that captures persistent market anomalies.</span>
                </div>
            </div>
            <div class="step">
                <div class="step-num">3</div>
                <div class="step-text">
                    <strong>Construct</strong><br>
                    <span>Build an equal-weight portfolio of top-ranked names.
                    Diversified, disciplined, no concentration bets.</span>
                </div>
            </div>
            <div class="step">
                <div class="step-num">4</div>
                <div class="step-text">
                    <strong>Rebalance</strong><br>
                    <span>Systematically refresh the portfolio on a fixed schedule.
                    No emotions, no overrides — the model decides.</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Key Stats ──────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="section">
            <h2>Key Numbers</h2>
            <div class="desc">Based on backtested performance across 16 years of Indian market data.</div>
            <table class="port-table">
                <tr><td>Annual return (CAGR)</td><td class="weight">{cagr*100:.1f}%</td></tr>
                <tr><td>Annual volatility</td><td style="color:{C['text']}">{summary.get('annual_vol',0)*100:.1f}%</td></tr>
                <tr><td>Sharpe ratio</td><td style="color:{C['text']}">{sharpe:.2f}</td></tr>
                <tr><td>Sortino ratio</td><td style="color:{C['text']}">{summary.get('sortino',0):.2f}</td></tr>
                <tr><td>Max drawdown</td><td style="color:{C['red']}">{max_dd*100:.1f}%</td></tr>
                <tr><td>Recovery from worst drawdown</td><td style="color:{C['muted']}">~26 months</td></tr>
                <tr><td>Win rate (monthly)</td><td style="color:{C['text']}">{win_rate*100:.0f}%</td></tr>
                <tr><td>Backtest period</td><td style="color:{C['muted']}">16 years</td></tr>
                <tr><td>Rebalance frequency</td><td style="color:{C['muted']}">Fixed schedule</td></tr>
                <tr><td>Number of positions</td><td style="color:{C['muted']}">Concentrated</td></tr>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Paper Trading Status ───────────────────────────────────────────────────
    if paper_state:
        eq_path = paper_dir / "equity.csv"
        eq_data = None
        if eq_path.exists():
            eq_data = pd.read_csv(eq_path)

        days_tracked = len(eq_data) if eq_data is not None else 0
        paper_equity = paper_state.get("equity", 1.0)
        paper_pnl = (paper_equity - 1.0) * 100

        pnl_class = "up" if paper_pnl >= 0 else "down"
        pnl_sign = "+" if paper_pnl >= 0 else ""

        st.markdown(
            f"""
            <div class="section">
                <h2>Paper Trading</h2>
                <div class="desc">Live simulation running since {paper_state.get('created', '—')[:10]}.
                Tracking real market prices without real money.</div>
                <div class="pnl-card">
                    <div class="amount {pnl_class}">{pnl_sign}{paper_pnl:.2f}%</div>
                    <div class="label">Paper P&amp;L</div>
                </div>
                <div style="margin-top:0.8rem;text-align:center;">
                    <span style="color:{C['muted']};font-size:0.8rem;">
                        {days_tracked} day(s) tracked |
                        {90 - days_tracked} more days until graduation gate
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  DISCLAIMER                                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

st.markdown(
    f"""
    <div class="disclaimer">
        <strong>Disclaimer:</strong> This is not financial advice. Past performance does not
        guarantee future results. The strategy shown is based on historical backtesting which
        has inherent limitations. Always do your own research before investing.
    </div>
    """,
    unsafe_allow_html=True,
)
