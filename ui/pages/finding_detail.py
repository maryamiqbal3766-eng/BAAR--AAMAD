"""
Requirement / evidence view — the "Why did BAAR-AAMAD flag this?" screen.

Answers the seven questions the specification requires of a requirement card,
then shows the six-link evidence chain behind the verdict:

    Requirement -> Source evidence -> Your document evidence
                -> Comparison -> Conclusion -> What you need to do

This is also the Human Review Gate. Where BAAR-AAMAD could not settle a
requirement, a person can record that they have verified it — and that
decision, not the system's, is what clears the item.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.rules import LABEL_GLYPH
from core.schemas import AssessmentState, HumanDecision
from ui import theme

CHAIN_LABELS = [
    ("requirement", "Requirement"),
    ("source_evidence", "Source evidence"),
    ("your_document_evidence", "Your document evidence"),
    ("comparison", "Comparison"),
    ("conclusion", "Conclusion"),
    ("what_you_need_to_do", "What you need to do"),
]


def _compared_values(finding) -> None:
    """The conflicting values side by side, when there are any.

    This is what makes a contradiction land: seeing 500 next to 450 rather
    than reading a sentence about them.
    """
    if finding.state is not AssessmentState.INCONSISTENT:
        return

    from modules.findings import _friendly

    cells: list[str] = []
    seen: set[str] = set()
    for check in finding.checks:
        if check.passed is not False:
            continue
        for key, value in check.compared.items():
            if value is None or key in seen:
                continue
            seen.add(key)
            cells.append(
                f'<div class="ba-compare-item">'
                f'<div class="ba-compare-k">{_friendly(key)}</div>'
                f'<div class="ba-compare-v">{value}</div></div>'
            )

    if cells:
        st.markdown(
            '<div class="ba-block"><div class="ba-block-label">The issue</div>'
            f'<div class="ba-compare">{"".join(cells)}</div></div>',
            unsafe_allow_html=True,
        )


def _human_review(case, finding) -> None:
    """Accept / Correct / Verify, per the Human Review Gate."""
    theme.section("Human review")

    if finding.human_decision is not HumanDecision.PENDING:
        st.success(
            f"Recorded as {finding.human_decision.value.lower()} by you. "
            "This item no longer counts against the case status."
        )
        if st.button("Undo this decision"):
            finding.human_decision = HumanDecision.PENDING
            state.touch_case()
            st.rerun()
        return

    if finding.state is AssessmentState.SATISFIED:
        theme.note(
            "BAAR-AAMAD found this requirement satisfied. Review the evidence "
            "above and confirm you agree."
        )
        return

    theme.note(
        "BAAR-AAMAD is decision support, not an authority. If you have "
        "confirmed this yourself — with your customs broker, a test report or "
        "the issuing body — record that here. Blockers are normally cleared by "
        "correcting the document and running Recheck instead."
    )

    left, middle, right = st.columns(3)
    with left:
        if st.button("Mark as verified", width="stretch"):
            finding.human_decision = HumanDecision.VERIFIED
            state.touch_case()
            st.rerun()
    with middle:
        if st.button("Accept as is", width="stretch"):
            finding.human_decision = HumanDecision.ACCEPTED
            state.touch_case()
            st.rerun()
    with right:
        if st.button("Fix documents", width="stretch"):
            state.goto(state.Page.UPLOAD)
            st.rerun()


def render() -> None:
    case = state.current_case()
    finding = state.selected_finding()
    if case is None or finding is None:
        state.goto(state.Page.DASHBOARD if case else state.Page.LANDING)
        st.rerun()
        return

    requirement = case.requirement(finding.requirement_id)
    trace = case.trace(finding.finding_id)

    theme.masthead(f"CASE {case.case_id}")
    st.markdown(
        f'<div class="ba-eyebrow">{LABEL_GLYPH[finding.label]} '
        f"{finding.label.value} &middot; {finding.priority.value}</div>"
        f'<div class="ba-h1">{requirement.title if requirement else finding.requirement_id}</div>',
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Explain")

    # --- the issue, at a glance ---------------------------------------------
    _compared_values(finding)

    # --- the seven questions, as scannable blocks ---------------------------
    theme.block("What you need", requirement.what_is_required)
    theme.block(
        "Why it matters",
        f"{requirement.why_required}\n\n{requirement.when_it_applies}",
    )
    theme.block("What BAAR-AAMAD found", finding.what_we_found)

    if finding.what_is_missing:
        theme.block("What is still needed", finding.what_is_missing)

    if finding.what_to_provide:
        st.markdown(
            '<div class="ba-block"><div class="ba-block-label">What to provide'
            "</div>"
            + "".join(
                f'<div class="ba-bullet">{item}</div>'
                for item in finding.what_to_provide
            )
            + "</div>",
            unsafe_allow_html=True,
        )

    theme.block("What to do", finding.next_action)

    # --- the evidence chain -------------------------------------------------
    theme.section("Evidence")
    if trace is None:
        theme.note("No explanation was recorded for this finding.")
    else:
        with st.expander("Why BAAR-AAMAD reached this conclusion", expanded=True):
            for index, (attribute, label) in enumerate(CHAIN_LABELS, start=1):
                theme.block(
                    f"{index}. {label}",
                    getattr(trace, attribute, ""),
                    evidence=attribute in ("source_evidence", "your_document_evidence"),
                )

    # --- citations ----------------------------------------------------------
    if requirement and requirement.evidence:
        theme.section("Sources")
        for evidence in requirement.evidence:
            locator = f" — {evidence.locator}" if evidence.locator else ""
            st.markdown(
                f'<div class="ba-source"><a href="{evidence.source_url}" '
                f'target="_blank" rel="noopener">{evidence.source_name}</a>'
                f"{locator}</div>",
                unsafe_allow_html=True,
            )

    _human_review(case, finding)

    st.markdown("")
    left, right = st.columns(2)
    with left:
        if st.button("← Back to findings", width="stretch"):
            state.goto(state.Page.DASHBOARD)
            st.rerun()
    with right:
        if st.button("Action plan", width="stretch"):
            state.goto(state.Page.ACTION_PLAN)
            st.rerun()

    theme.disclaimer()
