"""
AI & AGENT ACTIVITY

What the model actually did on this run, in four parts:

    1  which model answered, and whether it is the one we claim
    2  retrieved passage -> AI interpretation -> structured requirement
    3  the agent loop: tool, observation, decision
    4  every model call: call site, latency, tokens, outcome

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Chain-of-thought. The gateway sets reasoning_format="hidden", so the model's
reasoning never arrives in this process at all — there is nothing on this page
that had to be filtered out, because there was never anything to filter. What
is shown are EVENTS: a call was made, a tool was run, a result came back, a
reading was accepted or refused.

A refusal is as informative as a success and is shown the same way. A page
that only displayed the AI working would be advertising, not observability.
"""

from __future__ import annotations

import streamlit as st

from core import llm, state
from core.schemas import AgentDecision, InterpretationSource
from ui import theme

OUTCOME_TONE = {
    "OK": "is-on",
    "REPAIRED": "is-warn",
    "FAILED": "is-bad",
    "NOT CONFIGURED": "is-off",
}

CALL_SITE_MEANING = {
    "profile.describe_product": "Describing the goods so retrieval can match them",
    "requirements.interpret_evidence": "Reading the retrieved passages into requirements",
    "documents.fill_field_gaps": "Reading fields the patterns could not find",
    "agent.plan_step": "Choosing the agent's next tool",
    "validation.semantic_comparison": "Judging whether two entries mean the same thing",
    "reasoning.explain_findings": "Putting a finding into plain language",
}


def _model_panel() -> None:
    report = llm.resolution_report()
    theme.section("Model")

    if not report.get("configured"):
        theme.note(
            "<b>No API key is configured in this environment.</b><br>"
            "Every stage below ran on its deterministic path, and the call log "
            "records each point where the model would have been used. Nothing "
            "on this page is simulated: if it says a call did not happen, it "
            "did not happen.",
        )
        theme.kv_table(
            [
                ("Model this app is built on", report.get("primary", "")),
                ("Status", "Not configured — deterministic fallback in use"),
            ]
        )
        return

    if report.get("error"):
        theme.note(f"The model could not be reached: {report['error']}")

    rows = [
        ("Model this app is built on", report.get("primary", "")),
        ("Serving REASONING calls", report.get("reasoning", "unresolved")),
        ("Serving FAST calls", report.get("fast", "unresolved")),
        ("Models offered by the provider", str(len(report.get("available", [])))),
    ]
    theme.kv_table(rows)

    if report.get("available") and not report.get("on_primary"):
        theme.note(
            "A fallback model is currently serving calls. Everything below was "
            "produced by the model named above, not by "
            f"{report.get('primary')}.",
            scope=True,
        )


