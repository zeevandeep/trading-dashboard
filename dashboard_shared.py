"""Shared styles, helpers, and config for the multi-page dashboard."""

from __future__ import annotations

import json
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from trading.config import DATA_DIR, OUTPUTS_DIR  # noqa: E402

PAPER_DIR = DATA_DIR / "paper"

# ─── CSS Design System ───────────────────────────────────────────────────────

SHARED_CSS = """
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
.navbar .nav-links {
    display: flex; align-items: center; gap: 1.5rem;
}
.navbar .nav-links a {
    color: var(--text-secondary); text-decoration: none;
    font-size: 0.82rem; font-weight: 500;
    transition: color 0.2s;
}
.navbar .nav-links a:hover { color: var(--text-primary); }
.navbar .nav-links a.active { color: var(--accent); }
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

/* ── Strategy Card (Home) ──────────────── */
.strat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 2rem 2.2rem;
    transition: all 0.3s;
    cursor: pointer;
    position: relative;
    overflow: hidden;
}
.strat-card:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.3);
}
.strat-card .strat-num {
    font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; margin-bottom: 0.8rem;
}
.strat-card .strat-name {
    font-size: 1.4rem; font-weight: 700; color: var(--text-primary);
    letter-spacing: -0.02em; margin-bottom: 0.5rem;
}
.strat-card .strat-desc {
    color: var(--text-tertiary); font-size: 0.82rem; line-height: 1.5;
    margin-bottom: 1.5rem;
}
.strat-card .strat-stats {
    display: flex; gap: 1.5rem;
}
.strat-card .strat-stat .val {
    font-size: 1.3rem; font-weight: 700; line-height: 1.1;
}
.strat-card .strat-stat .lbl {
    color: var(--text-tertiary); font-size: 0.6rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.2rem;
}
.strat-card .strat-cta {
    margin-top: 1.4rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: var(--accent);
    font-size: 0.82rem;
    font-weight: 600;
    text-align: center;
    transition: color 0.2s;
}
.strat-card:hover .strat-cta {
    color: var(--text-primary);
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
"""


def inject_css():
    st.markdown(SHARED_CSS, unsafe_allow_html=True)


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


# ─── Data Helpers ─────────────────────────────────────────────────────────────

def list_runs():
    if not OUTPUTS_DIR.exists():
        return []
    return sorted(
        [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and (p / "summary.json").exists()],
        key=lambda p: p.name, reverse=True,
    )


@st.cache_data(show_spinner=False)
def load_summary(d):
    return json.loads((Path(d) / "summary.json").read_text())


@st.cache_data(show_spinner=False)
def load_series(d, n):
    return pd.read_csv(Path(d) / n, index_col=0, parse_dates=True).iloc[:, 0]


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


def render_navbar(active: str = ""):
    """Render the site-wide navbar with navigation links.

    active: one of "home", "ascent", "bedrock", "portfolio", "about"
    """
    from datetime import datetime as _dt

    def _cls(page):
        return ' class="active"' if page == active else ""

    st.markdown(f"""
    <div class="navbar">
        <a href="/" target="_self" style="text-decoration:none;color:inherit;">
        <div class="logo">
            <div class="logo-mark">JD</div>
            JD Quant
        </div>
        </a>
        <div class="nav-links">
            <a href="/About"{_cls("about")}>About</a>
            <a href="/Portfolio"{_cls("strategies")}>Strategies</a>
        </div>
        <div class="nav-status">
            <div class="live-dot"></div>
            {_dt.now().strftime("%d %b %Y")}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_disclaimer():
    st.markdown("""
    <div class="disc">
        <strong>Disclaimer:</strong> This is not financial advice. Past performance does not guarantee future results.
        The strategy shown is based on historical backtesting which has inherent limitations including
        survivorship bias. Always do your own research before investing.
    </div>
    """, unsafe_allow_html=True)
