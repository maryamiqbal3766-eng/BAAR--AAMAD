"""
Action plan, missing information checklist and preparation drafts.

Turns findings into work: what is wrong, why it matters, what to do, what to
provide, and where a document is missing entirely, a worksheet to help
prepare it.

Every draft carries DRAFT — FOR HUMAN VERIFICATION and says plainly that
BAAR-AAMAD does not issue official documents. That banner is not decoration.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.rules import LABEL_GLYPH, PRIORITY_ORDER, PRIORITY_SUBTITLE
from ui import theme
from ui.pages.upload import TYPE_LABELS


def _action_card(case, item, index: int) -> None:
    st.markdown(
        f'<div class="ba-action">'
        f'<div class="ba-action-n">{index}</div>'
        f'<div class="ba-action-main">'
        f'<div class="ba-action-problem">{item.problem}'
        f'<span class="ba-finding-label">{LABEL_GLYPH[item.status]} '
        f"{item.status.value}</span></div>"
        f'<div class="ba-action-row"><b>Why it matters</b> {item.why_it_matters}</div>'
        f'<div class="ba-action-row"><b>Action required</b> {item.action_required}</div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )
    if item.what_to_provide:
        st.markdown(
            '<div class="ba-action-provide"><b>What to provide</b></div>'
            + "".join(
                f'<div class="ba-bullet">{thing}</div>' for thing in item.what_to_provide
            ),
            unsafe_allow_html=True,
        )
    if st.button("Why was this flagged?", key=f"a_why_{item.action_id}"):
        state.select_finding(item.finding_id)
        state.goto(state.Page.FINDING)
        st.rerun()


def render() -> None:
    case = state.current_case()
    if case is None or not case.findings:
        state.goto(state.Page.DASHBOARD if case else state.Page.LANDING)
        st.rerun()
        return

    theme.masthead(f"CASE {case.case_id}")
    st.markdown(
        '<div class="ba-eyebrow">Step 4 of 5 &middot; Fix</div>'
        '<div class="ba-h1">What to do next</div>'
        '<div class="ba-lede">Everything outstanding on this case, most '
        "urgent first.</div>",
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Fix")

    if not case.action_plan:
        st.success(
            "There is nothing outstanding. Every requirement BAAR-AAMAD can "
            "check is satisfied — review the evidence before you rely on it."
        )
    else:
        for priority in PRIORITY_ORDER:
            group = [i for i in case.action_plan if i.priority is priority]
            if not group:
                continue
            st.markdown(
                f'<div class="ba-band"><span class="ba-band-name">{priority.value}'
                f'</span><span class="ba-band-sub">{PRIORITY_SUBTITLE[priority]}'
                f"</span></div>",
                unsafe_allow_html=True,
            )
            for offset, item in enumerate(group, start=1):
                _action_card(case, item, offset)

    if case.checklists:
        theme.section("Missing information")
        theme.note(
            "These documents were provided but do not carry everything the "
            "requirements ask for."
        )
        for checklist in case.checklists:
            st.markdown(
                f'<div class="ba-slot-key">{TYPE_LABELS.get(checklist.document_type, checklist.document_type.value)}</div>'
                + "".join(
                    f'<div class="ba-bullet">{field}</div>'
                    for field in checklist.missing_fields
                ),
                unsafe_allow_html=True,
            )

    if case.drafts:
        theme.section("Preparation help")
        theme.note(
            "Where a document is missing, BAAR-AAMAD can assemble a worksheet "
            "from what your case already contains. <b>This is not a "
            "certificate and BAAR-AAMAD does not issue official documents</b> "
            "— take it to the issuing body."
        )
        for draft in case.drafts:
            label = TYPE_LABELS.get(draft.document_type, draft.document_type.value)
            with st.expander(f"Draft worksheet — {label}"):
                st.markdown(
                    f'<div class="ba-draft-banner">{draft.banner}</div>',
                    unsafe_allow_html=True,
                )
                st.code(draft.body, language=None)
                st.caption(
                    "Prepared from " + ", ".join(draft.prepared_from) + ". " + draft.disclaimer
                )

    theme.section("Next")
    left, middle, right = st.columns(3)
    with left:
        if st.button("Upload corrected documents", type="primary", width="stretch"):
            state.goto(state.Page.UPLOAD)
            st.rerun()
    with middle:
        if st.button("Recheck this case", width="stretch"):
            state.goto(state.Page.PROCESSING)
            st.rerun()
    with right:
        if st.button("← Back to findings", width="stretch"):
            state.goto(state.Page.DASHBOARD)
            st.rerun()

    theme.disclaimer()
