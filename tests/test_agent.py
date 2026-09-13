"""
THE BOUNDED AGENT: PLAN -> USE TOOL -> OBSERVE -> DECIDE

Driven by a scripted model, so the loop's behaviour is decidable rather than
hoped for. The tests that matter most are the last group: whatever the agent
does, the deterministic verdict is identical to the verdict with no agent at
all. That is the safety claim, and it is checked rather than asserted in prose.
"""

from __future__ import annotations

import json

import pytest

from core import agent, llm
from core.orchestrator import RunContext, run_to_completion
from core.schemas import AgentDecision, DocumentType, StepOrigin
from tests.conftest import CERTIFICATE, INVOICE_500, PACKING_450, build_case
from tests.test_llm import FakeClient, install


@pytest.fixture
def case(profile, corpus):
    return build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
        (CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN),
    )


@pytest.fixture(autouse=True)
def _clean_ledger():
    llm.clear_ledger()
    yield
    llm.clear_ledger()


def move(tool: str, **arguments) -> str:
    looking_for = arguments.pop("looking_for", "checking something")
    return json.dumps(
        {"tool": tool, "arguments": arguments, "looking_for": looking_for}
    )


def ai_on(monkeypatch, moves: list[str]) -> FakeClient:
    """Script the agent loop. Every other call site gets an empty object, so a
    full pipeline run does not eat the script before the agent starts."""
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "available_models", lambda refresh=False: {llm.PRIMARY_MODEL})
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    llm.reset_cache()

    remaining = list(moves)

    def route(kwargs):
        system = kwargs["messages"][0]["content"]
        if agent.SYSTEM in system:
            return None  # fall through to the scripted list
        return "{}"  # some other call site; answer harmlessly

    client = FakeClient(remaining, router=route, default='{"tool": "", "arguments": {}}')
    return install(monkeypatch, client)


def agent_requests(client: FakeClient) -> list[dict]:
    """Only the requests the agent loop made."""
    return [
        request
        for request in client.requests
        if agent.SYSTEM in request["messages"][0]["content"]
    ]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_the_tool_menu_is_fixed():
    assert set(agent.TOOLS) == {
        "list_documents",
        "read_document_fields",
        "run_requirement_checks",
        "compare_field_across_documents",
        "finish",
    }


def test_an_unknown_tool_is_refused_not_executed(case):
    observation = agent.execute(case, "delete_everything", {})
    assert observation.startswith("REFUSED")
    assert "not an available tool" in observation


def test_a_document_type_that_is_not_attached_is_refused(case):
    observation = agent.execute(case, "read_document_fields", {"document_type": "INVENTED"})
    assert observation.startswith("REFUSED")


def test_a_requirement_not_on_the_case_is_refused(case):
    observation = agent.execute(
        case, "run_requirement_checks", {"requirement_id": "REQ-MADE-UP"}
    )
    assert observation.startswith("REFUSED")
    assert "REQ-COMMERCIAL-INVOICE" in observation  # tells it what does exist


def test_listing_documents_reports_what_is_attached(case):
    observation = agent.execute(case, "list_documents", {})
    assert "COMMERCIAL_INVOICE" in observation
    assert "PACKING_LIST" in observation
    assert "readable" in observation


def test_reading_fields_shows_what_a_document_states(case):
    observation = agent.execute(
        case, "read_document_fields", {"document_type": "COMMERCIAL_INVOICE"}
    )
    assert "quantity" in observation
    assert "500" in observation


def test_running_checks_returns_real_deterministic_results(case):
    observation = agent.execute(
        case, "run_requirement_checks", {"requirement_id": "REQ-DOCUMENT-CONSISTENCY"}
    )
    assert "FAILED" in observation
    assert "500" in observation and "450" in observation


def test_comparing_a_field_finds_the_contradiction(case):
    observation = agent.execute(
        case,
        "compare_field_across_documents",
        {"field": "quantity", "document_types": "COMMERCIAL_INVOICE,PACKING_LIST"},
    )
    assert "disagree" in observation
    assert "500" in observation and "450" in observation


def test_comparing_needs_two_documents(case):
    observation = agent.execute(
        case, "compare_field_across_documents", {"field": "quantity",
                                                 "document_types": "COMMERCIAL_INVOICE"}
    )
    assert observation.startswith("REFUSED")


def test_a_tool_never_raises_into_the_pipeline(case):
    """Any tool failure must come back as an observation."""
    assert agent.execute(case, "read_document_fields", {}).startswith("REFUSED")
    assert agent.execute(case, "compare_field_across_documents", {}).startswith("REFUSED")
    assert agent.execute(case, "run_requirement_checks", {}).startswith("REFUSED")


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def test_the_loop_runs_tools_and_records_every_step(monkeypatch, case):
    ai_on(
        monkeypatch,
        [
            move("list_documents", looking_for="what is attached"),
            move("run_requirement_checks", requirement_id="REQ-DOCUMENT-CONSISTENCY"),
            move("finish", reason="the contradiction is identified"),
        ],
    )
    investigation = agent.investigate(case)

    assert [s.tool for s in investigation.steps] == [
        "list_documents",
        "run_requirement_checks",
        "finish",
    ]
    assert investigation.steps[0].rationale == "what is attached"
    assert all(s.chosen_by is StepOrigin.MODEL for s in investigation.steps)
    assert "500" in investigation.steps[1].observation


