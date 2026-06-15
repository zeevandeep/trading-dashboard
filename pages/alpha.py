"""Alpha — Private view with full holdings and stock picks.

Share jdquant.in/alpha with friends and family.
Not linked from the public site.
"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dashboard_shared import (
    DATA_DIR,
    OUTPUTS_DIR,
    PAPER_DIR,
    days_to_rebal,
    inject_css,
    list_runs,
    load_summary,
    render_disclaimer,
)

st.set_page_config(page_title="JD Quant — Alpha", page_icon="", layout="wide", initial_sidebar_state="collapsed")
inject_css()

# ─── Data ─────────────────────────────────────────────────────────────────────

runs = list_runs()

# Ascent backtest summary
mom_run = next((r for r in runs if "smallcap_momentum_v2" in r.name and "smoke" not in r.name), None)
mom_summary = load_summary(str(mom_run)) if mom_run else {}

# Bedrock backtest summary
vq_runs_list = [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and "value_quality" in p.name and (p / "summary.json").exists()] if OUTPUTS_DIR.exists() else []
vq_run = sorted(vq_runs_list, key=lambda p: p.name, reverse=True)[0] if vq_runs_list else None
vq_summary = load_summary(str(vq_run)) if vq_run else {}

# Paper states
ascent_paper = None
ascent_paper_dir = PAPER_DIR / "smallcap_momentum_v2"
if (ascent_paper_dir / "state.json").exists():
    ascent_paper = json.loads((ascent_paper_dir / "state.json").read_text())

bedrock_paper = None
bedrock_paper_dir = PAPER_DIR / "value_quality_v1"
if (bedrock_paper_dir / "state.json").exists():
    bedrock_paper = json.loads((bedrock_paper_dir / "state.json").read_text())

# Bedrock V+Q scores
vq_cache_path = DATA_DIR / "vq_scores_latest.json"
vq_data = {}
if vq_cache_path.exists():
    vq_data = json.loads(vq_cache_path.read_text())

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown(f"""
<div class="navbar">
    <a href="/" target="_self" style="text-decoration:none;color:inherit;">
    <div class="logo">
        <div class="logo-mark">JD</div>
        JD Quant
    </div>
    </a>
    <div class="nav-status">
        <div class="live-dot"></div>
        Alpha View &middot; {datetime.now().strftime("%d %b %Y")}
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">Private Research View</div>
    <h1>Alpha <span>Access</span></h1>
    <div class="tagline">
        Full portfolio holdings, live picks, and paper trading performance.
        Shared for informational purposes only — this is not investment advice.
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="disc" style="margin-top:0;margin-bottom:2rem;border-color:var(--gold);background:rgba(245,158,11,0.05);">
    <strong>Private &amp; Confidential:</strong> This page shows JD Quant's personal portfolio holdings.
    Shared for informational purposes only. This is not a recommendation to buy or sell any security.
    Past performance does not guarantee future results. Always do your own research.
</div>
""", unsafe_allow_html=True)

# ── Paper Trading Summary
st.markdown("""
<div class="card-v2">
    <div class="card-header">
        <div class="card-title">Paper Trading Status</div>
        <div class="card-badge" style="background:var(--gold-dim);color:var(--gold);">Live Tracking</div>
    </div>
