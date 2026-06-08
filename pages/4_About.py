"""About — Investment philosophy and approach."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dashboard_shared import inject_css, render_disclaimer, render_navbar

st.set_page_config(page_title="JD Quant — About", page_icon="", layout="wide", initial_sidebar_state="collapsed")
inject_css()

render_navbar(active="about")

# ── Hero
st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">About</div>
    <h1>Philosophy &amp; <span>Approach</span></h1>
    <div class="tagline">
        Systematic, evidence-based investing in Indian equities.
        No predictions, no opinions, no discretion — only process.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Content
col_l, col_r = st.columns([3, 2], gap="large")

with col_l:
    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">What We Believe</div>
        </div>
        <div class="process">
            <div class="proc-step">
                <div class="num">1</div>
                <div class="txt"><strong>Markets are mostly efficient, but not perfectly</strong><br>
                <span>Academic research has identified persistent anomalies — momentum, value, quality — that survive transaction costs and have decades of out-of-sample evidence across global markets.</span></div>
            </div>
            <div class="proc-step">
                <div class="num">2</div>
                <div class="txt"><strong>Discipline beats intelligence</strong><br>
                <span>The biggest edge in investing isn't a better model — it's the ability to follow a process without emotional interference. Systematic strategies remove the human biases that destroy returns: panic selling, overconfidence, anchoring, herd behavior.</span></div>
            </div>
            <div class="proc-step">
                <div class="num">3</div>
                <div class="txt"><strong>Diversification is the only free lunch</strong><br>
                <span>Running multiple uncorrelated strategies reduces drawdowns without sacrificing returns. Two complementary signals working together produce a smoother, more investable equity curve.</span></div>
            </div>
            <div class="proc-step">
                <div class="num">4</div>
                <div class="txt"><strong>Costs matter, complexity doesn't</strong><br>
                <span>Simple, transparent strategies with low turnover outperform complex black boxes over time. We keep our models interpretable and our transaction costs minimal.</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Our Process</div>
        </div>
        <div class="process">
            <div class="proc-step">
                <div class="num" style="background:var(--green-dim);color:var(--green);">R</div>
                <div class="txt"><strong>Research</strong><br>
                <span>Every strategy starts with published academic evidence. We study peer-reviewed papers, replicate results on Indian market data, and stress-test across multiple market regimes before deploying capital.</span></div>
            </div>
            <div class="proc-step">
                <div class="num" style="background:var(--green-dim);color:var(--green);">B</div>
                <div class="txt"><strong>Backtest</strong><br>
                <span>Rigorous historical simulation with realistic costs, survivorship-bias-free data, and point-in-time fundamentals. We account for slippage, delisted stocks, and reporting lags. No data snooping.</span></div>
            </div>
            <div class="proc-step">
                <div class="num" style="background:var(--green-dim);color:var(--green);">V</div>
                <div class="txt"><strong>Validate</strong><br>
                <span>Paper trading for 90+ days to verify that live signals match backtest expectations. Only strategies that pass this gate receive real capital.</span></div>
            </div>
            <div class="proc-step">
                <div class="num" style="background:var(--green-dim);color:var(--green);">D</div>
                <div class="txt"><strong>Deploy</strong><br>
                <span>Automated execution with fixed rebalance schedules. No overrides, no market timing, no second-guessing. The process is the edge.</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Academic Foundations</div>
        </div>
        <div class="card-desc">Our strategies are grounded in decades of published research:</div>
        <div class="process">
            <div class="proc-step">
                <div class="txt"><strong>Momentum</strong><br>
                <span>Jegadeesh &amp; Titman (1993) first documented the momentum premium. Asness et al. (2013) confirmed it across 8 asset classes and 40+ years. The Indian market shows particularly strong momentum effects in mid and smallcap segments.</span></div>
            </div>
            <div class="proc-step">
                <div class="txt"><strong>Value</strong><br>
                <span>Fama &amp; French (1992) identified the value premium. Greenblatt (2006) popularized earnings yield as a practical value signal. Novy-Marx (2013) showed that combining value with profitability significantly improves risk-adjusted returns.</span></div>
            </div>
            <div class="proc-step">
                <div class="txt"><strong>Quality</strong><br>
                <span>Piotroski (2000) demonstrated that fundamental quality metrics predict stock returns. Asness, Frazzini &amp; Pedersen (2019) showed that quality — measured by profitability, growth, and safety — is a distinct and persistent factor.</span></div>
            </div>
            <div class="proc-step">
                <div class="txt"><strong>Diversification</strong><br>
                <span>Markowitz (1952) formalized the benefits of diversification. Ilmanen (2011) showed that combining uncorrelated return streams improves Sharpe ratios more reliably than optimizing any single strategy.</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_r:
    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Two Strategies</div>
        </div>
        <div class="process">
            <div class="proc-step">
                <div class="num" style="background:var(--accent-dim);color:var(--accent);">A</div>
                <div class="txt"><strong>Ascent</strong><br>
                <span>Captures persistent price trends. Monthly rebalance. Works best in trending markets. Based on cross-sectional momentum anomaly.</span></div>
            </div>
            <div class="proc-step">
                <div class="num" style="background:var(--purple-dim);color:var(--purple);">B</div>
                <div class="txt"><strong>Bedrock</strong><br>
                <span>Identifies undervalued, high-quality businesses. Quarterly rebalance. Works best in corrections. Based on composite value-quality scoring.</span></div>
            </div>
        </div>
        <div class="card-desc" style="margin-top:1rem;">
            Together, they provide exposure to two of the most well-documented
            return anomalies in finance, with low correlation to each other.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">What We Don't Do</div>
        </div>
        <div class="process">
            <div class="proc-step">
                <div class="txt" style="color:var(--red);">
                    <strong>No market timing.</strong><br>
                    <span style="color:var(--text-tertiary)">We don't predict where markets are going. We follow fixed rebalance schedules regardless of headlines.</span>
                </div>
            </div>
            <div class="proc-step">
                <div class="txt" style="color:var(--red);">
                    <strong>No stock tips.</strong><br>
                    <span style="color:var(--text-tertiary)">We don't recommend individual stocks. Our models produce portfolios, not picks. The signal is the system, not any single name.</span>
                </div>
            </div>
            <div class="proc-step">
                <div class="txt" style="color:var(--red);">
                    <strong>No overfitting.</strong><br>
                    <span style="color:var(--text-tertiary)">We use simple, interpretable models with few parameters. If a strategy needs 20 tuned variables to work, it doesn't work.</span>
                </div>
            </div>
            <div class="proc-step">
                <div class="txt" style="color:var(--red);">
                    <strong>No discretion.</strong><br>
                    <span style="color:var(--text-tertiary)">Every decision is rules-based. If a stock meets the criteria, it enters the portfolio. If it doesn't, it exits. No exceptions.</span>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">Risk Awareness</div>
        </div>
        <div class="process">
            <div class="proc-step">
                <div class="txt">
                    <strong>Drawdowns are inevitable.</strong><br>
                    <span style="color:var(--text-tertiary)">Even the best strategies experience significant drawdowns. Our momentum strategy has seen drawdowns exceeding 40% historically. We accept this as the cost of long-term outperformance.</span>
                </div>
            </div>
            <div class="proc-step">
                <div class="txt">
                    <strong>Past performance is not predictive.</strong><br>
                    <span style="color:var(--text-tertiary)">Backtest results, no matter how rigorous, do not guarantee future returns. Market regimes change. Factors can experience prolonged periods of underperformance.</span>
                </div>
            </div>
            <div class="proc-step">
                <div class="txt">
                    <strong>Paper trading is not live trading.</strong><br>
                    <span style="color:var(--text-tertiary)">We validate strategies with paper trading before deploying capital, but execution slippage and market impact in live trading may differ from simulations.</span>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card-v2">
        <div class="card-header">
            <div class="card-title">About JD Quant</div>
        </div>
        <div class="card-desc">
            JD Quant is a personal quantitative research project focused on
            systematic investing in Indian equities. All strategies are developed,
            tested, and deployed by an independent researcher using publicly
            available data and open academic literature.
            <br><br>
            JD Quant is not a registered investment adviser, research analyst,
            or portfolio manager. Nothing on this site constitutes investment advice.
        </div>
    </div>
    """, unsafe_allow_html=True)

render_disclaimer()
