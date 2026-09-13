"""Landing screen: what BAAR-AAMAD does, and two ways to start."""

from __future__ import annotations

import streamlit as st

from core import state
from modules.corpus import get_corpus
from ui import theme
from ui.pages.create_case import load_demo

#: Kept short on purpose. The old page explained the whole workflow in
#: paragraphs; a line each is enough to orient someone.
HOW_IT_WORKS = [
    ("Find", "The requirements that apply to your product, origin and destination."),
    ("Check", "Your documents, read and compared against those requirements."),
    ("Explain", "Why each item was flagged, with the source behind it."),
    ("Fix", "An action plan, ordered by what matters most."),
    ("Recheck", "Upload the correction and run the case again."),
]


def _sources() -> None:
    """Name the actual sources. Credibility comes from being checkable."""
    try:
        corpus = get_corpus()
    except Exception:
        theme.note("The authoritative source library could not be loaded.")
        return

    for source in corpus.sources.values():
        st.markdown(
            f'<div class="ba-source">'
            f'<a href="{source.source_url}" target="_blank" rel="noopener">'
            f"{source.source_name}</a></div>",
            unsafe_allow_html=True,
        )


def render() -> None:
    theme.masthead("AI Export Readiness &amp; Compliance Agent")

    st.markdown(
        '<div class="ba-h1">Know what your shipment needs<br>before it gets '
        "stopped.</div>"
        '<div class="ba-lede">BAAR-AAMAD checks your export case, your '
        "documents and the available compliance evidence to identify gaps, "
        "explain what needs attention, and guide you through correction."
        "</div>",
        unsafe_allow_html=True,
    )

    left, middle, right = st.columns([1.1, 1, 1.4])
    with left:
        if st.button("Start an export check", type="primary", width="stretch"):
            state.goto(state.Page.CREATE_CASE)
            st.rerun()
    with middle:
        if st.button("Load golden demo", width="stretch"):
            load_demo()
            state.goto(state.Page.CREATE_CASE)
            st.rerun()
    with right:
        if state.has_case():
            case = state.current_case()
            if st.button(f"Return to case {case.case_id}", width="stretch"):
                state.goto(
                    state.Page.DASHBOARD if case.findings else state.Page.CASE_CREATED
                )
                st.rerun()

    st.markdown("")
    theme.workflow_strip()

    theme.section("How it works")
    st.markdown(
        "".join(
            f'<div class="ba-howto"><div class="ba-howto-step">{step}</div>'
            f'<div class="ba-howto-text">{line}</div></div>'
            for step, line in HOW_IT_WORKS
        ),
        unsafe_allow_html=True,
    )

    theme.section("Where the requirements come from")
    _sources()
    theme.note(
        "Every requirement BAAR-AAMAD states is traced to one of these "
        "sources and quoted with a link you can open. Coverage varies by "
        "product and market: where the sources do not settle a question, the "
        "case says so and marks it for human verification. "
        "<b>BAAR-AAMAD never invents a regulation.</b>"
    )

    theme.disclaimer()
