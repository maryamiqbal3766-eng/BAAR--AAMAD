"""
AI processing.

Runs the pipeline and shows each stage as it happens. The work is done here
and only here — never as a side effect of rendering another screen — because
Streamlit re-executes the script on every interaction and a pipeline that ran
on render would run again on every click.
"""

from __future__ import annotations

import streamlit as st

from core import orchestrator, state
from core.schemas import StageStatus
from ui import theme


def render() -> None:
    case = state.current_case()
    if case is None:
        state.goto(state.Page.LANDING)
        st.rerun()
        return

    rerunning = case.run_number > 0
    theme.masthead(f"CASE {case.case_id}")
    st.markdown(
        f'<div class="ba-eyebrow">Step 3 of 5 &middot; '
        f'{"Recheck" if rerunning else "Check"}</div>'
        f'<div class="ba-h1">{"Rechecking your case" if rerunning else "Analysing your case"}'
        "</div>"
        '<div class="ba-lede">BAAR-AAMAD is finding the requirements that apply '
        "to this shipment, reading your documents, and checking one against "
        "the other.</div>",
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Recheck" if rerunning else "Check")

    slots = {name: st.empty() for name in orchestrator.STAGE_ORDER}
    for name in orchestrator.STAGE_ORDER:
        slots[name].markdown(
            f'<div class="ba-stage is-waiting">{orchestrator.STAGE_LABELS[name]}</div>',
            unsafe_allow_html=True,
        )

    failed = False
    for outcome in orchestrator.run(case, ctx=state.run_context()):
        label = orchestrator.STAGE_LABELS[outcome.stage]
        if outcome.status is StageStatus.COMPLETE:
            slots[outcome.stage].markdown(
                f'<div class="ba-stage is-done">{label}'
                f'<span class="ba-stage-note">{outcome.message}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            failed = True
            slots[outcome.stage].markdown(
                f'<div class="ba-stage is-failed">{label}'
                f'<span class="ba-stage-note">{outcome.message}</span></div>',
                unsafe_allow_html=True,
            )

    state.touch_case()

    if failed:
        record = orchestrator.failed_stage(case)
        st.error(record.error if record else "This case could not be processed.")
        theme.note(
            "Your export case has been kept exactly as it was. Nothing has "
            "been guessed to fill the gap."
        )
        left, right = st.columns(2)
        with left:
            if st.button("Try again", type="primary", width="stretch"):
                st.rerun()
        with right:
            if st.button("Back to documents", width="stretch"):
                state.goto(state.Page.UPLOAD)
                st.rerun()
        theme.disclaimer()
        return

    state.goto(state.Page.DASHBOARD)
    st.rerun()
