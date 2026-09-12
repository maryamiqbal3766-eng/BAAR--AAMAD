"""
BAAR-AAMAD — application entry point.

This file is a router and nothing else. All logic lives in `core` (shared
contract, rules, state) and all rendering lives in `ui/pages`. Keeping it
thin means several people can work on different screens without colliding
here.

Run:
    .venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from core import state
from ui import theme
from ui.pages import (
    action_plan,
    case_created,
    create_case,
    dashboard,
    finding_detail,
    landing,
    passport,
    processing,
    upload,
)

st.set_page_config(
    page_title="BAAR-AAMAD — Export Readiness",
    page_icon="▣",
    layout="centered",
    initial_sidebar_state="collapsed",
)

ROUTES = {
    state.Page.LANDING: landing.render,
    state.Page.CREATE_CASE: create_case.render,
    state.Page.CASE_CREATED: case_created.render,
    state.Page.UPLOAD: upload.render,
    state.Page.PROCESSING: processing.render,
    state.Page.DASHBOARD: dashboard.render,
    state.Page.FINDING: finding_detail.render,
    state.Page.ACTION_PLAN: action_plan.render,
    state.Page.PASSPORT: passport.render,
}


def main() -> None:
    theme.inject()
    state.init_session()
    ROUTES[state.current_page()]()


main()
