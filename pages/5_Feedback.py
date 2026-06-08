"""Feedback — Link to Google Form for user feedback."""

from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dashboard_shared import inject_css, render_navbar, render_disclaimer

st.set_page_config(page_title="JD Quant — Feedback", page_icon="", layout="wide", initial_sidebar_state="collapsed")
inject_css()

render_navbar(active="feedback")

st.markdown("""
<div class="hero-v2">
    <div class="eyebrow">We'd love to hear from you</div>
    <h1>Share Your <span>Feedback</span></h1>
    <div class="tagline">
        Help us improve. Your input shapes what we build next.
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<a href="https://docs.google.com/forms/d/e/1FAIpQLScpLCCgwiLqtGmm-A-p-t02P38qTpSXhMkas2L-FSsahmw24w/viewform" target="_blank" style="text-decoration:none;color:inherit;display:block;">
<div class="strat-card" style="text-align:center;max-width:600px;margin:2rem auto;">
    <div class="strat-name" style="font-size:1.2rem;">Take the 2-Minute Survey</div>
    <div class="strat-desc" style="margin:0.8rem auto 1.2rem;max-width:400px;">
        Tell us what you think, what features you'd like, and whether you'd use a premium research service.
    </div>
    <div class="strat-cta">Open Feedback Form &rarr;</div>
</div>
</a>
""", unsafe_allow_html=True)

st.markdown("""
<div class="card-v2" style="max-width:600px;margin:0 auto;">
    <div class="card-header">
        <div class="card-title">What We're Asking</div>
    </div>
    <div class="process">
        <div class="proc-step">
            <div class="num">1</div>
            <div class="txt"><strong>Your impression</strong><br><span>What do you think of JD Quant?</span></div>
        </div>
        <div class="proc-step">
            <div class="num">2</div>
            <div class="txt"><strong>Feature requests</strong><br><span>What would you like us to build next?</span></div>
        </div>
        <div class="proc-step">
            <div class="num">3</div>
            <div class="txt"><strong>Investment intent</strong><br><span>Would you invest using these strategies?</span></div>
        </div>
        <div class="proc-step">
            <div class="num">4</div>
            <div class="txt"><strong>Premium interest</strong><br><span>Would you pay for a research service like this?</span></div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

render_disclaimer()
