"""JD Quant — Home Page.

Run with:  streamlit run dashboard.py
"""

from __future__ import annotations
from pathlib import Path

import streamlit as st

import pandas as pd

from dashboard_shared import (
    OUTPUTS_DIR,
    inject_css,
    list_runs,
    load_summary,
    render_navbar,
)

DATA_DIR_HOME = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="JD Quant — Systematic Quantitative Strategies for Indian Equities", page_icon="", layout="wide", initial_sidebar_state="collapsed")
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

# ── Live Performance Strip ────────────────────────────────────────────────────

def _load_live_equity(subdir: str) -> pd.DataFrame:
    p = DATA_DIR_HOME / "live" / subdir / "equity.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p).sort_values("date").reset_index(drop=True)

def _load_tf_equity() -> pd.DataFrame:
    p = DATA_DIR_HOME / "paper" / "ascent_trend_filtered" / "equity.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p).sort_values("date").reset_index(drop=True)

a_eq  = _load_live_equity("smallcap_momentum_v2_live")
b_eq  = _load_live_equity("value_quality_v1_live")
tf_eq = _load_tf_equity()

a_last  = a_eq.iloc[-1]  if not a_eq.empty  else None
b_last  = b_eq.iloc[-1]  if not b_eq.empty  else None
a_prev  = a_eq.iloc[-2]  if len(a_eq) > 1   else None
b_prev  = b_eq.iloc[-2]  if len(b_eq) > 1   else None
tf_last = tf_eq.iloc[-1] if not tf_eq.empty else None

# ── Section label + regime pill (separate markdown calls to avoid f-string nesting)
st.markdown("""
<div style="margin-top:2.5rem;display:flex;align-items:center;gap:1rem;margin-bottom:0.8rem;">
    <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;
         letter-spacing:0.12em;color:#64748b;">Live Performance</div>
    <div style="display:flex;align-items:center;gap:0.4rem;font-size:0.65rem;
         color:#10b981;font-weight:600;">
        <span style="width:6px;height:6px;border-radius:50%;background:#10b981;
            box-shadow:0 0 6px #10b981;display:inline-block;"></span>
        LIVE
    </div>
</div>
""", unsafe_allow_html=True)

if tf_last is not None:
    regime    = str(tf_last.get("regime", "UNKNOWN"))
    nifty_10m = float(tf_last.get("nifty_10m_ret", 0))
    is_on     = regime == "RISK_ON"
    r_color   = "#10b981" if is_on else "#ef4444"
    r_icon    = "▲" if is_on else "▼"
    r_label   = "RISK-ON" if is_on else "RISK-OFF"
    nifty_sign = "+" if nifty_10m >= 0 else ""
    st.markdown(
        f'<div style="margin-bottom:0.8rem;">'
        f'<span style="display:inline-flex;align-items:center;gap:0.4rem;'
        f'background:{r_color}15;border:1px solid {r_color}35;'
        f'border-radius:20px;padding:0.25rem 0.75rem;'
        f'font-size:0.68rem;font-weight:700;color:{r_color};'
        f'text-transform:uppercase;letter-spacing:0.08em;">'
        f'{r_icon} {r_label} &nbsp;·&nbsp; NIFTY 10m {nifty_sign}{nifty_10m:.1f}%'
        f'</span></div>',
        unsafe_allow_html=True,
    )

# ── Strategy cards using st.columns (avoids nested f-string HTML composition)
lc1, lc2 = st.columns(2, gap="large")

def _render_live_card(col, label, accent, eq_last, eq_prev):
    with col:
        if eq_last is None:
            st.markdown(
                f'<div style="padding:1.2rem 1.4rem;background:#111820;border-radius:12px;'
                f'border:1px solid #1e2a3a;border-top:3px solid {accent};margin-bottom:1rem;">'
                f'<div style="color:#64748b;font-size:0.8rem;">No data yet</div></div>',
                unsafe_allow_html=True,
            )
            return
        nav      = float(eq_last["nav"])
        total    = (nav - 1.0) * 100
        mv       = float(eq_last.get("market_value", 0))
        date_str = str(eq_last.get("date", ""))[:10]
        daily    = 0.0
        if eq_prev is not None:
            pn    = float(eq_prev["nav"])
            daily = (nav / pn - 1) * 100 if pn > 0 else 0
        t_color = "#10b981" if total >= 0 else "#ef4444"
        d_color = "#10b981" if daily >= 0 else "#ef4444"
        t_sign  = "+" if total >= 0 else ""
        d_sign  = "+" if daily >= 0 else ""
        st.markdown(
            f'<div style="padding:1.2rem 1.4rem;background:#111820;border-radius:12px;'
            f'border:1px solid #1e2a3a;border-top:3px solid {accent};margin-bottom:1rem;">'
            f'<div style="font-size:0.6rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.1em;color:#64748b;margin-bottom:0.4rem;">{label}</div>'
            f'<div style="display:flex;align-items:baseline;gap:0.5rem;margin-bottom:0.5rem;">'
            f'<span style="font-size:1.6rem;font-weight:800;color:{t_color};letter-spacing:-0.03em;">'
            f'{t_sign}{total:.2f}%</span>'
            f'<span style="font-size:0.75rem;font-weight:600;color:{d_color};'
            f'background:{d_color}15;padding:0.1rem 0.4rem;border-radius:5px;">'
            f'{d_sign}{daily:.2f}% today</span>'
            f'</div>'
            f'<div style="font-size:0.78rem;color:#94a3b8;">'
            f'&#8377;{mv:,.0f} market value'
            f'<span style="color:#64748b;"> &nbsp;·&nbsp; {date_str}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

_render_live_card(lc1, "Ascent",  "#3b82f6", a_last, a_prev)
_render_live_card(lc2, "Bedrock", "#a78bfa", b_last, b_prev)

# ── Disclaimer
st.markdown("""
<div class="disc">
    <strong>Disclaimer:</strong> This is not investment advice. JD Quant is a personal quantitative research project,
    not a registered investment adviser or research analyst. Past performance does not guarantee future results.
    The strategies shown are based on historical backtesting which has inherent limitations including
    survivorship bias. Always do your own research before investing.
</div>
""", unsafe_allow_html=True)
