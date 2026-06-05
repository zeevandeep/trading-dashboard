"""JD Quant — Home Page.

Run with:  streamlit run dashboard.py
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from dashboard_shared import (
    OUTPUTS_DIR,
    inject_css,
    list_runs,
    load_summary,
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

# ── Navbar
st.markdown(f"""
<div class="navbar">
    <div class="logo">
        <div class="logo-mark">JD</div>
        JD Quant
    </div>
    <div class="nav-status">
        <div class="live-dot"></div>
        Strategies Active &middot; {datetime.now().strftime("%d %b %Y")}
    </div>
</div>
""", unsafe_allow_html=True)

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
    <div class="strat-card">
        <div class="strat-num" style="color:var(--accent);">Strategy 1</div>
        <div class="strat-name">Momentum</div>
        <div class="strat-desc">
            12-month cross-sectional momentum on NSE 500 ex Nifty 50.
            Monthly rebalance, top 15 equal weight. Pure price-based signal.
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
    </div>
    """, unsafe_allow_html=True)

    st.page_link("pages/1_Momentum.py", label="View Strategy 1 →", icon="📈")

with col2:
    v_cagr = vq.get("cagr", 0) * 100
    v_ret = vq.get("final_equity", 1)
    v_dd = vq.get("max_drawdown", 0) * 100
    v_wr = vq.get("win_rate_monthly", 0) * 100

    st.markdown(f"""
    <div class="strat-card">
        <div class="strat-num" style="color:var(--purple);">Strategy 2</div>
        <div class="strat-name">Value + Quality</div>
        <div class="strat-desc">
            Buys cheap, high-quality stocks — low P/E, high ROE, low debt,
            growing earnings. Quarterly rebalance, top 15 equal weight.
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
    </div>
    """, unsafe_allow_html=True)

    st.page_link("pages/2_Value_Quality.py", label="View Strategy 2 →", icon="💎")

# ── Disclaimer
st.markdown("""
<div class="disc">
    <strong>Disclaimer:</strong> This is not financial advice. Past performance does not guarantee future results.
    The strategies shown are based on historical backtesting which has inherent limitations including
    survivorship bias. Always do your own research before investing.
</div>
""", unsafe_allow_html=True)
