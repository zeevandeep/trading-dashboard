"""Combined Portfolio — Ascent + Bedrock together."""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dashboard_shared import (
    DATA_DIR,
    OUTPUTS_DIR,
    PAPER_DIR,
    apply_plotly_style,
    inject_css,
    list_runs,
    load_series,
    load_summary,
    render_disclaimer,
    render_navbar,
)

st.set_page_config(page_title="JD Quant — Strategies", page_icon="", layout="wide", initial_sidebar_state="collapsed")
inject_css()

# ─── Data ─────────────────────────────────────────────────────────────────────

runs = list_runs()

# Ascent (Momentum) backtest
mom_run = next((r for r in runs if "smallcap_momentum_v2" in r.name and "smoke" not in r.name), runs[0] if runs else None)
mom_summary = load_summary(str(mom_run)) if mom_run else {}
mom_equity = load_series(str(mom_run), "equity_curve.csv") if mom_run else None
mom_returns = load_series(str(mom_run), "returns.csv") if mom_run else None

# Bedrock (V+Q) backtest
vq_runs = [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and "value_quality" in p.name and (p / "summary.json").exists()] if OUTPUTS_DIR.exists() else []
vq_run = sorted(vq_runs, key=lambda p: p.name, reverse=True)[0] if vq_runs else None
vq_summary = load_summary(str(vq_run)) if vq_run else {}
vq_equity = load_series(str(vq_run), "equity_curve.csv") if vq_run else None
vq_returns = load_series(str(vq_run), "returns.csv") if vq_run else None

# Paper states
ascent_paper = None
ascent_paper_dir = PAPER_DIR / "smallcap_momentum_v2"
if (ascent_paper_dir / "state.json").exists():
    ascent_paper = json.loads((ascent_paper_dir / "state.json").read_text())

bedrock_paper = None
bedrock_paper_dir = PAPER_DIR / "value_quality_v1"
if (bedrock_paper_dir / "state.json").exists():
    bedrock_paper = json.loads((bedrock_paper_dir / "state.json").read_text())

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER
# ═══════════════════════════════════════════════════════════════════════════════

render_navbar(active="strategies")

# ── Hero
st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">Combined Portfolio</div>
    <h1>Ascent + <span>Bedrock</span></h1>
    <div class="tagline">
        Two uncorrelated strategies working together. Momentum captures trends,
        fundamentals provide stability. The sum is greater than the parts.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Combined Backtest Stats
