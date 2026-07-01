"""Strategy 1 — Smallcap Momentum."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dashboard_shared import (
    DATA_DIR,
    PAPER_DIR,
    apply_plotly_style,
    days_to_rebal,
    extend_returns_with_paper,
    inject_css,
    list_runs,
    load_series,
    load_summary,
    monthly_table,
    render_disclaimer,
    render_navbar,
)

st.set_page_config(page_title="Ascent — Momentum Strategy | JD Quant", page_icon="", layout="wide", initial_sidebar_state="collapsed")
inject_css()

# ─── Data ─────────────────────────────────────────────────────────────────────

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

render_navbar(active="ascent")

# ── Hero
st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">Strategy 1 &middot; Monthly Rebalance</div>
    <h1><span>Ascent</span></h1>
    <div class="tagline">
        Captures persistent price trends across Indian mid &amp; smallcaps.
        Pure price-based signal. Monthly rebalance, concentrated portfolio.
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
        <div class="val gold">{final_eq:.0f}x</div>
        <div class="lbl">Total Return</div>
    </div>
    <div class="stat-cell">
        <div class="val" style="color:var(--red)">{max_dd*100:.1f}%</div>
        <div class="lbl">Max Drawdown</div>
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
        extended = extend_returns_with_paper(returns, "smallcap_momentum_v2")
        mr = monthly_table(extended) * 100
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

    # Current Portfolio (hidden on public page — visible on /alpha)
    if False and paper_state and paper_state.get("holdings"):
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

    # Paper PnL — read latest equity from equity.csv (updated daily), not state.json (only on rebalance)
    if paper_state:
        eq_path = paper_dir / "equity.csv"
        if eq_path.exists():
            _eq_df = pd.read_csv(eq_path)
            dtrk = len(_eq_df)
            peq = _eq_df["equity"].iloc[-1] if not _eq_df.empty else 1.0
        else:
            dtrk = 0
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

render_disclaimer()
