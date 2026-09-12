"""
Readiness dashboard.

Findings grouped into the four priority bands the specification fixes, worst
first, so an exporter is never handed ten problems in arbitrary order.

There is no score here, by design. A case is described — ACTION REQUIRED,
VERIFICATION REQUIRED, READY FOR HUMAN REVIEW — never graded out of ten.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.rules import (
    LABEL_GLYPH,
    PRIORITY_ORDER,
    PRIORITY_SUBTITLE,
    case_status_for,
)
from core.schemas import AssessmentState, CaseStatus, Priority
from ui import theme

STATUS_TONE: dict[CaseStatus, str] = {
    CaseStatus.ACTION_REQUIRED: "is-action",
    CaseStatus.VERIFICATION_REQUIRED: "is-verify",
    CaseStatus.READY_FOR_HUMAN_REVIEW: "is-ready",
    CaseStatus.NOT_STARTED: "",
}

STATUS_MEANING: dict[CaseStatus, str] = {
    CaseStatus.ACTION_REQUIRED: (
        "Something in this case is missing or contradicts itself. Resolve the "
        "items below before this shipment is declared."
    ),
    CaseStatus.VERIFICATION_REQUIRED: (
        "Nothing is missing or contradictory, but some requirements cannot be "
        "settled from paperwork alone and need a person to confirm them."
    ),
    CaseStatus.READY_FOR_HUMAN_REVIEW: (
        "Every requirement BAAR-AAMAD can check is satisfied. Review the "
        "evidence yourself before you rely on it."
    ),
    CaseStatus.NOT_STARTED: "This case has not been analysed yet.",
}


def _finding_row(case, finding) -> None:
    requirement = case.requirement(finding.requirement_id)
    title = requirement.title if requirement else finding.requirement_id
    glyph = LABEL_GLYPH[finding.label]

    body, action = st.columns([5, 1.5])
    with body:
        st.markdown(
            f'<div class="ba-finding">'
            f'<div class="ba-finding-head">'
            f'<span class="ba-glyph">{glyph}</span> {title}'
            f'<span class="ba-finding-label">{finding.label.value}</span></div>'
            f'<div class="ba-finding-body">{finding.what_we_found}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with action:
        if st.button("Why?", key=f"why_{finding.finding_id}", width="stretch"):
            state.select_finding(finding.finding_id)
            state.goto(state.Page.FINDING)
            st.rerun()


def render() -> None:
    case = state.current_case()
    if case is None or not case.findings:
        state.goto(state.Page.LANDING if case is None else state.Page.UPLOAD)
        st.rerun()
        return

    status = case_status_for(case.findings)
    theme.masthead(f"CASE {case.case_id} &middot; RUN {case.run_number}")

    st.markdown(
        '<div class="ba-eyebrow">Export readiness</div>', unsafe_allow_html=True
    )
    st.markdown(
        f'<div class="ba-status {STATUS_TONE[status]}">{status.value}</div>'
        f'<div class="ba-lede">{STATUS_MEANING[status]}</div>',
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Explain")

    counts = {}
    for finding in case.findings:
        counts[finding.label] = counts.get(finding.label, 0) + 1
    theme.section("Requirements")
    st.markdown(
        '<div class="ba-tally">'
        + "".join(
            f'<div class="ba-tally-item"><span class="ba-tally-n">{count}</span>'
            f'<span class="ba-tally-l">{LABEL_GLYPH[label]} {label.value}</span></div>'
            for label, count in counts.items()
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    for priority in PRIORITY_ORDER:
        group = [f for f in case.findings if f.priority is priority]
        if not group:
            continue
        st.markdown(
            f'<div class="ba-band"><span class="ba-band-name">{priority.value}</span>'
            f'<span class="ba-band-sub">{PRIORITY_SUBTITLE[priority]}</span></div>',
            unsafe_allow_html=True,
        )
        for finding in group:
            _finding_row(case, finding)

    theme.section("Next")
    left, middle, right = st.columns(3)
    with left:
        if st.button("Action plan", type="primary", width="stretch"):
            state.goto(state.Page.ACTION_PLAN)
            st.rerun()
    with middle:
        if st.button("Compliance Passport", width="stretch"):
            state.goto(state.Page.PASSPORT)
            st.rerun()
    with right:
        if st.button("Fix documents", width="stretch"):
            state.goto(state.Page.UPLOAD)
            st.rerun()

    if st.button("Recheck this case", width="stretch"):
        state.goto(state.Page.PROCESSING)
        st.rerun()

    theme.note(
        "BAAR-AAMAD checks what your documents show against curated "
        "authoritative sources. Every finding below links to the source it "
        "came from. It is decision support, not a customs clearance."
    )
    theme.disclaimer()
