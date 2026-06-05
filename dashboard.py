"""JD Quant — Quantitative Strategies Dashboard.

Run with:  streamlit run dashboard.py
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

st.set_page_config(page_title="JD Quant", page_icon="", layout="wide", initial_sidebar_state="collapsed")

# ─── Design System ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,300&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-primary: #06080d;
    --bg-secondary: #0d1117;
    --bg-card: #111820;
    --bg-card-hover: #151d28;
    --bg-elevated: #1a2332;
    --border: #1e2a3a;
    --border-subtle: #152030;
    --text-primary: #f0f4f8;
    --text-secondary: #94a3b8;
    --text-tertiary: #64748b;
    --accent: #3b82f6;
    --accent-dim: rgba(59,130,246,0.12);
    --green: #10b981;
    --green-dim: rgba(16,185,129,0.12);
    --red: #ef4444;
    --red-dim: rgba(239,68,68,0.12);
    --gold: #f59e0b;
    --gold-dim: rgba(245,158,11,0.10);
    --purple: #a78bfa;
    --purple-dim: rgba(167,139,250,0.10);
}

* { font-family: 'DM Sans', system-ui, -apple-system, sans-serif !important; }
code, .mono { font-family: 'JetBrains Mono', monospace !important; }

.stApp {
    background: var(--bg-primary);
    background-image:
        radial-gradient(ellipse 80% 60% at 50% -20%, rgba(59,130,246,0.04) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 110%, rgba(16,185,129,0.03) 0%, transparent 50%);
}

[data-testid="stSidebar"] { display: none; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; max-width: 1280px; }

/* ── Navigation Bar ─────────────────────── */
.navbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0 2rem 0;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 2.5rem;
}
.navbar .logo {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.03em;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}
.navbar .logo-mark {
    width: 28px; height: 28px;
    background: linear-gradient(135deg, var(--accent) 0%, #8b5cf6 100%);
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.75rem; color: white;
}
.navbar .nav-status {
    display: flex; align-items: center; gap: 0.5rem;
    color: var(--text-tertiary); font-size: 0.78rem; font-weight: 500;
}
.navbar .live-dot {
    width: 6px; height: 6px; border-radius: 50%; background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: pulse-dot 2.5s ease-in-out infinite;
}
@keyframes pulse-dot { 0%,100% { opacity:1; } 50% { opacity:0.3; } }

/* ── Hero ───────────────────────────────── */
.hero-v2 {
    padding: 0 0 2.5rem 0;
    position: relative;
}
.hero-v2 .eyebrow {
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin-bottom: 0.8rem;
}
.hero-v2 h1 {
    font-size: 3rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.04em;
    line-height: 1.05;
    margin: 0 0 0.8rem 0;
}
.hero-v2 h1 span {
    background: linear-gradient(135deg, var(--accent) 0%, #a78bfa 50%, var(--green) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-v2 .tagline {
    color: var(--text-secondary);
    font-size: 1.05rem;
    line-height: 1.6;
    max-width: 600px;
}

/* ── Stat Row ───────────────────────────── */
.stat-row {
    display: flex; gap: 1px;
    background: var(--border);
    border-radius: 14px;
    overflow: hidden;
    margin: 2rem 0;
}
.stat-cell {
    flex: 1;
    background: var(--bg-card);
    padding: 1.4rem 1.6rem;
    text-align: center;
    transition: background 0.2s;
}
.stat-cell:hover { background: var(--bg-card-hover); }
.stat-cell .val {
    font-size: 1.7rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.1;
}
.stat-cell .val.green { color: var(--green); }
.stat-cell .val.accent { color: var(--accent); }
.stat-cell .val.gold { color: var(--gold); }
.stat-cell .val.purple { color: var(--purple); }
.stat-cell .lbl {
    color: var(--text-tertiary);
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.35rem;
}

/* ── Card ───────────────────────────────── */
.card-v2 {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.2rem;
    transition: border-color 0.2s;
}
.card-v2:hover { border-color: #2a3a4e; }
.card-v2 .card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 1rem;
}
.card-v2 .card-title {
    font-size: 0.85rem; font-weight: 600; color: var(--text-primary);
    letter-spacing: -0.01em;
}
.card-v2 .card-badge {
    font-size: 0.65rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; padding: 0.2rem 0.6rem; border-radius: 6px;
}
.card-v2 .card-desc {
    color: var(--text-tertiary); font-size: 0.78rem; line-height: 1.5;
    margin-bottom: 1rem;
}

/* ── Holdings Table ─────────────────────── */
.htable { width: 100%; border-collapse: collapse; }
.htable th {
    text-align: left; color: var(--text-tertiary);
    font-size: 0.62rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; padding: 0 0.6rem 0.6rem;
    border-bottom: 1px solid var(--border);
}
.htable td {
    padding: 0.55rem 0.6rem;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 0.82rem; color: var(--text-primary);
}
.htable tr:last-child td { border-bottom: none; }
.htable .sym { font-weight: 600; letter-spacing: 0.02em; }
.htable .wt { color: var(--accent); font-weight: 600; font-family: 'JetBrains Mono', monospace !important; }
.htable .idx { color: var(--text-tertiary); font-size: 0.72rem; }

/* ── Process Steps ──────────────────────── */
.process { display: flex; flex-direction: column; gap: 0.8rem; }
.proc-step {
    display: flex; align-items: flex-start; gap: 0.9rem;
    padding: 0.8rem 1rem;
    border-radius: 10px;
    border: 1px solid transparent;
    transition: all 0.2s;
}
.proc-step:hover { background: var(--bg-elevated); border-color: var(--border); }
.proc-step .num {
    min-width: 26px; height: 26px; border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.7rem;
    background: var(--accent-dim); color: var(--accent);
}
.proc-step .txt { font-size: 0.82rem; line-height: 1.5; }
.proc-step .txt strong { color: var(--text-primary); }
.proc-step .txt span { color: var(--text-tertiary); }

/* ── Countdown ──────────────────────────── */
.cdown {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1.8rem;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.cdown::before {
    content: ''; position: absolute; inset: 0;
    background: radial-gradient(circle at 50% 0%, var(--purple-dim) 0%, transparent 60%);
    pointer-events: none;
}
.cdown .big { font-size: 3rem; font-weight: 700; color: var(--purple); line-height: 1; }
.cdown .sub {
    color: var(--text-tertiary); font-size: 0.68rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.4rem;
}

/* ── Key Stats Table ────────────────────── */
.kstats { width: 100%; border-collapse: collapse; }
.kstats td {
    padding: 0.5rem 0; font-size: 0.8rem;
    border-bottom: 1px solid var(--border-subtle);
}
.kstats td:first-child { color: var(--text-secondary); }
.kstats td:last-child { text-align: right; font-weight: 600; color: var(--text-primary); }
.kstats tr:last-child td { border-bottom: none; }

/* ── Paper PnL ──────────────────────────── */
.pnl {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: center;
}
.pnl .big { font-size: 1.8rem; font-weight: 700; }
.pnl .big.up { color: var(--green); }
.pnl .big.dn { color: var(--red); }
.pnl .sub {
    color: var(--text-tertiary); font-size: 0.65rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.2rem;
}

/* ── Disclaimer ─────────────────────────── */
.disc {
    margin-top: 3rem;
    padding: 1rem 1.4rem;
    border-radius: 10px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-secondary);
    color: var(--text-tertiary);
    font-size: 0.7rem;
    line-height: 1.6;
}

/* ── Streamlit Overrides ────────────────── */
div[data-testid="stMetric"] {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 0.8rem 1rem;
}
div[data-testid="stMetric"] label {
    color: var(--text-tertiary) !important; font-size: 0.65rem !important;
    text-transform: uppercase; letter-spacing: 0.08em;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.2rem !important; font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Plotly Config ─────────────────────────────────────────────────────────────

def apply_plotly_style(fig, **kw):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, system-ui, sans-serif", color="#94a3b8", size=11),
        margin=dict(l=40, r=20, t=20, b=40),
        hoverlabel=dict(bgcolor="#111820", font_size=12, bordercolor="#1e2a3a"),
        **kw,
    )
    fig.update_xaxes(gridcolor="#1e2a3a", linecolor="#1e2a3a", zeroline=False)
    fig.update_yaxes(gridcolor="#1e2a3a", linecolor="#1e2a3a", zeroline=False)
    return fig

# ─── Helpers ───────────────────────────────────────────────────────────────────

def list_runs():
    if not OUTPUTS_DIR.exists(): return []
    return sorted(
        [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and (p / "summary.json").exists()],
        key=lambda p: p.name, reverse=True,
    )

@st.cache_data(show_spinner=False)
def load_summary(d): return json.loads((Path(d) / "summary.json").read_text())

@st.cache_data(show_spinner=False)
def load_series(d, n): return pd.read_csv(Path(d) / n, index_col=0, parse_dates=True).iloc[:, 0]

def days_to_rebal():
    t = date.today()
    _, ld = monthrange(t.year, t.month)
    return max(0, (date(t.year, t.month, ld) - t).days)

def monthly_table(rets):
    m = (1 + rets).resample("ME").prod() - 1
    t = m.to_frame("r")
    t["y"], t["m"] = t.index.year, t.index.month
    p = t.pivot(index="y", columns="m", values="r").sort_index(ascending=False)
    p.columns = [pd.Timestamp(2000, int(c), 1).strftime("%b") for c in p.columns]
    return p

# ─── Data ──────────────────────────────────────────────────────────────────────

runs = list_runs()
primary_run = next((r for r in runs if "smallcap_momentum_v2" in r.name and "smoke" not in r.name), runs[0] if runs else None)
if not primary_run:
    st.error("No backtest data.")
    st.stop()

summary = load_summary(str(primary_run))
equity = load_series(str(primary_run), "equity_curve.csv")
returns = load_series(str(primary_run), "returns.csv")

paper_state = None
paper_dir = PAPER_DIR / "smallcap_momentum_v2"
if (paper_dir / "state.json").exists():
    paper_state = json.loads((paper_dir / "state.json").read_text())

cagr = summary.get("cagr", 0)
sharpe = summary.get("sharpe", 0)
max_dd = summary.get("max_drawdown", 0)
final_eq = summary.get("final_equity", 1)
win_rate = summary.get("win_rate_monthly", 0)
vol = summary.get("annual_vol", 0)
sortino = summary.get("sortino", 0)

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER
# ═══════════════════════════════════════════════════════════════════════════════

# ── Navbar
st.markdown(f"""
<div class="navbar">
    <div class="logo">
        <div class="logo-mark">JD</div>
        JD Quant
    </div>
    <div class="nav-status">
        <div class="live-dot"></div>
        Strategy Active &middot; Updated {datetime.now().strftime("%d %b %Y")}
    </div>