if mom_equity is not None and vq_equity is not None:
    # Align to common date range and compute 50/50 blend
    common_start = max(mom_equity.index[0], vq_equity.index[0])
    common_end = min(mom_equity.index[-1], vq_equity.index[-1])

    m_eq = mom_equity.loc[common_start:common_end]
    v_eq = vq_equity.loc[common_start:common_end]

    m_ret = mom_returns.loc[common_start:common_end]
    v_ret = vq_returns.loc[common_start:common_end]

    # Align indices
    common_idx = m_ret.index.intersection(v_ret.index)
    m_ret = m_ret.loc[common_idx]
    v_ret = v_ret.loc[common_idx]

    # 50/50 blended returns
    blend_ret = 0.5 * m_ret + 0.5 * v_ret
    blend_equity = (1 + blend_ret).cumprod()

    # Normalize individual equities to start at 1 from common start
    m_eq_norm = m_eq / m_eq.iloc[0]
    v_eq_norm = v_eq / v_eq.iloc[0]

    # Blended metrics
    years = len(blend_ret) / 252
    blend_cagr = (blend_equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0
    blend_vol = blend_ret.std() * np.sqrt(252)
    blend_sharpe = (blend_cagr - 0.06) / blend_vol if blend_vol > 0 else 0
    blend_peak = blend_equity.cummax()
    blend_dd = (blend_equity / blend_peak - 1)
    blend_max_dd = blend_dd.min()
    blend_final = blend_equity.iloc[-1]

    # Correlation
    corr = m_ret.corr(v_ret)

    # Win rate
    monthly_blend = (1 + blend_ret).resample("ME").prod() - 1
    blend_win_rate = (monthly_blend > 0).mean()

    # Stat bar
    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-cell">
            <div class="val green">{blend_cagr*100:.1f}%</div>
            <div class="lbl">Blended CAGR</div>
        </div>
        <div class="stat-cell">
            <div class="val gold">{blend_final:.0f}x</div>
            <div class="lbl">Total Return</div>
        </div>
        <div class="stat-cell">
            <div class="val" style="color:var(--red)">{blend_max_dd*100:.1f}%</div>
            <div class="lbl">Max Drawdown</div>
        </div>
        <div class="stat-cell">
            <div class="val accent">{blend_sharpe:.2f}</div>
            <div class="lbl">Sharpe Ratio</div>
        </div>
        <div class="stat-cell">
            <div class="val purple">{corr:.2f}</div>
            <div class="lbl">Correlation</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Two Columns
    col_l, col_r = st.columns([3, 2], gap="large")

    with col_l:
        # Combined equity curve
        st.markdown("""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Growth Comparison</div>
                <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Backtest</div>
            </div>
            <div class="card-desc">Growth of Rs. 1 — individual strategies vs 50/50 blend. Log scale.</div>
        </div>
        """, unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=m_eq_norm.index, y=m_eq_norm.values, mode="lines",
            name="Ascent", line=dict(color="#3b82f6", width=1.5),
            hovertemplate="%{x|%b %Y}: Rs. %{y:.2f}<extra>Ascent</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=v_eq_norm.index, y=v_eq_norm.values, mode="lines",
            name="Bedrock", line=dict(color="#a78bfa", width=1.5),
            hovertemplate="%{x|%b %Y}: Rs. %{y:.2f}<extra>Bedrock</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=blend_equity.index, y=blend_equity.values, mode="lines",
            name="50/50 Blend", line=dict(color="#10b981", width=2.5),
            hovertemplate="%{x|%b %Y}: Rs. %{y:.2f}<extra>Blend</extra>",
        ))
        apply_plotly_style(fig, height=360, yaxis_type="log", yaxis_tickprefix="Rs. ",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
        st.plotly_chart(fig, use_container_width=True)

        # Drawdown comparison
        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Drawdown Comparison</div>
                <div class="card-badge" style="background:var(--red-dim);color:var(--red);">Blend max {blend_max_dd*100:.1f}%</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        m_peak = m_eq_norm.cummax()
        m_dd = m_eq_norm / m_peak - 1
        v_peak = v_eq_norm.cummax()
        v_dd = v_eq_norm / v_peak - 1

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=m_dd.index, y=m_dd.values, mode="lines",
            name="Ascent", line=dict(color="#3b82f6", width=1), opacity=0.5,
            hovertemplate="%{x|%b %Y}: %{y:.1%}<extra>Ascent</extra>",
        ))
        fig_dd.add_trace(go.Scatter(
            x=v_dd.index, y=v_dd.values, mode="lines",
            name="Bedrock", line=dict(color="#a78bfa", width=1), opacity=0.5,
            hovertemplate="%{x|%b %Y}: %{y:.1%}<extra>Bedrock</extra>",
        ))
        fig_dd.add_trace(go.Scatter(
            x=blend_dd.index, y=blend_dd.values, mode="lines",
            name="50/50 Blend", line=dict(color="#10b981", width=2),
            fill="tozeroy", fillcolor="rgba(16,185,129,0.06)",
            hovertemplate="%{x|%b %Y}: %{y:.1%}<extra>Blend</extra>",
        ))
        apply_plotly_style(fig_dd, height=220, yaxis_tickformat=".0%",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
        st.plotly_chart(fig_dd, use_container_width=True)

        # Rolling correlation
        st.markdown("""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Rolling Correlation (1 Year)</div>
                <div class="card-badge" style="background:var(--purple-dim);color:var(--purple);">Diversification</div>
            </div>
            <div class="card-desc">Lower correlation = better diversification. Below 0.5 is excellent.</div>
        </div>
        """, unsafe_allow_html=True)

        rolling_corr = m_ret.rolling(252).corr(v_ret).dropna()
        fig_corr = go.Figure()
        fig_corr.add_trace(go.Scatter(
            x=rolling_corr.index, y=rolling_corr.values, mode="lines",
            line=dict(color="#a78bfa", width=1.5),
            fill="tozeroy", fillcolor="rgba(167,139,250,0.08)",
            hovertemplate="%{x|%b %Y}: %{y:.2f}<extra></extra>",
        ))
        fig_corr.add_hline(y=0.5, line_dash="dash", line_color="#64748b", line_width=1)
        fig_corr.add_annotation(x=rolling_corr.index[len(rolling_corr)//2], y=0.53,
                                text="0.5 threshold", showarrow=False,
                                font=dict(size=10, color="#64748b"))
        apply_plotly_style(fig_corr, height=200, showlegend=False)
        fig_corr.update_yaxes(range=[-0.2, 1.0])
        st.plotly_chart(fig_corr, use_container_width=True)

    with col_r:
        # Side-by-side key numbers
        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Strategy Comparison</div>
            </div>
            <table class="kstats">
                <tr>
                    <td></td>
                    <td style="text-align:right;color:var(--accent);font-weight:700">Ascent</td>
                    <td style="text-align:right;color:var(--purple);font-weight:700">Bedrock</td>
                    <td style="text-align:right;color:var(--green);font-weight:700">Blend</td>
                </tr>
                <tr>
                    <td>CAGR</td>
                    <td style="text-align:right;color:var(--green)">{mom_summary.get('cagr',0)*100:.1f}%</td>
                    <td style="text-align:right;color:var(--green)">{vq_summary.get('cagr',0)*100:.1f}%</td>
                    <td style="text-align:right;color:var(--green)">{blend_cagr*100:.1f}%</td>
                </tr>
                <tr>
                    <td>Volatility</td>
                    <td style="text-align:right">{mom_summary.get('annual_vol',0)*100:.1f}%</td>
                    <td style="text-align:right">{vq_summary.get('annual_vol',0)*100:.1f}%</td>
                    <td style="text-align:right">{blend_vol*100:.1f}%</td>
                </tr>
                <tr>
                    <td>Sharpe</td>
                    <td style="text-align:right">{mom_summary.get('sharpe',0):.2f}</td>
                    <td style="text-align:right">{vq_summary.get('sharpe',0):.2f}</td>
                    <td style="text-align:right">{blend_sharpe:.2f}</td>
                </tr>
                <tr>
                    <td>Max DD</td>
                    <td style="text-align:right;color:var(--red)">{mom_summary.get('max_drawdown',0)*100:.1f}%</td>
                    <td style="text-align:right;color:var(--red)">{vq_summary.get('max_drawdown',0)*100:.1f}%</td>
                    <td style="text-align:right;color:var(--red)">{blend_max_dd*100:.1f}%</td>
                </tr>
                <tr>
                    <td>Win Rate</td>
                    <td style="text-align:right">{mom_summary.get('win_rate_monthly',0)*100:.0f}%</td>
                    <td style="text-align:right">{vq_summary.get('win_rate_monthly',0)*100:.0f}%</td>
                    <td style="text-align:right">{blend_win_rate*100:.0f}%</td>
                </tr>
                <tr>
                    <td>Correlation</td>
                    <td colspan="3" style="text-align:right;color:var(--purple);font-weight:600">{corr:.2f}</td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        # Diversification benefit
        naive_dd = min(mom_summary.get("max_drawdown", 0), vq_summary.get("max_drawdown", 0))
        dd_benefit = blend_max_dd - naive_dd
        st.markdown(f"""
        <div class="card-v2">
            <div class="card-header">
                <div class="card-title">Diversification Benefit</div>
                <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Active</div>
            </div>
            <div class="process">
                <div class="proc-step">
                    <div class="num" style="background:var(--green-dim);color:var(--green);">1</div>
                    <div class="txt"><strong>Lower drawdowns</strong><br><span>Blend max DD of {blend_max_dd*100:.1f}% vs worst single strategy {min(mom_summary.get('max_drawdown',0), vq_summary.get('max_drawdown',0))*100:.1f}%</span></div>
                </div>
                <div class="proc-step">
                    <div class="num" style="background:var(--green-dim);color:var(--green);">2</div>
                    <div class="txt"><strong>Smoother ride</strong><br><span>Blended volatility of {blend_vol*100:.1f}% — lower than either strategy alone.</span></div>
                </div>
                <div class="proc-step">
                    <div class="num" style="background:var(--green-dim);color:var(--green);">3</div>
                    <div class="txt"><strong>Better risk-adjusted</strong><br><span>Blend Sharpe of {blend_sharpe:.2f} benefits from low correlation ({corr:.2f}).</span></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Overlap analysis
        ascent_holdings = set(ascent_paper.get("holdings", {}).keys()) if ascent_paper else set()
        bedrock_holdings = set(bedrock_paper.get("holdings", {}).keys()) if bedrock_paper else set()

        if ascent_holdings or bedrock_holdings:
            overlap = ascent_holdings & bedrock_holdings
            total_unique = len(ascent_holdings | bedrock_holdings)

            st.markdown(f"""
            <div class="card-v2">
                <div class="card-header">
                    <div class="card-title">Current Overlap</div>
                </div>
                <table class="kstats">
                    <tr><td>Ascent positions</td><td style="text-align:right">{len(ascent_holdings)}</td></tr>
                    <tr><td>Bedrock positions</td><td style="text-align:right">{len(bedrock_holdings)}</td></tr>
                    <tr><td>Unique stocks</td><td style="text-align:right;font-weight:700">{total_unique}</td></tr>
                    <tr><td>Overlap</td><td style="text-align:right;color:var(--purple)">{len(overlap)}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            if overlap:
                st.markdown(f"""
                <div class="card-v2">
                    <div class="card-header">
                        <div class="card-title">High Conviction</div>
                        <div class="card-badge" style="background:var(--green-dim);color:var(--green);">Both Signals</div>
                    </div>
                    <div class="card-desc">Stocks appearing in both Ascent and Bedrock:</div>
                    <div style="color:var(--text-primary);font-weight:600;font-size:0.95rem;line-height:1.8;">
                        {", ".join(sorted(overlap))}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # Paper trading status
        if ascent_paper or bedrock_paper:
            paper_rows = []
            for sname, sstate in [("Ascent", ascent_paper), ("Bedrock", bedrock_paper)]:
                if sstate:
                    seq = sstate.get("equity", 1.0)
                    spnl = (seq - 1.0) * 100
                    scolor = "#10b981" if spnl >= 0 else "#ef4444"
                    ssign = "+" if spnl >= 0 else ""
                    ssince = sstate.get("created", "")[:10]
                    paper_rows.append(f'<tr><td style="font-weight:600">{sname}</td><td style="text-align:right;color:{scolor};font-weight:600">{ssign}{spnl:.2f}%</td><td style="text-align:right;color:#64748b">{ssince}</td></tr>')
                else:
                    paper_rows.append(f'<tr><td style="font-weight:600">{sname}</td><td style="text-align:right;color:#64748b">—</td><td style="text-align:right;color:#64748b">Not started</td></tr>')

            paper_html = "\n".join(paper_rows)
            st.markdown(f'<div class="card-v2"><div class="card-header"><div class="card-title">Paper Trading</div><div class="card-badge" style="background:rgba(245,158,11,0.10);color:#f59e0b;">Live Tracking</div></div><table class="kstats"><tr><td style="color:#64748b">Strategy</td><td style="text-align:right;color:#64748b">P&L</td><td style="text-align:right;color:#64748b">Since</td></tr>{paper_html}</table></div>', unsafe_allow_html=True)

else:
    st.warning("Need both Ascent and Bedrock backtest data for combined analysis.")

render_disclaimer()