def _interpretation_panel(case) -> None:
    theme.section("Retrieved evidence &rarr; AI interpretation")
    st.markdown(
        '<div class="ba-para is-muted">Requirements are not written from the '
        "model's memory. Each one below was produced from passages retrieved "
        "out of the curated corpus for this case, and the passage is shown "
        "beside the requirement it produced. Where the model's reading failed "
        "its grounding check, the curated wording is shown instead and the "
        "reason is stated.</div>",
        unsafe_allow_html=True,
    )

    if not case.requirements:
        theme.note("No requirements were found for this case.")
        return

    for requirement in case.requirements:
        interpretation = requirement.interpretation
        ai = interpretation.source is InterpretationSource.AI_INTERPRETED
        badge = "AI INTERPRETED" if ai else "CURATED WORDING"
        tone = "is-ai" if ai else "is-curated"

        st.markdown(
            f'<div class="ba-trace">'
            f'<div class="ba-trace-head">{requirement.title}'
            f'<span class="ba-tag {tone}">{badge}</span></div>',
            unsafe_allow_html=True,
        )

        for evidence in requirement.evidence:
            used = evidence.evidence_id in interpretation.grounded_in
            st.markdown(
                f'<div class="ba-trace-step"><b>Retrieved passage</b>'
                f'<span class="ba-pill">{evidence.evidence_id}'
                f'{" &middot; used" if used else ""}</span><br>'
                f'<span class="ba-quote">&ldquo;{evidence.excerpt}&rdquo;</span><br>'
                f'<span class="ba-cite">{evidence.source_name} &middot; '
                f'{evidence.locator}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div class="ba-trace-step"><b>Requirement produced</b><br>'
            f"{requirement.what_is_required}</div>",
            unsafe_allow_html=True,
        )

        if ai:
            st.markdown(
                f'<div class="ba-trace-foot">Written by {interpretation.model} '
                f"from {len(interpretation.grounded_in)} passage(s). "
                f"Fields interpreted: {', '.join(interpretation.fields_from_ai)}."
                "</div>",
                unsafe_allow_html=True,
            )
        elif interpretation.fallback_reason:
            st.markdown(
                '<div class="ba-trace-foot is-bad">Curated wording is shown '
                f"because {interpretation.fallback_reason}.</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)


def _agent_panel(case) -> None:
    theme.section("Agent loop")
    st.markdown(
        '<div class="ba-para is-muted">The model chooses one tool at a time '
        "from a fixed menu, Python runs it, and the result goes back so the "
        "model can decide what to look at next. It investigates; it does not "
        "decide. The deterministic checks below run in full afterwards "
        "whatever the agent did.</div>",
        unsafe_allow_html=True,
    )

    if not case.agent_steps:
        theme.note(
            "No agent steps were planned on this run — the AI service was "
            "unavailable. Every requirement was still checked deterministically."
        )
        return

    for step in case.agent_steps:
        arguments = ", ".join(f"{k}={v}" for k, v in step.arguments.items())
        decision = (
            "Decided to continue"
            if step.decision is AgentDecision.CONTINUE
            else "Decided to stop"
        )
        refused = step.observation.startswith("REFUSED")

        st.markdown(
            f'<div class="ba-move{" is-refused" if refused else ""}">'
            f'<div class="ba-move-head"><span class="ba-move-n">{step.step}</span>'
            f'<span class="ba-move-tool">{step.tool}({arguments})</span></div>'
            + (
                f'<div class="ba-move-why">Looking for: {step.rationale}</div>'
                if step.rationale
                else ""
            )
            + f'<div class="ba-move-obs">{step.observation}</div>'
            f'<div class="ba-move-decision">{decision}</div>'
            "</div>",
            unsafe_allow_html=True,
        )


def _calls_panel(case) -> None:
    theme.section("Model calls on this run")

    if not case.llm_calls:
        theme.note("No model calls were made on this run.")
        return

    total_tokens = sum(call.total_tokens for call in case.llm_calls)
    made = [c for c in case.llm_calls if c.outcome in ("OK", "REPAIRED")]
    st.markdown(
        '<div class="ba-tally">'
        f'<div class="ba-tally-item"><span class="ba-tally-n">{len(made)}</span>'
        '<span class="ba-tally-l">calls answered</span></div>'
        f'<div class="ba-tally-item"><span class="ba-tally-n">{total_tokens}</span>'
        '<span class="ba-tally-l">tokens used</span></div>'
        f'<div class="ba-tally-item"><span class="ba-tally-n">'
        f'{len(case.llm_calls) - len(made)}</span>'
        '<span class="ba-tally-l">fell back to deterministic</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )

    rows = ['<div class="ba-log">']
    rows.append(
        '<div class="ba-log-row is-head"><span>Call site</span><span>Model</span>'
        "<span>Outcome</span><span>Latency</span><span>Tokens</span></div>"
    )
    for call in case.llm_calls:
        tone = OUTCOME_TONE.get(call.outcome, "is-off")
        meaning = CALL_SITE_MEANING.get(call.call_site, "")
        # A dash means the call never left the process. A call that DID happen
        # reports its real numbers, including a genuine zero.
        happened = call.outcome != "NOT CONFIGURED"
        latency = f"{call.latency_ms} ms" if happened else "&mdash;"
        tokens = str(call.total_tokens) if happened else "&mdash;"
        rows.append(
            '<div class="ba-log-row">'
            f'<span><b>{call.call_site}</b>'
            + (f'<br><span class="ba-log-note">{meaning}</span>' if meaning else "")
            + "</span>"
            f"<span>{call.model or '&mdash;'}</span>"
            f'<span class="ba-doc-state {tone}">{call.outcome}</span>'
            f"<span>{latency}</span>"
            f"<span>{tokens}</span>"
            "</div>"
        )
        if call.detail:
            rows.append(f'<div class="ba-log-detail">{call.detail}</div>')
    rows.append("</div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def render() -> None:
    case = state.current_case()
    if case is None:
        state.goto(state.Page.LANDING)
        st.rerun()
        return

    theme.masthead(f"CASE {case.case_id} &middot; RUN {case.run_number}")
    st.markdown(
        '<div class="ba-eyebrow">Transparency</div>'
        '<div class="ba-h1">AI &amp; agent activity</div>'
        '<div class="ba-lede">Everything the model did on this run, and every '
        "point where it did not run and the deterministic path took over. No "
        "model reasoning is shown here, and none is collected.</div>",
        unsafe_allow_html=True,
    )

    _model_panel()

    theme.section("What the corpus could speak to")
    st.markdown(
        '<div class="ba-para is-muted">Retrieval runs before any model call. '
        "Nothing below could have been interpreted if nothing had been "
        "retrieved.</div>",
        unsafe_allow_html=True,
    )
    theme.coverage_banner(case.coverage)

    _interpretation_panel(case)
    _agent_panel(case)
    _calls_panel(case)

    theme.section("Back")
    left, right = st.columns(2)
    with left:
        if st.button("Readiness dashboard", type="primary", width="stretch"):
            state.goto(state.Page.DASHBOARD)
            st.rerun()
    with right:
        if st.button("Compliance Passport", width="stretch"):
            state.goto(state.Page.PASSPORT)
            st.rerun()

    theme.disclaimer()
