"""Professional trading dashboard for sharing strategy performance.

Loads backtest runs from outputs/, paper/live trading state from data/,
and renders an interactive, public-facing dashboard with Plotly charts,
professional styling, and a follower-friendly signal board.

Run with:
    pip install -e '.[dashboard]'
    streamlit run dashboard.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
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
    page_title="Jeevandeep | Systematic Trading",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Theme / CSS ───────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0e1117",
    "card": "#161b22",
    "border": "#21262d",
    "text": "#e6edf3",
    "muted": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "blue": "#58a6ff",
    "purple": "#bc8cff",
    "orange": "#d29922",
    "accent": "#58a6ff",
}

st.markdown(
    f"""
    <style>
    /* ── Global ────────────────────────────────── */
    .stApp {{
        background-color: {COLORS["bg"]};
    }}

    /* ── Header bar ────────────────────────────── */
    .dash-header {{
        background: linear-gradient(135deg, #161b22 0%, #1a1f2e 100%);
        border-bottom: 1px solid {COLORS["border"]};
        padding: 1.2rem 2rem;
        margin: -1rem -1rem 1.5rem -1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .dash-header h1 {{
        margin: 0;
        font-size: 1.5rem;
        font-weight: 700;
        color: {COLORS["text"]};
        letter-spacing: -0.02em;
    }}
    .dash-header .subtitle {{
        color: {COLORS["muted"]};
        font-size: 0.85rem;
        margin-top: 0.2rem;
    }}
    .dash-header .badge {{
        background: {COLORS["green"]}22;
        color: {COLORS["green"]};
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        border: 1px solid {COLORS["green"]}44;
    }}

    /* ── Metric cards ──────────────────────────── */
    .metric-card {{
        background: {COLORS["card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        text-align: center;
    }}
    .metric-card .label {{
        color: {COLORS["muted"]};
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }}
    .metric-card .value {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {COLORS["text"]};
        line-height: 1.2;
    }}
    .metric-card .value.positive {{ color: {COLORS["green"]}; }}
    .metric-card .value.negative {{ color: {COLORS["red"]}; }}

    /* ── Section headers ───────────────────────── */
    .section-title {{
        color: {COLORS["text"]};
        font-size: 1.1rem;
        font-weight: 600;
        margin: 1.5rem 0 0.8rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid {COLORS["border"]};
    }}

    /* ── Position table ────────────────────────── */
    .position-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.6rem 1rem;
        border-bottom: 1px solid {COLORS["border"]};
        font-size: 0.9rem;
    }}
    .position-row:hover {{
        background: {COLORS["border"]}44;
    }}
    .position-row .ticker {{
        font-weight: 600;
        color: {COLORS["text"]};
        min-width: 100px;
    }}
    .position-row .weight {{
        color: {COLORS["blue"]};
        font-weight: 600;
    }}

    /* ── Status indicator ──────────────────────── */
    .status-dot {{
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }}
    .status-dot.live {{ background: {COLORS["green"]}; }}
    .status-dot.paper {{ background: {COLORS["orange"]}; }}

    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.4; }}
    }}

    /* ── Info banner ───────────────────────────── */
    .info-banner {{
        background: {COLORS["blue"]}11;
        border: 1px solid {COLORS["blue"]}33;
        border-radius: 8px;
        padding: 0.8rem 1.2rem;
        color: {COLORS["blue"]};
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }}

    /* ── Tab styling ───────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        background: {COLORS["card"]};
        border-radius: 10px;
        padding: 4px;
        border: 1px solid {COLORS["border"]};
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px;
        padding: 0.5rem 1.2rem;
        font-weight: 500;
        font-size: 0.85rem;
        color: {COLORS["muted"]};
    }}
    .stTabs [aria-selected="true"] {{
        background: {COLORS["accent"]}22 !important;
        color: {COLORS["accent"]} !important;
    }}

    /* ── Footer ────────────────────────────────── */
    .dash-footer {{
        margin-top: 3rem;
        padding: 1.5rem 0;
        border-top: 1px solid {COLORS["border"]};
        text-align: center;
        color: {COLORS["muted"]};
        font-size: 0.75rem;
    }}

    /* ── Streamlit overrides ───────────────────── */
    [data-testid="stSidebar"] {{
        background: {COLORS["card"]};
        border-right: 1px solid {COLORS["border"]};
    }}
    .stSelectbox label, .stMultiSelect label {{
        color: {COLORS["muted"]} !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    div[data-testid="stMetric"] {{
        background: {COLORS["card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 12px;
        padding: 1rem 1.2rem;
    }}
    div[data-testid="stMetric"] label {{
        color: {COLORS["muted"]} !important;
        font-size: 0.72rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Plotly layout template ────────────────────────────────────────────────────

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", color=COLORS["text"], size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    xaxis=dict(
        gridcolor=COLORS["border"],
        linecolor=COLORS["border"],
        zeroline=False,
    ),
    yaxis=dict(
        gridcolor=COLORS["border"],
        linecolor=COLORS["border"],
        zeroline=False,
    ),
    hoverlabel=dict(bgcolor=COLORS["card"], font_size=12, bordercolor=COLORS["border"]),
)


def make_fig(**kwargs) -> go.Figure:
    """Create a Figure pre-configured with the dashboard theme."""
    fig = go.Figure()
    layout = {**PLOTLY_LAYOUT, **kwargs}
    fig.update_layout(**layout)
    return fig


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


def fmt_pct(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "--"
    return f"{x * 100:.2f}%"


def fmt_num(x: float | None, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "--"
    return f"{x:.{digits}f}"


def value_color(val: float | None, invert: bool = False) -> str:
    """Return 'positive', 'negative', or '' CSS class."""
    if val is None or pd.isna(val):
        return ""
    positive = val > 0
    if invert:
        positive = not positive
    return "positive" if positive else "negative"


def metric_card(label: str, value: str, css_class: str = "") -> str:
    return f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value {css_class}">{value}</div>
    </div>
    """


def monthly_returns_table(daily_returns: pd.Series) -> pd.DataFrame:
    m = (1 + daily_returns).resample("ME").prod() - 1
    table = m.to_frame(name="ret")
    table["year"] = table.index.year
    table["month"] = table.index.month
    pivot = table.pivot(index="year", columns="month", values="ret").sort_index(ascending=False)
    pivot.columns = [pd.Timestamp(2000, int(c), 1).strftime("%b") for c in pivot.columns]
    return pivot


# ─── Header ───────────────────────────────────────────────────────────────────

runs = list_runs()

# Determine overall status
has_paper = PAPER_DIR.exists() and any(
    p.is_dir() and (p / "state.json").exists() for p in PAPER_DIR.iterdir()
) if PAPER_DIR.exists() else False

has_live = LIVE_DIR.exists() and any(
    p.is_dir() and (p / "orders.csv").exists() for p in LIVE_DIR.iterdir()
) if LIVE_DIR.exists() else False

if has_live:
    status_html = '<span class="status-dot live"></span> Live'
elif has_paper:
    status_html = '<span class="status-dot paper"></span> Paper Trading'
else:
    status_html = '<span class="badge">Research</span>'

st.markdown(
    f"""
    <div class="dash-header">
        <div>
            <h1>Systematic Trading</h1>
            <div class="subtitle">Quantitative strategies &middot; Indian equities</div>
        </div>
        <div>{status_html}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── No runs guard ────────────────────────────────────────────────────────────

if not runs:
    st.markdown(
        """
        <div class="info-banner">
            No backtest runs found. Run a backtest first, then refresh this page.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.code("python main.py backtest --config configs/smallcap_momentum_v1.yaml", language="bash")
    st.stop()

# ─── Run selector (top bar, not sidebar) ───────────────────────────────────────

run_names = [p.name for p in runs]
col_sel, col_info = st.columns([3, 1])
with col_sel:
    selected = st.selectbox(
        "Strategy run",
        run_names,
        index=0,
        label_visibility="collapsed",
    )
with col_info:
    st.caption(f"{len(runs)} run(s) available")

run_dir = OUTPUTS_DIR / selected
summary = load_summary(str(run_dir))
equity = load_series(str(run_dir), "equity_curve.csv")
returns = load_series(str(run_dir), "returns.csv")

# ─── Tabs ──────────────────────────────────────────────────────────────────────

tab_signal, tab_overview, tab_perf, tab_port, tab_compare, tab_paper, tab_live = st.tabs(
    ["Signal Board", "Overview", "Performance", "Portfolio", "Compare", "Paper", "Live"]
)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  SIGNAL BOARD — public-facing tab for followers                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_signal:
    st.markdown('<div class="section-title">Current Signals</div>', unsafe_allow_html=True)

    # Headline metrics
    cagr_val = summary.get("cagr")
    sharpe_val = summary.get("sharpe")
    dd_val = summary.get("max_drawdown")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CAGR", fmt_pct(cagr_val))
    m2.metric("Sharpe Ratio", fmt_num(sharpe_val))
    m3.metric("Max Drawdown", fmt_pct(dd_val))
    m4.metric("Win Rate (Monthly)", fmt_pct(summary.get("win_rate_monthly")))

    st.markdown("")  # spacer

    # Current positions from the latest run
    weights_path = run_dir / "weights.csv"
    signal_left, signal_right = st.columns([2, 3])

    with signal_left:
        st.markdown('<div class="section-title">Active Positions</div>', unsafe_allow_html=True)

        if weights_path.exists():
            weights = load_frame(str(run_dir), "weights.csv")
            latest_date = weights.index.max()
            latest = weights.loc[latest_date]
            latest = latest[latest > 0].sort_values(ascending=False)

            st.caption(f"As of {latest_date.date()}  |  {len(latest)} positions")

            pos_html = ""
            for ticker, w in latest.items():
                pct = f"{w * 100:.1f}%"
                pos_html += f"""
                <div class="position-row">
                    <span class="ticker">{ticker}</span>
                    <span class="weight">{pct}</span>
                </div>
                """
            st.markdown(pos_html, unsafe_allow_html=True)
        else:
            st.info("No position data available for this run.")

    with signal_right:
        st.markdown('<div class="section-title">Equity Curve</div>', unsafe_allow_html=True)

        fig = make_fig(height=380)
        fig.add_trace(
            go.Scatter(
                x=equity.index,
                y=equity.values,
                mode="lines",
                line=dict(color=COLORS["blue"], width=2),
                fill="tozeroy",
                fillcolor="rgba(88,166,255,0.07)",
                hovertemplate="Date: %{x|%Y-%m-%d}<br>Equity: %{y:.4f}<extra></extra>",
            )
        )
        fig.update_layout(
            xaxis_title="",
            yaxis_title="Equity (normalized)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Performance summary at bottom
    st.markdown('<div class="section-title">Strategy Summary</div>', unsafe_allow_html=True)
    date_range = f"{equity.index.min().date()} to {equity.index.max().date()}"
    days = len(equity)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Period", date_range)
    s2.metric("Trading Days", f"{days:,}")
    s3.metric("Annual Vol", fmt_pct(summary.get("annual_vol")))
    s4.metric("Calmar Ratio", fmt_num(summary.get("calmar")))

    # Paper trading current state if available
    if has_paper:
        st.markdown('<div class="section-title">Paper Trading Status</div>', unsafe_allow_html=True)
        paper_strategies = [
            p.name for p in PAPER_DIR.iterdir()
            if p.is_dir() and (p / "state.json").exists()
        ]
        for strat_name in sorted(paper_strategies):
            paper_dir = PAPER_DIR / strat_name
            with open(paper_dir / "state.json") as f:
                pstate = json.load(f)
            p1, p2, p3, p4 = st.columns(4)
            p1.metric(
                f"{strat_name}",
                f"Equity: {fmt_num(pstate.get('equity'), 4)}",
            )
            p2.metric("Positions", str(len(pstate.get("holdings", {}))))
            p3.metric("Trades", str(pstate.get("trade_count", 0)))
            p4.metric("Last Rebalance", pstate.get("last_rebalance", "never"))

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  OVERVIEW                                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_overview:
    st.markdown(f'<div class="section-title">{selected}</div>', unsafe_allow_html=True)
    st.caption(
        f"{equity.index.min().date()} to {equity.index.max().date()}  |  "
        f"{len(equity):,} trading days"
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("CAGR", fmt_pct(summary.get("cagr")))
    c2.metric("Sharpe", fmt_num(summary.get("sharpe")))
    c3.metric("Max Drawdown", fmt_pct(summary.get("max_drawdown")))
    c4.metric("Calmar", fmt_num(summary.get("calmar")))
    c5.metric("Final Equity", fmt_num(summary.get("final_equity"), 4))

    # Equity curve — Plotly
    st.markdown('<div class="section-title">Equity Curve</div>', unsafe_allow_html=True)
    fig_eq = make_fig(height=360)
    fig_eq.add_trace(
        go.Scatter(
            x=equity.index,
            y=equity.values,
            mode="lines",
            line=dict(color=COLORS["green"], width=2),
            fill="tozeroy",
            fillcolor="rgba(63,185,80,0.05)",
            name="Equity",
            hovertemplate="%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>",
        )
    )
    fig_eq.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
    st.plotly_chart(fig_eq, use_container_width=True)

    # Drawdown — Plotly
    st.markdown('<div class="section-title">Drawdown</div>', unsafe_allow_html=True)
    peak = equity.cummax()
    dd = equity / peak - 1
    fig_dd = make_fig(height=240)
    fig_dd.add_trace(
        go.Scatter(
            x=dd.index,
            y=dd.values,
            mode="lines",
            line=dict(color=COLORS["red"], width=1.5),
            fill="tozeroy",
            fillcolor="rgba(248,81,73,0.13)",
            name="Drawdown",
            hovertemplate="%{x|%Y-%m-%d}: %{y:.2%}<extra></extra>",
        )
    )
    fig_dd.update_layout(
        showlegend=False,
        xaxis_title="",
        yaxis_title="",
        yaxis_tickformat=".0%",
    )
    st.plotly_chart(fig_dd, use_container_width=True)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PERFORMANCE                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_perf:
    st.markdown('<div class="section-title">Performance Detail</div>', unsafe_allow_html=True)

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Summary Metrics**")
        tbl = []
        for k, v in summary.items():
            if isinstance(v, float):
                if k in {"cagr", "annual_vol", "max_drawdown", "win_rate_monthly"}:
                    tbl.append((k.replace("_", " ").title(), fmt_pct(v)))
                else:
                    tbl.append((k.replace("_", " ").title(), fmt_num(v)))
            else:
                tbl.append((k.replace("_", " ").title(), str(v)))
        st.dataframe(
            pd.DataFrame(tbl, columns=["Metric", "Value"]),
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.markdown("**Monthly Returns (%)**")
        try:
            mr = monthly_returns_table(returns) * 100
            try:
                styled = mr.style.format("{:.2f}").background_gradient(cmap="RdYlGn", axis=None)
                st.dataframe(styled, use_container_width=True)
            except (ImportError, AttributeError):
                st.dataframe(mr.round(2), use_container_width=True)
        except Exception as e:
            st.warning(f"Could not build monthly table: {e}")

    # Rolling Sharpe — Plotly
    st.markdown('<div class="section-title">Rolling 1-Year Sharpe</div>', unsafe_allow_html=True)
    roll = returns.rolling(252)
    rolling_sharpe = (roll.mean() * 252) / (roll.std() * (252**0.5))
    rs_clean = rolling_sharpe.dropna()

    fig_rs = make_fig(height=280)
    fig_rs.add_trace(
        go.Scatter(
            x=rs_clean.index,
            y=rs_clean.values,
            mode="lines",
            line=dict(color=COLORS["purple"], width=1.5),
            hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>",
        )
    )
    # Reference line at 1.0
    fig_rs.add_hline(
        y=1.0,
        line_dash="dash",
        line_color=COLORS["muted"],
        opacity=0.5,
        annotation_text="Sharpe = 1.0",
        annotation_position="bottom right",
        annotation_font_color=COLORS["muted"],
    )
    fig_rs.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
    st.plotly_chart(fig_rs, use_container_width=True)

    # Turnover
    turnover_path = run_dir / "turnover.csv"
    if turnover_path.exists():
        st.markdown('<div class="section-title">Turnover per Rebalance</div>', unsafe_allow_html=True)
        turnover = load_series(str(run_dir), "turnover.csv")
        if not turnover.empty:
            fig_tv = make_fig(height=250)
            fig_tv.add_trace(
                go.Bar(
                    x=turnover.index,
                    y=turnover.values,
                    marker_color=COLORS["orange"],
                    opacity=0.8,
                    hovertemplate="%{x|%Y-%m-%d}: %{y:.1%}<extra></extra>",
                )
            )
            fig_tv.update_layout(
                showlegend=False,
                xaxis_title="",
                yaxis_title="",
                yaxis_tickformat=".0%",
            )
            st.plotly_chart(fig_tv, use_container_width=True)
            st.caption(f"Average turnover: {turnover.mean():.1%}")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PORTFOLIO                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_port:
    st.markdown('<div class="section-title">Portfolio</div>', unsafe_allow_html=True)

    weights_path = run_dir / "weights.csv"
    if not weights_path.exists():
        st.info("No weights.csv in this run.")
    else:
        weights = load_frame(str(run_dir), "weights.csv")
        latest_date = weights.index.max()
        latest = weights.loc[latest_date]
        latest = latest[latest > 0].sort_values(ascending=False)
        latest.name = "weight"
        latest.index.name = "ticker"

        st.caption(f"As of {latest_date.date()}  |  {len(latest)} positions")

        c1, c2 = st.columns([1, 2])
        with c1:
            holdings = latest.to_frame("weight")
            holdings["Weight %"] = (holdings["weight"] * 100).round(2)
            st.dataframe(holdings[["Weight %"]], use_container_width=True)

        with c2:
            fig_pos = make_fig(height=400)
            sorted_latest = latest.sort_values(ascending=True)
            fig_pos.add_trace(
                go.Bar(
                    x=sorted_latest.values,
                    y=sorted_latest.index,
                    orientation="h",
                    marker_color=COLORS["blue"],
                    opacity=0.85,
                    hovertemplate="%{y}: %{x:.1%}<extra></extra>",
                )
            )
            fig_pos.update_layout(
                xaxis_title="Weight",
                yaxis_title="",
                xaxis_tickformat=".0%",
                showlegend=False,
            )
            st.plotly_chart(fig_pos, use_container_width=True)

        st.markdown('<div class="section-title">Position History</div>', unsafe_allow_html=True)
        active_names = weights.columns[(weights != 0).any(axis=0)]
        history = (weights[active_names] * 100).round(2)
        st.dataframe(history.tail(20), use_container_width=True)
        st.caption("Last 20 rebalance dates. Full data in weights.csv.")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  COMPARE RUNS                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_compare:
    st.markdown('<div class="section-title">Compare Runs</div>', unsafe_allow_html=True)

    picks = st.multiselect("Select runs", run_names, default=[selected])

    if not picks:
        st.info("Select at least one run above.")
    else:
        rows = []
        curves = {}
        for name in picks:
            rd = OUTPUTS_DIR / name
            try:
                s = load_summary(str(rd))
                s = dict(s)
                s["run"] = name
                rows.append(s)
                curves[name] = load_series(str(rd), "equity_curve.csv")
            except Exception as e:
                st.warning(f"Skipping {name}: {e}")

        if rows:
            df = pd.DataFrame(rows)
            col_order = [
                "run", "cagr", "annual_vol", "sharpe", "sortino",
                "max_drawdown", "calmar", "win_rate_monthly", "final_equity",
            ]
            df = df[[c for c in col_order if c in df.columns]]
            display_df = df.copy()
            pct_cols = ["cagr", "annual_vol", "max_drawdown", "win_rate_monthly"]
            num_cols = ["sharpe", "sortino", "calmar", "final_equity"]
            for c in pct_cols:
                if c in display_df.columns:
                    display_df[c] = display_df[c].apply(
                        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "--"
                    )
            for c in num_cols:
                if c in display_df.columns:
                    display_df[c] = display_df[c].apply(
                        lambda x: f"{x:.2f}" if pd.notna(x) else "--"
                    )
            # Clean up column names
            display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Plotly equity comparison
            st.markdown(
                '<div class="section-title">Equity Curves (Normalized)</div>',
                unsafe_allow_html=True,
            )
            aligned = pd.DataFrame(curves)
            aligned = aligned.apply(lambda s: s / s.dropna().iloc[0])

            trace_colors = [
                COLORS["blue"], COLORS["green"], COLORS["purple"],
                COLORS["orange"], COLORS["red"],
            ]
            fig_cmp = make_fig(height=400)
            for i, col in enumerate(aligned.columns):
                color = trace_colors[i % len(trace_colors)]
                fig_cmp.add_trace(
                    go.Scatter(
                        x=aligned.index,
                        y=aligned[col],
                        mode="lines",
                        name=col,
                        line=dict(color=color, width=2),
                        hovertemplate=f"{col}<br>%{{x|%Y-%m-%d}}: %{{y:.4f}}<extra></extra>",
                    )
                )
            fig_cmp.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="left",
                    x=0,
                    font=dict(size=11),
                ),
                xaxis_title="",
                yaxis_title="",
            )
            st.plotly_chart(fig_cmp, use_container_width=True)

        # Robustness CSVs
        rob_csvs = sorted(OUTPUTS_DIR.glob("robustness_comparison_*.csv"), reverse=True)
        if rob_csvs:
            st.markdown(
                '<div class="section-title">Robustness Comparisons</div>',
                unsafe_allow_html=True,
            )
            pick_rob = st.selectbox("Robustness CSV", [p.name for p in rob_csvs], index=0)
            rob_df = pd.read_csv(OUTPUTS_DIR / pick_rob)
            st.dataframe(rob_df, use_container_width=True, hide_index=True)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PAPER TRADING                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_paper:
    st.markdown('<div class="section-title">Paper Trading</div>', unsafe_allow_html=True)

    paper_strategies = []
    if PAPER_DIR.exists():
        paper_strategies = [
            p.name for p in PAPER_DIR.iterdir()
            if p.is_dir() and (p / "state.json").exists()
        ]

    if not paper_strategies:
        st.markdown(
            """
            <div class="info-banner">
                No paper trading strategies found. Start one from the CLI.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(
            "python main.py paper -c configs/smallcap_momentum_v2.yaml",
            language="bash",
        )
    else:
        paper_pick = st.selectbox("Strategy", sorted(paper_strategies), key="paper_strat")
        paper_dir = PAPER_DIR / paper_pick

        with open(paper_dir / "state.json") as f:
            pstate = json.load(f)

        # Metrics
        pc1, pc2, pc3, pc4, pc5 = st.columns(5)
        pc1.metric("Equity", fmt_num(pstate.get("equity"), 4))
        pc2.metric("Positions", str(len(pstate.get("holdings", {}))))
        pc3.metric("Cash Weight", fmt_pct(pstate.get("cash_weight", 0)))
        pc4.metric("Total Trades", str(pstate.get("trade_count", 0)))
        pc5.metric("Last Rebalance", pstate.get("last_rebalance", "never"))

        # Holdings
        holdings_dict = pstate.get("holdings", {})
        if holdings_dict:
            st.markdown(
                '<div class="section-title">Current Holdings</div>',
                unsafe_allow_html=True,
            )
            h_left, h_right = st.columns([1, 2])
            with h_left:
                h_df = pd.DataFrame([
                    {"Ticker": t, "Weight %": round(w * 100, 2)}
                    for t, w in sorted(holdings_dict.items(), key=lambda x: -x[1])
                ])
                st.dataframe(h_df, use_container_width=True, hide_index=True)
            with h_right:
                chart_s = pd.Series(holdings_dict).sort_values(ascending=True)
                fig_ph = make_fig(height=350)
                fig_ph.add_trace(
                    go.Bar(
                        x=chart_s.values,
                        y=chart_s.index,
                        orientation="h",
                        marker_color=COLORS["orange"],
                        opacity=0.85,
                        hovertemplate="%{y}: %{x:.1%}<extra></extra>",
                    )
                )
                fig_ph.update_layout(
                    xaxis_tickformat=".0%",
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title="",
                )
                st.plotly_chart(fig_ph, use_container_width=True)

        # Equity history
        eq_path = paper_dir / "equity.csv"
        if eq_path.exists():
            eq_df = pd.read_csv(eq_path)
            if not eq_df.empty:
                st.markdown(
                    '<div class="section-title">Equity History</div>',
                    unsafe_allow_html=True,
                )
                eq_df["date"] = pd.to_datetime(eq_df["date"])
                fig_peq = make_fig(height=280)
                fig_peq.add_trace(
                    go.Scatter(
                        x=eq_df["date"],
                        y=eq_df["equity"],
                        mode="lines",
                        line=dict(color=COLORS["green"], width=2),
                        fill="tozeroy",
                        fillcolor="rgba(63,185,80,0.05)",
                        hovertemplate="%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>",
                    )
                )
                fig_peq.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
                st.plotly_chart(fig_peq, use_container_width=True)

        # Trade log
        trades_path = paper_dir / "trades.csv"
        if trades_path.exists():
            trades_df = pd.read_csv(trades_path)
            if not trades_df.empty:
                st.markdown(
                    '<div class="section-title">Trade Log</div>',
                    unsafe_allow_html=True,
                )
                tc1, tc2, tc3 = st.columns(3)
                tc1.metric("Total Trades", str(len(trades_df)))
                tc2.metric("Buy Orders", str(len(trades_df[trades_df["side"] == "buy"])))
                tc3.metric("Sell Orders", str(len(trades_df[trades_df["side"] == "sell"])))

                rebal_dates = trades_df["date"].unique()
                st.caption(f"{len(rebal_dates)} rebalance(s)")
                st.dataframe(
                    trades_df.sort_values(["date", "ticker"], ascending=[False, True]),
                    use_container_width=True,
                    hide_index=True,
                )

        # Signals
        signals_path = paper_dir / "signals.csv"
        if signals_path.exists():
            with st.expander("Signal scores (latest rebalance)"):
                sig_df = pd.read_csv(signals_path)
                if not sig_df.empty:
                    latest_rebal = (
                        sig_df["rebalance_date"].iloc[-1]
                        if "rebalance_date" in sig_df.columns
                        else "unknown"
                    )
                    latest_sig = (
                        sig_df[sig_df["rebalance_date"] == latest_rebal]
                        if "rebalance_date" in sig_df.columns
                        else sig_df
                    )
                    latest_sig = latest_sig.sort_values("score", ascending=False)
                    st.caption(f"Rebalance date: {latest_rebal}")
                    st.dataframe(latest_sig.head(30), use_container_width=True, hide_index=True)

        # Gate comparison
        comp_path = paper_dir / "comparison.json"
        if comp_path.exists():
            st.markdown(
                '<div class="section-title">Paper vs Backtest Gate</div>',
                unsafe_allow_html=True,
            )
            with open(comp_path) as f:
                comp = json.load(f)

            gate_pass = comp.get("passes_gate", False)
            if gate_pass:
                st.success(
                    f"GATE: PASS - CAGR diff {comp.get('cagr_diff', 0):.2%} "
                    f"within +/-{comp.get('gate_threshold', 0.03):.0%}"
                )
            else:
                st.error(
                    f"GATE: FAIL - CAGR diff {comp.get('cagr_diff', 0):.2%} "
                    f"exceeds +/-{comp.get('gate_threshold', 0.03):.0%}"
                )

            gc1, gc2, gc3, gc4 = st.columns(4)
            gc1.metric("Paper CAGR", fmt_pct(comp.get("paper_cagr")))
            gc2.metric("Backtest CAGR", fmt_pct(comp.get("backtest_cagr")))
            gc3.metric("Tracking Error", fmt_pct(comp.get("tracking_error_annualized")))
            gc4.metric("Days Tracked", str(comp.get("days_tracked", 0)))

            days = comp.get("days_tracked", 0)
            if days < 90:
                st.warning(f"Only {days} days tracked. Need 90+ for graduation ({90 - days} more).")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  LIVE TRADING                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_live:
    st.markdown('<div class="section-title">Live Trading</div>', unsafe_allow_html=True)

    live_strategies = []
    if LIVE_DIR.exists():
        live_strategies = [
            p.name for p in LIVE_DIR.iterdir()
            if p.is_dir() and (p / "orders.csv").exists()
        ]

    if not live_strategies:
        st.markdown(
            """
            <div class="info-banner">
                No live trading history found. Run a live rebalance from the CLI.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(
            "python main.py live -c configs/smallcap_momentum_v2.yaml --capital 100000 --dry-run",
            language="bash",
        )
    else:
        live_pick = st.selectbox("Strategy", sorted(live_strategies), key="live_strat")
        live_dir = LIVE_DIR / live_pick

        orders_path = live_dir / "orders.csv"
        if orders_path.exists():
            orders_df = pd.read_csv(orders_path)
            if not orders_df.empty:
                st.markdown(
                    '<div class="section-title">Order History</div>',
                    unsafe_allow_html=True,
                )

                lc1, lc2, lc3, lc4 = st.columns(4)
                lc1.metric("Total Orders", str(len(orders_df)))
                placed = (
                    len(orders_df[orders_df["status"] == "placed"])
                    if "status" in orders_df.columns
                    else 0
                )
                failed = (
                    len(orders_df[orders_df["status"].str.startswith("failed")])
                    if "status" in orders_df.columns
                    else 0
                )
                lc2.metric("Placed", str(placed))
                lc3.metric("Failed", str(failed))
                total_value = (
                    orders_df["estimated_value"].sum()
                    if "estimated_value" in orders_df.columns
                    else 0
                )
                lc4.metric("Total Value", f"Rs. {total_value:,.0f}")

                st.dataframe(
                    orders_df.sort_values("timestamp", ascending=False)
                    if "timestamp" in orders_df.columns
                    else orders_df,
                    use_container_width=True,
                    hide_index=True,
                )

# ─── Footer ───────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <div class="dash-footer">
        Systematic Trading Dashboard &middot;
        Updated {datetime.now().strftime("%Y-%m-%d %H:%M")} &middot;
        Past performance does not guarantee future results
    </div>
    """,
    unsafe_allow_html=True,
)
