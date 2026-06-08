"""Feedback — Collect user feedback via embedded Google Form."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

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

components.html(
    """
    <iframe
        src="https://docs.google.com/forms/d/e/1FAIpQLScpLCCgwiLqtGmm-A-p-t02P38qTpSXhMkas2L-FSsahmw24w/viewform?embedded=true"
        width="100%"
        height="1400"
        frameborder="0"
        marginheight="0"
        marginwidth="0"
        style="background:transparent;"
    >Loading…</iframe>
    """,
    height=1420,
)

render_disclaimer()