</div>
""", unsafe_allow_html=True)

# ── Hero
st.markdown(f"""
<div class="hero-v2">
    <div class="eyebrow">Quantitative Strategies</div>
    <h1>Systematic edge<br>in <span>Indian equities</span></h1>
    <div class="tagline">
        A proprietary quantitative strategy that systematically identifies
        high-conviction opportunities. Fully automated, rules-based, zero discretion.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Stats Bar
st.markdown(f"""
<div class="stat-row">
    <div class="stat-cell">
        <div class="val green">{cagr*100:.1f}%</div>
        <div class="lbl">CAGR</div>
    </div>
    <div class="stat-cell">
        <div class="val accent">{sharpe:.2f}</div>
        <div class="lbl">Sharpe Ratio</div>
    </div>
    <div class="stat-cell">
        <div class="val gold">{final_eq:.0f}x</div>
        <div class="lbl">Total Return</div>
    </div>
    <div class="stat-cell">
        <div class="val purple">{win_rate*100:.0f}%</div>
        <div class="lbl">Win Rate</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Two Columns
col_l, col_r = st.columns([3, 2], gap="large")

with col_l:
    # Equity Curve
    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Performance</div>
            <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Backtest</div>
        </div>
        <div class="card-desc">Growth of Rs. 1 from 2010. Log scale.</div>
    </div>
    """, unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity.index, y=equity.values, mode="lines",
        line=dict(color="#3b82f6", width=2),
        fill="tozeroy", fillcolor="rgba(59,130,246,0.04)",
        hovertemplate="%{x|%b %Y}: Rs. %{y:.2f}<extra></extra>",
    ))
    apply_plotly_style(fig, height=340, showlegend=False, yaxis_type="log", yaxis_tickprefix="Rs. ")
    st.plotly_chart(fig, use_container_width=True)

    # Drawdown
    st.markdown(f"""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Drawdown</div>
            <div class="card-badge" style="background:var(--red-dim);color:var(--red);">Max {max_dd*100:.1f}%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    peak = equity.cummax()
    dd = equity / peak - 1
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=dd.index, y=dd.values, mode="lines",
        line=dict(color="#ef4444", width=1.5),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.08)",
        hovertemplate="%{x|%b %Y}: %{y:.1%}<extra></extra>",
    ))
    apply_plotly_style(fig_dd, height=200, showlegend=False, yaxis_tickformat=".0%")
    st.plotly_chart(fig_dd, use_container_width=True)

    # Monthly Heatmap
    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Monthly Returns</div>
            <div class="card-badge" style="background:var(--accent-dim);color:var(--accent);">%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        mr = monthly_table(returns) * 100
        years = [str(y) for y in mr.index.tolist()]
        months = mr.columns.tolist()

        fig_hm = go.Figure()
        fig_hm.add_trace(go.Heatmap(
            z=mr.values, x=months, y=years,
            colorscale=[[0,"#991b1b"],[0.35,"#450a0a"],[0.5,"#0d1117"],[0.65,"#052e16"],[1,"#166534"]],
            zmid=0, showscale=False,
            hovertemplate="%{y} %{x}: %{z:.1f}%<extra></extra>",
            xgap=2, ygap=2,
        ))
        for i, yr in enumerate(years):
            for j, mo in enumerate(months):
                v = mr.values[i][j]
                if pd.notna(v):
                    fig_hm.add_annotation(x=mo, y=yr, text=f"{v:.1f}", showarrow=False,
                                          font=dict(size=9, color="#e2e8f0"))
        fig_hm.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Sans, sans-serif", color="#94a3b8", size=11),
            margin=dict(l=50, r=20, t=30, b=10),
            height=max(420, len(mr) * 28),
        )
        fig_hm.update_xaxes(side="top", dtick=1, tickfont=dict(size=10),
                            gridcolor="rgba(0,0,0,0)", linecolor="rgba(0,0,0,0)", zeroline=False)
        fig_hm.update_yaxes(autorange="reversed", dtick=1, tickfont=dict(size=10),
                            gridcolor="rgba(0,0,0,0)", linecolor="rgba(0,0,0,0)", zeroline=False)
        st.plotly_chart(fig_hm, use_container_width=True)
    except Exception as e:
        st.warning(f"Heatmap error: {e}")

with col_r:
    # Countdown
    dl = days_to_rebal()
    st.markdown(f"""
    <div class="cdown">
        <div class="big">{dl}</div>
        <div class="sub">Days to next rebalance</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")

    # Current Portfolio
    if paper_state and paper_state.get("holdings"):
        holdings = paper_state["holdings"]
        last_r = paper_state.get("last_rebalance", "-")
        sh = sorted(holdings.items(), key=lambda x: -x[1])

        rows = "".join(
            f'<tr><td class="idx">{i}</td><td class="sym">{t}</td><td class="wt">{w*100:.1f}%</td></tr>'
            for i, (t, w) in enumerate(sh, 1)
        )
        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Current Portfolio</div>
                <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Active</div>
            </div>
            <div class="card-desc">Last rebalanced {last_r} &middot; {len(holdings)} positions &middot; Equal weight</div>
            <table class="htable">
                <thead><tr><th>#</th><th>Ticker</th><th>Weight</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """, unsafe_allow_html=True)

    # How it works
    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Process</div>
        </div>
        <div class="process">
            <div class="proc-step">
                <div class="num">1</div>
                <div class="txt"><strong>Screen</strong><br><span>Filter Indian equities through proprietary quantitative criteria.</span></div>
            </div>
            <div class="proc-step">
                <div class="num">2</div>
                <div class="txt"><strong>Score</strong><br><span>Multi-factor model capturing persistent market anomalies.</span></div>
            </div>
            <div class="proc-step">
                <div class="num">3</div>
                <div class="txt"><strong>Construct</strong><br><span>Equal-weight portfolio. Diversified, disciplined.</span></div>
            </div>
            <div class="proc-step">
                <div class="num">4</div>
                <div class="txt"><strong>Rebalance</strong><br><span>Fixed schedule. No emotions, no overrides.</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Key Numbers
    st.markdown(f"""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Key Numbers</div>
        </div>
        <table class="kstats">
            <tr><td>Annual return</td><td style="color:var(--green)">{cagr*100:.1f}%</td></tr>
            <tr><td>Volatility</td><td>{vol*100:.1f}%</td></tr>
            <tr><td>Sharpe</td><td>{sharpe:.2f}</td></tr>
            <tr><td>Sortino</td><td>{sortino:.2f}</td></tr>
            <tr><td>Max drawdown</td><td style="color:var(--red)">{max_dd*100:.1f}%</td></tr>
            <tr><td>Recovery</td><td style="color:var(--text-tertiary)">~26 months</td></tr>
            <tr><td>Win rate</td><td>{win_rate*100:.0f}%</td></tr>
            <tr><td>Track record</td><td style="color:var(--text-tertiary)">16 years</td></tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    # Paper PnL
    if paper_state:
        eq_path = paper_dir / "equity.csv"
        dtrk = len(pd.read_csv(eq_path)) if eq_path.exists() else 0
        peq = paper_state.get("equity", 1.0)
        ppnl = (peq - 1.0) * 100
        cls = "up" if ppnl >= 0 else "dn"
        sgn = "+" if ppnl >= 0 else ""

        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Paper Trading</div>
                <div class="card-badge" style="background:var(--gold-dim);color:var(--gold);">Simulation</div>
            </div>
            <div class="card-desc">Running since {paper_state.get('created','')[:10]}. {dtrk} days tracked.</div>
            <div class="pnl">
                <div class="big {cls}">{sgn}{ppnl:.2f}%</div>
                <div class="sub">Paper P&amp;L</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 2 — VALUE + QUALITY
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("")

st.markdown("""
<div class="navbar" style="margin-top:1rem;padding-top:2rem;">
    <div class="logo" style="font-size:1rem;">Strategy 2</div>
    <div class="nav-status">Quarterly rebalance</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero-v2" style="padding-bottom:1.5rem;">
    <div class="eyebrow">Fundamental Analysis</div>
    <h1 style="font-size:2rem;">Value + <span>Quality</span></h1>
    <div class="tagline" style="font-size:0.9rem;">
        Buys cheap, high-quality stocks — low P/E, high ROE, low debt, growing earnings.
        Designed to complement the momentum strategy with uncorrelated returns.
    </div>
</div>
""", unsafe_allow_html=True)

# Load V+Q backtest data
vq_runs = [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and "value_quality" in p.name and (p / "summary.json").exists()] if OUTPUTS_DIR.exists() else []
vq_run = sorted(vq_runs, key=lambda p: p.name, reverse=True)[0] if vq_runs else None

vq_summary = vq_equity = vq_returns = None
if vq_run:
    vq_summary = load_summary(str(vq_run))
    try:
        vq_equity = load_series(str(vq_run), "equity_curve.csv")
        vq_returns = load_series(str(vq_run), "returns.csv")
    except Exception:
        pass

# V+Q Stats Bar
if vq_summary:
    vq_cagr = vq_summary.get("cagr", 0)
    vq_sharpe = vq_summary.get("sharpe", 0)
    vq_max_dd = vq_summary.get("max_drawdown", 0)
    vq_win_rate = vq_summary.get("win_rate_monthly", 0)
    vq_vol = vq_summary.get("annual_vol", 0)
    vq_sortino = vq_summary.get("sortino", 0)
    vq_final_eq = vq_summary.get("final_equity", 1)

    cagr_color = "green" if vq_cagr >= 0 else "red"
    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-cell">
            <div class="val" style="color:var(--{cagr_color})">{vq_cagr*100:.1f}%</div>
            <div class="lbl">CAGR</div>
        </div>
        <div class="stat-cell">
            <div class="val accent">{vq_sharpe:.2f}</div>
            <div class="lbl">Sharpe Ratio</div>
        </div>
        <div class="stat-cell">
            <div class="val" style="color:var(--red)">{vq_max_dd*100:.1f}%</div>
            <div class="lbl">Max Drawdown</div>
        </div>
        <div class="stat-cell">
            <div class="val purple">{vq_win_rate*100:.0f}%</div>
            <div class="lbl">Win Rate</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Fetch V+Q scores (cached for 6 hours)
from trading.data.universe import smallcap_universe  # noqa: E402
from trading.signals.value_quality import fetch_fundamentals, score_value_quality  # noqa: E402

@st.cache_data(ttl=6*3600, show_spinner="Scoring stocks on fundamentals...")
def get_vq_data():
    tickers = smallcap_universe()
    fund = fetch_fundamentals(tickers, max_workers=15)
    scores = score_value_quality(fund)
    return fund, scores

try:
    vq_fund, vq_scores = get_vq_data()

    if not vq_scores.empty:
        top_15 = vq_scores.head(15)

        vq_l, vq_r = st.columns([3, 2], gap="large")

        with vq_l:
            # V+Q Equity Curve
            if vq_equity is not None:
                st.markdown("""
                <div class="card-v2">
                    <div class="card-header">
                        <div class="card-title">Performance</div>
                        <div class="card-badge" style="background:var(--purple-dim);color:var(--purple);">Backtest</div>
                    </div>
                    <div class="card-desc">Growth of Rs. 1. Quarterly rebalance, top 15 equal weight.</div>
                </div>
                """, unsafe_allow_html=True)

                fig_vq = go.Figure()
                fig_vq.add_trace(go.Scatter(
                    x=vq_equity.index, y=vq_equity.values, mode="lines",
                    line=dict(color="#a78bfa", width=2),
                    fill="tozeroy", fillcolor="rgba(167,139,250,0.06)",
                    hovertemplate="%{x|%b %Y}: Rs. %{y:.3f}<extra></extra>",
                ))
                apply_plotly_style(fig_vq, height=280, showlegend=False, yaxis_tickprefix="Rs. ")
                st.plotly_chart(fig_vq, use_container_width=True)

            # V+Q Drawdown
            if vq_equity is not None:
                vq_peak = vq_equity.cummax()
                vq_dd = vq_equity / vq_peak - 1
                st.markdown(f"""
                <div class="card-v2">
                    <div class="card-header">
                        <div class="card-title">Drawdown</div>
                        <div class="card-badge" style="background:var(--red-dim);color:var(--red);">Max {vq_max_dd*100:.1f}%</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                fig_vq_dd = go.Figure()
                fig_vq_dd.add_trace(go.Scatter(
                    x=vq_dd.index, y=vq_dd.values, mode="lines",
                    line=dict(color="#ef4444", width=1.5),
                    fill="tozeroy", fillcolor="rgba(239,68,68,0.08)",
                    hovertemplate="%{x|%b %Y}: %{y:.1%}<extra></extra>",
                ))
                apply_plotly_style(fig_vq_dd, height=180, showlegend=False, yaxis_tickformat=".0%")
                st.plotly_chart(fig_vq_dd, use_container_width=True)

            # V+Q Portfolio table
            vq_rows = ""
            for i, (ticker, score) in enumerate(top_15.items(), 1):
                row = vq_fund.loc[ticker]
                pe = row.get("pe", 0)
                roe = row.get("roe", 0) * 100
                de = row.get("de", 0)
                eg = row.get("earnings_growth", 0) * 100
                eg_color = "var(--green)" if eg > 0 else "var(--red)"
                vq_rows += (
                    f'<tr>'
                    f'<td class="idx">{i}</td>'
                    f'<td class="sym">{ticker}</td>'
                    f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:var(--text-secondary)">{pe:.1f}</td>'
                    f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:var(--green)">{roe:.1f}%</td>'
                    f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:var(--text-secondary)">{de:.1f}</td>'
                    f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:{eg_color}">{eg:+.0f}%</td>'
                    f'<td class="wt">{score:.3f}</td>'
                    f'</tr>'
                )

            st.markdown(f"""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">Value + Quality Picks</div>
                    <div class="card-badge" style="background:var(--purple-dim);color:var(--purple);">Top 15</div>
                </div>
                <div class="card-desc">Ranked by composite score: Earnings Yield + ROE + Low Debt + Earnings Growth. Updated live.</div>
                <table class="htable">
                    <thead><tr><th>#</th><th>Ticker</th><th>P/E</th><th>ROE</th><th>D/E</th><th>EPS Gr.</th><th>Score</th></tr></thead>
                    <tbody>{vq_rows}</tbody>
                </table>
            </div>
            """, unsafe_allow_html=True)

        with vq_r:
            # Overlap analysis
            momentum_holdings = set(paper_state.get("holdings", {}).keys()) if paper_state else set()
            vq_holdings = set(top_15.index)
            overlap = momentum_holdings & vq_holdings
            only_momentum = momentum_holdings - vq_holdings
            only_vq = vq_holdings - momentum_holdings

            st.markdown(f"""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">Strategy Overlap</div>
                </div>
                <div class="card-desc">Stocks appearing in both strategies have the strongest conviction.</div>
                <table class="kstats">
                    <tr><td>Momentum-only stocks</td><td>{len(only_momentum)}</td></tr>
                    <tr><td>Value+Quality-only stocks</td><td>{len(only_vq)}</td></tr>
                    <tr><td>Both strategies</td><td style="color:var(--green)">{len(overlap)}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            if overlap:
                overlap_list = ", ".join(sorted(overlap))
                st.markdown(f"""
                <div class="card-v2">
                    <div class="card-header">
                        <div class="card-title">High Conviction</div>
                        <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Both Signals</div>
                    </div>
                    <div class="card-desc">These stocks rank highly on BOTH momentum and fundamentals:</div>
                    <div style="color:var(--text-primary);font-weight:600;font-size:0.95rem;line-height:1.8;">
                        {overlap_list}
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # V+Q Key Numbers
            if vq_summary:
                st.markdown(f"""
                <div class="card-v2">
                    <div class="card-header">
                        <div class="card-title">Key Numbers</div>
                        <div class="card-badge" style="background:var(--purple-dim);color:var(--purple);">Backtest</div>
                    </div>
                    <table class="kstats">
                        <tr><td>Period</td><td style="color:var(--text-tertiary)">{vq_summary.get('start_date','')[:7]} — {vq_summary.get('end_date','')[:7]}</td></tr>
                        <tr><td>Annual return</td><td style="color:{'var(--green)' if vq_cagr>=0 else 'var(--red)'}">{vq_cagr*100:.1f}%</td></tr>
                        <tr><td>Volatility</td><td>{vq_vol*100:.1f}%</td></tr>
                        <tr><td>Sharpe</td><td>{vq_sharpe:.2f}</td></tr>
                        <tr><td>Sortino</td><td>{vq_sortino:.2f}</td></tr>
                        <tr><td>Max drawdown</td><td style="color:var(--red)">{vq_max_dd*100:.1f}%</td></tr>
                        <tr><td>Win rate</td><td>{vq_win_rate*100:.0f}%</td></tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)

            # V+Q Process
            st.markdown("""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">How It Works</div>
                </div>
                <div class="process">
                    <div class="proc-step">
                        <div class="num" style="background:var(--purple-dim);color:var(--purple);">1</div>
                        <div class="txt"><strong>Earnings Yield</strong><br><span>Inverse of P/E. Cheaper stocks score higher.</span></div>
                    </div>
                    <div class="proc-step">
                        <div class="num" style="background:var(--purple-dim);color:var(--purple);">2</div>
                        <div class="txt"><strong>Return on Equity</strong><br><span>Higher ROE = better capital efficiency.</span></div>
                    </div>
                    <div class="proc-step">
                        <div class="num" style="background:var(--purple-dim);color:var(--purple);">3</div>
                        <div class="txt"><strong>Low Debt</strong><br><span>Lower debt/equity = safer balance sheet.</span></div>
                    </div>
                    <div class="proc-step">
                        <div class="num" style="background:var(--purple-dim);color:var(--purple);">4</div>
                        <div class="txt"><strong>Earnings Growth</strong><br><span>Growing profits confirm the value isn't a trap.</span></div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

except Exception as e:
    st.warning(f"Value+Quality data unavailable: {e}")

# ── Disclaimer
st.markdown("""
<div class="disc">
    <strong>Disclaimer:</strong> This is not financial advice. Past performance does not guarantee future results.
    The strategy shown is based on historical backtesting which has inherent limitations including
    survivorship bias. Always do your own research before investing.
</div>
""", unsafe_allow_html=True)
