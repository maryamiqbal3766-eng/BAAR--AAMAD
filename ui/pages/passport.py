"""
Compliance Passport — the flagship output.

Section order is fixed by the specification: product, destination, case
status, the requirement tally, key issues, next actions, and the evidence map
chaining REQUIREMENT -> SOURCE -> DOCUMENT EVIDENCE -> FINDING.

Everything here is assembled from the case by modules.passport. Nothing on
this page is written by a model, and there is no score.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.rules import LABEL_GLYPH
from modules.passport import as_plain_text
from ui import theme
from ui.pages.dashboard import STATUS_TONE


def render() -> None:
    case = state.current_case()
    if case is None or case.passport is None:
        state.goto(state.Page.DASHBOARD if case else state.Page.LANDING)
        st.rerun()
        return

    passport = case.passport
    theme.masthead(f"CASE {case.case_id} &middot; RUN {passport.run_number}")

    st.markdown(
        '<div class="ba-eyebrow">BAAR-AAMAD Export Readiness Passport</div>'
        '<div class="ba-h1">Compliance Passport</div>',
        unsafe_allow_html=True,
    )
    theme.workflow_strip()

    theme.kv_table(
        [
            ("Product", passport.product),
            ("Destination", passport.destination),
            ("Case", passport.case_id),
        ]
    )

    theme.section("Case status")
    st.markdown(
        f'<div class="ba-status {STATUS_TONE[passport.case_status]}">'
        f"{passport.case_status.value}</div>",
        unsafe_allow_html=True,
    )

    theme.section("Requirements")
    st.markdown(
        '<div class="ba-tally">'
        + "".join(
            f'<div class="ba-tally-item"><span class="ba-tally-n">{count}</span>'
            f'<span class="ba-tally-l">{LABEL_GLYPH[label]} {label.value}</span></div>'
            for label, count in passport.requirement_tally.items()
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    theme.section("Key issues")
    if passport.key_issues:
        st.markdown(
            "".join(
                f'<div class="ba-numbered"><span>{i}</span>{issue}</div>'
                for i, issue in enumerate(passport.key_issues, 1)
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ba-para is-muted">Nothing outstanding.</div>',
            unsafe_allow_html=True,
        )

    theme.section("Next actions")
    if passport.next_actions:
        st.markdown(
            "".join(
                f'<div class="ba-numbered"><span>{i}</span>{action}</div>'
                for i, action in enumerate(passport.next_actions, 1)
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ba-para is-muted">Nothing outstanding.</div>',
            unsafe_allow_html=True,
        )

    theme.section("Evidence")
    st.markdown(
        '<div class="ba-para is-muted">Requirement &rarr; Source &rarr; '
        "Document evidence &rarr; Finding</div>",
        unsafe_allow_html=True,
    )
    for row in passport.evidence_map:
        source = (
            f'<a href="{row.source_url}" target="_blank" rel="noopener">{row.source}</a>'
            if row.source_url
            else row.source
        )
        st.markdown(
            f'<div class="ba-map">'
            f'<div class="ba-map-req">{row.requirement}</div>'
            f'<div class="ba-map-row"><b>Source</b> {source}</div>'
            f'<div class="ba-map-row"><b>Your documents</b> {row.document_evidence}</div>'
            f'<div class="ba-map-row"><b>Finding</b> {row.finding}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    with st.expander("Plain text version (to copy)"):
        st.code(as_plain_text(passport), language=None)

    theme.section("Next")
    left, middle, right = st.columns(3)
    with left:
        if st.button("← Back to findings", width="stretch"):
            state.goto(state.Page.DASHBOARD)
            st.rerun()
    with middle:
        if st.button("Action plan", width="stretch"):
            state.goto(state.Page.ACTION_PLAN)
            st.rerun()
    with right:
        if st.button("Recheck this case", width="stretch"):
            state.goto(state.Page.PROCESSING)
            st.rerun()

    theme.note(
        f"Generated {passport.generated_at:%d %b %Y, %H:%M} UTC from run "
        f"{passport.run_number} of this case. Run Recheck after any change to "
        "refresh it."
    )
    theme.disclaimer()