</div>
""", unsafe_allow_html=True)

p1, p2, p3, p4 = st.columns(4)

if ascent_paper:
    a_eq_path = ascent_paper_dir / "equity.csv"
    if a_eq_path.exists():
        _a_eq_df = pd.read_csv(a_eq_path)
        a_days = len(_a_eq_df)
        a_eq = _a_eq_df["equity"].iloc[-1] if not _a_eq_df.empty else 1.0
    else:
        a_days = 0
        a_eq = ascent_paper.get("equity", 1.0)
    a_pnl = (a_eq - 1.0) * 100
    p1.metric("Ascent P&L", f"{a_pnl:+.2f}%")
    p2.metric("Ascent Days", f"{a_days}/90")

if bedrock_paper:
    b_eq_path = bedrock_paper_dir / "equity.csv"
    if b_eq_path.exists():
        _b_eq_df = pd.read_csv(b_eq_path)
        b_days = len(_b_eq_df)
        b_eq = _b_eq_df["equity"].iloc[-1] if not _b_eq_df.empty else 1.0
    else:
        b_days = 0
        b_eq = bedrock_paper.get("equity", 1.0)
    b_pnl = (b_eq - 1.0) * 100
    p3.metric("Bedrock P&L", f"{b_pnl:+.2f}%")
    p4.metric("Bedrock Days", f"{b_days}/90")

# ── Two strategy columns
col_a, col_b = st.columns(2, gap="large")

# ── Ascent Holdings
with col_a:
    st.markdown(f"""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Ascent — Current Holdings</div>
            <div class="card-badge" style="background:var(--accent-dim);color:var(--accent);">Momentum</div>
        </div>
        <div class="card-desc">
            CAGR {mom_summary.get('cagr',0)*100:.1f}% &middot;
            Sharpe {mom_summary.get('sharpe',0):.2f} &middot;
            Monthly rebalance &middot;
            {days_to_rebal()} days to next
        </div>
    """, unsafe_allow_html=True)

    if ascent_paper and ascent_paper.get("holdings"):
        holdings = ascent_paper["holdings"]
        last_r = ascent_paper.get("last_rebalance", "-")
        sh = sorted(holdings.items(), key=lambda x: -x[1])

        rows = "".join(
            f'<tr><td class="idx">{i}</td><td class="sym">{t}</td><td class="wt">{w*100:.1f}%</td></tr>'
            for i, (t, w) in enumerate(sh, 1)
        )
        st.markdown(f"""
            <div class="card-desc">Last rebalanced {last_r} &middot; {len(holdings)} positions &middot; Equal weight</div>
            <table class="htable">
                <thead><tr><th>#</th><th>Ticker</th><th>Weight</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="card-desc">No holdings yet.</div>
        </div>
        """, unsafe_allow_html=True)

# ── Bedrock Holdings
with col_b:
    st.markdown(f"""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Bedrock — Current Holdings</div>
            <div class="card-badge" style="background:var(--purple-dim);color:var(--purple);">Value + Quality</div>
        </div>
        <div class="card-desc">
            CAGR {vq_summary.get('cagr',0)*100:.1f}% &middot;
            Sharpe {vq_summary.get('sharpe',0):.2f} &middot;
            Quarterly rebalance
        </div>
    """, unsafe_allow_html=True)

    if bedrock_paper and bedrock_paper.get("holdings"):
        holdings = bedrock_paper["holdings"]
        last_r = bedrock_paper.get("last_rebalance", "-")
        sh = sorted(holdings.items(), key=lambda x: -x[1])

        rows = "".join(
            f'<tr><td class="idx">{i}</td><td class="sym">{t}</td><td class="wt">{w*100:.1f}%</td></tr>'
            for i, (t, w) in enumerate(sh, 1)
        )
        st.markdown(f"""
            <div class="card-desc">Last rebalanced {last_r} &middot; {len(holdings)} positions &middot; Equal weight</div>
            <table class="htable">
                <thead><tr><th>#</th><th>Ticker</th><th>Weight</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="card-desc">No holdings yet.</div>
        </div>
        """, unsafe_allow_html=True)

# ── Bedrock Detailed Scores
if vq_data.get("top_15"):
    picks = vq_data["top_15"]
    updated = vq_data.get("updated_at", "")[:10]

    vq_rows = ""
    for i, p in enumerate(picks, 1):
        pe = p.get("pe", 0) or 0
        roe = (p.get("roe", 0) or 0) * 100
        de = p.get("de", 0) or 0
        eg = (p.get("earnings_growth") or 0) * 100
        eg_color = "var(--green)" if eg > 0 else "var(--red)"
        vq_rows += (
            f'<tr>'
            f'<td class="idx">{i}</td>'
            f'<td class="sym">{p["ticker"]}</td>'
            f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:var(--text-secondary)">{pe:.1f}</td>'
            f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:var(--green)">{roe:.1f}%</td>'
            f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:var(--text-secondary)">{de:.1f}</td>'
            f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:{eg_color}">{eg:+.0f}%</td>'
            f'<td class="wt">{p["score"]:.3f}</td>'
            f'</tr>'
        )

    st.markdown(f"""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Bedrock — Factor Scores</div>
            <div class="card-badge" style="background:var(--purple-dim);color:var(--purple);">Detail</div>
        </div>
        <div class="card-desc">Composite score: Earnings Yield + ROE + Low Debt + Earnings Growth. Last refreshed {updated}.</div>
        <table class="htable">
            <thead><tr><th>#</th><th>Ticker</th><th>P/E</th><th>ROE</th><th>D/E</th><th>EPS Gr.</th><th>Score</th></tr></thead>
            <tbody>{vq_rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

# ── Overlap Analysis
ascent_set = set(ascent_paper.get("holdings", {}).keys()) if ascent_paper else set()
bedrock_set = set(bedrock_paper.get("holdings", {}).keys()) if bedrock_paper else set()

if ascent_set and bedrock_set:
    overlap = ascent_set & bedrock_set
    only_ascent = ascent_set - bedrock_set
    only_bedrock = bedrock_set - ascent_set
    total_unique = len(ascent_set | bedrock_set)

    ol, ov_r = st.columns(2, gap="large")

    with ol:
        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Strategy Overlap</div>
            </div>
            <table class="kstats">
                <tr><td>Ascent-only stocks</td><td style="text-align:right">{len(only_ascent)}</td></tr>
                <tr><td>Bedrock-only stocks</td><td style="text-align:right">{len(only_bedrock)}</td></tr>
                <tr><td>In both strategies</td><td style="text-align:right;color:var(--green);font-weight:700">{len(overlap)}</td></tr>
                <tr><td>Total unique positions</td><td style="text-align:right;font-weight:700">{total_unique}</td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

    with ov_r:
        if overlap:
            st.markdown(f"""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">High Conviction</div>
                    <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Both Signals</div>
                </div>
                <div class="card-desc">These stocks rank highly on BOTH momentum and fundamentals:</div>
                <div style="color:var(--text-primary);font-weight:600;font-size:1rem;line-height:2;">
                    {", ".join(sorted(overlap))}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">No Overlap</div>
                </div>
                <div class="card-desc">The two strategies hold completely different stocks — maximum diversification.</div>
            </div>
            """, unsafe_allow_html=True)

# ── Links to full strategy pages
st.markdown("")
l1, l2, l3 = st.columns(3)
with l1:
    st.page_link("pages/1_Momentum.py", label="Ascent — Full Backtest →")
with l2:
    st.page_link("pages/2_Value_Quality.py", label="Bedrock — Full Backtest →")
with l3:
    st.page_link("pages/3_Portfolio.py", label="Combined Portfolio →")

render_disclaimer()