def test_a_step_the_model_continued_from_is_marked_continue(monkeypatch, case):
    ai_on(monkeypatch, [move("list_documents"), move("finish", reason="done")])
    investigation = agent.investigate(case)

    assert investigation.steps[0].decision is AgentDecision.CONTINUE
    assert investigation.steps[-1].decision is AgentDecision.STOP


def test_the_observation_goes_back_to_the_model(monkeypatch, case):
    """Without this, it is a sequence of calls, not a loop."""
    client = ai_on(monkeypatch, [move("list_documents"), move("finish", reason="done")])
    agent.investigate(case)

    second_prompt = agent_requests(client)[1]["messages"][1]["content"]
    assert "WHAT YOU HAVE OBSERVED SO FAR" in second_prompt
    assert "Step 1: list_documents" in second_prompt
    assert "COMMERCIAL_INVOICE" in second_prompt


def test_a_refusal_goes_back_to_the_model_and_the_loop_continues(monkeypatch, case):
    client = ai_on(
        monkeypatch,
        [
            move("run_requirement_checks", requirement_id="REQ-INVENTED"),
            move("list_documents"),
            move("finish", reason="done"),
        ],
    )
    investigation = agent.investigate(case)

    assert investigation.steps[0].observation.startswith("REFUSED")
    assert len(investigation.steps) == 3
    assert "REFUSED" in agent_requests(client)[1]["messages"][1]["content"]


def test_the_step_limit_is_enforced_in_python(monkeypatch, case):
    """A model that never finishes must still stop."""
    ai_on(monkeypatch, [move("list_documents")] * 50)
    investigation = agent.investigate(case)

    assert len(investigation.steps) == agent.MAX_STEPS
    assert "step limit" in investigation.stopped_because


def test_the_call_limit_is_enforced_in_python(monkeypatch, case):
    monkeypatch.setattr(agent, "MAX_STEPS", 100)
    monkeypatch.setattr(agent, "MAX_LLM_CALLS", 3)
    ai_on(monkeypatch, [move("list_documents")] * 50)
    investigation = agent.investigate(case)

    assert investigation.llm_calls == 3
    assert "call limit" in investigation.stopped_because


def test_a_model_failure_ends_the_loop_quietly(monkeypatch, case):
    ai_on(monkeypatch, [move("list_documents")] + [Exception("gone")] * llm.MAX_ATTEMPTS)
    investigation = agent.investigate(case)

    assert len(investigation.steps) == 1
    assert "stopped responding" in investigation.stopped_because


def test_without_a_key_no_steps_are_planned_and_it_says_so(monkeypatch, case):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    investigation = agent.investigate(case)

    assert investigation.steps == []
    assert "not configured" in investigation.stopped_because
    assert llm.ledger()[0].call_site == "agent.plan_step"


def test_the_model_is_told_it_does_not_decide_compliance():
    assert "not deciding" in agent.SYSTEM.lower() or "do not state whether" in agent.SYSTEM.lower()
    assert "deterministic checks decide that" in agent.SYSTEM.lower()


# ---------------------------------------------------------------------------
# THE SAFETY PROPERTY
# ---------------------------------------------------------------------------


def _verdicts(case):
    return {f.finding_id: (f.state, f.label, f.priority) for f in case.findings}


def test_the_agent_cannot_change_a_single_verdict(monkeypatch, profile, corpus):
    """The claim this whole module rests on, checked rather than argued."""
    without = build_case(
        profile, corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
        (CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN),
    )
    run_to_completion(without, ctx=RunContext(use_ai=False, file_provider=lambda _: None,
                                              text_sink=lambda *_: None))

    ai_on(monkeypatch, [move("finish", reason="I looked at nothing at all")])
    with_agent = build_case(
        profile, corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
        (CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN),
    )
    run_to_completion(with_agent, ctx=RunContext(use_ai=True, file_provider=lambda _: None,
                                                 text_sink=lambda *_: None))

    assert _verdicts(with_agent) == _verdicts(without)
    assert with_agent.passport.case_status is without.passport.case_status


def test_every_mandatory_check_runs_even_if_the_agent_ran_none(monkeypatch, case):
    ai_on(monkeypatch, [move("finish", reason="skipping everything")])
    run_to_completion(case, ctx=RunContext(use_ai=True, file_provider=lambda _: None,
                                           text_sink=lambda *_: None))

    # The quantity contradiction is found regardless of what the agent chose.
    consistency = case.finding("F-REQ-DOCUMENT-CONSISTENCY")
    assert consistency is not None
    assert any(check.passed is False for check in consistency.checks)
    assert case.checks


def test_the_agents_steps_are_recorded_on_the_case(monkeypatch, case):
    ai_on(
        monkeypatch,
        [move("list_documents"), move("finish", reason="done")],
    )
    run_to_completion(case, ctx=RunContext(use_ai=True, file_provider=lambda _: None,
                                           text_sink=lambda *_: None))

    assert [s.tool for s in case.agent_steps] == ["list_documents", "finish"]
    assert case.llm_calls, "model calls must be attributed to the run"


def test_a_recheck_replaces_the_activity_rather_than_appending(monkeypatch, case):
    ctx = RunContext(use_ai=True, file_provider=lambda _: None, text_sink=lambda *_: None)

    ai_on(monkeypatch, [move("list_documents"), move("finish", reason="first run")])
    run_to_completion(case, ctx=ctx)
    first = len(case.agent_steps)

    ai_on(monkeypatch, [move("finish", reason="second run")])
    run_to_completion(case, ctx=ctx)

    assert first == 2
    assert len(case.agent_steps) == 1
    assert case.agent_steps[0].rationale != ""
