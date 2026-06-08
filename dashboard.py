"""JD Quant — Home Page.

Run with:  streamlit run dashboard.py
"""

from __future__ import annotations

import streamlit as st

from dashboard_shared import (
    OUTPUTS_DIR,
    inject_css,
    list_runs,
    load_summary,
    render_navbar,
)

st.set_page_config(page_title="JD Quant", page_icon="", layout="wide", initial_sidebar_state="collapsed")
inject_css()

# ─── Load strategy summaries ─────────────────────────────────────────────────

runs = list_runs()

# Strategy 1: Momentum
mom_run = next((r for r in runs if "smallcap_momentum_v2" in r.name and "smoke" not in r.name), None)
mom = load_summary(str(mom_run)) if mom_run else {}

# Strategy 2: Value + Quality
vq_runs = [r for r in runs if "value_quality" in r.name]
vq_run = vq_runs[0] if vq_runs else None
vq = load_summary(str(vq_run)) if vq_run else {}

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER
# ═══════════════════════════════════════════════════════════════════════════════

render_navbar(active="home")

# ── Hero
st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">Quantitative Strategies</div>
    <h1>Systematic edge<br>in <span>Indian equities</span></h1>
    <div class="tagline">
        Two proprietary quantitative strategies that systematically identify
        high-conviction opportunities. Fully automated, rules-based, zero discretion.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Strategy Cards
col1, col2 = st.columns(2, gap="large")

with col1:
    m_cagr = mom.get("cagr", 0) * 100
    m_ret = mom.get("final_equity", 1)
    m_dd = mom.get("max_drawdown", 0) * 100
    m_wr = mom.get("win_rate_monthly", 0) * 100

    st.markdown(f"""
    <a href="/Momentum" target="_self" style="text-decoration:none;color:inherit;display:block;">
    <div class="strat-card">
        <div class="strat-num" style="color:var(--accent);">Strategy 1</div>
        <div class="strat-name">Ascent</div>
        <div class="strat-desc">
            Captures persistent price trends across Indian mid &amp; smallcaps.
            Monthly rebalance, concentrated portfolio. Pure price-based signal.
        </div>
        <div class="strat-stats">
            <div class="strat-stat">
                <div class="val" style="color:var(--green)">{m_cagr:.1f}%</div>
                <div class="lbl">CAGR</div>
            </div>
            <div class="strat-stat">
                <div class="val" style="color:var(--gold)">{m_ret:.0f}x</div>
                <div class="lbl">Total Return</div>
            </div>
            <div class="strat-stat">
                <div class="val" style="color:var(--red)">{m_dd:.1f}%</div>
                <div class="lbl">Max DD</div>
            </div>
            <div class="strat-stat">
                <div class="val" style="color:var(--purple)">{m_wr:.0f}%</div>
                <div class="lbl">Win Rate</div>
            </div>
        </div>
        <div class="strat-cta">View Ascent Strategy &rarr;</div>
    </div>
    </a>
    """, unsafe_allow_html=True)

with col2:
    v_cagr = vq.get("cagr", 0) * 100
    v_ret = vq.get("final_equity", 1)
    v_dd = vq.get("max_drawdown", 0) * 100
    v_wr = vq.get("win_rate_monthly", 0) * 100

    st.markdown(f"""
    <a href="/Value_Quality" target="_self" style="text-decoration:none;color:inherit;display:block;">
    <div class="strat-card">
        <div class="strat-num" style="color:var(--purple);">Strategy 2</div>
        <div class="strat-name">Bedrock</div>
        <div class="strat-desc">
            Identifies undervalued, high-quality businesses with strong fundamentals.
            Quarterly rebalance, concentrated portfolio. Multi-factor scoring.
        </div>
        <div class="strat-stats">
            <div class="strat-stat">
                <div class="val" style="color:var(--green)">{v_cagr:.1f}%</div>
                <div class="lbl">CAGR</div>
            </div>
            <div class="strat-stat">
                <div class="val" style="color:var(--gold)">{v_ret:.0f}x</div>
                <div class="lbl">Total Return</div>
            </div>
            <div class="strat-stat">
                <div class="val" style="color:var(--red)">{v_dd:.1f}%</div>
                <div class="lbl">Max DD</div>
            </div>
            <div class="strat-stat">
                <div class="val" style="color:var(--purple)">{v_wr:.0f}%</div>
                <div class="lbl">Win Rate</div>
            </div>
        </div>
        <div class="strat-cta">View Bedrock Strategy &rarr;</div>
    </div>
    </a>
    """, unsafe_allow_html=True)

# ── Disclaimer
st.markdown("""
<div class="disc">
    <strong>Disclaimer:</strong> This is not investment advice. JD Quant is a personal quantitative research project,
    not a registered investment adviser or research analyst. Past performance does not guarantee future results.
    The strategies shown are based on historical backtesting which has inherent limitations including
    survivorship bias. Always do your own research before investing.
</div>
""", unsafe_allow_html=True)
