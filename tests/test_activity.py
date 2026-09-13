"""
THE AI & AGENT ACTIVITY VIEW

Two jobs: show what actually happened, and never show model reasoning.

The second is checked here as well as at the gateway, because this page is the
one surface where a well-meaning change would leak it.
"""

from __future__ import annotations

import json

import pytest

from core import agent, llm, state
from core.schemas import DocumentType
from tests.conftest import CERTIFICATE, INVOICE_500, PACKING_450
from tests.test_create_case import app, click, fill, submit
from tests.test_llm import FakeClient, install
from tests.test_upload import PDF_MIME, certificate_pdf, invoice_pdf, packing_450_pdf


def body_of(at) -> str:
    return " ".join(m.value for m in at.markdown)


def attach(at, document_type, filename, data):
    at.selectbox(key="ba_upload_type").set_value(document_type)
    at.file_uploader[0].set_value((filename, data, PDF_MIME))
    click(at, "Attach document")
    return at


def walk_to_activity(at):
    click(at, "Start an export check")
    fill(at)
    submit(at)
    click(at, "Upload documents")
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())
    attach(at, DocumentType.CERTIFICATE_OF_ORIGIN, "origin.pdf", certificate_pdf())
    click(at, "Check against requirements")
    click(at, "AI & agent activity")
    return at


@pytest.fixture(autouse=True)
def _clean_ledger():
    llm.clear_ledger()
    yield
    llm.clear_ledger()


# ---------------------------------------------------------------------------
# Reachable, and honest when there is no key
# ---------------------------------------------------------------------------


def test_the_activity_view_is_reachable_from_the_dashboard(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    at = walk_to_activity(app())
    assert not at.exception
    assert "AI & agent activity" in body_of(at) or "agent activity" in body_of(at)


def test_without_a_key_it_says_so_instead_of_implying_ai_ran(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    body = body_of(walk_to_activity(app()))

    assert "No API key is configured" in body
    assert "deterministic" in body.lower()
    assert "openai/gpt-oss-120b" in body  # still names the model it is built on


def test_the_fallbacks_are_listed_rather_than_hidden(monkeypatch):
    """A stage that quietly did nothing must not look like a stage that ran."""
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    body = body_of(walk_to_activity(app()))

    assert "NOT CONFIGURED" in body
    assert "requirements.interpret_evidence" in body


def test_every_requirement_shows_its_retrieved_passage(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    body = body_of(walk_to_activity(app()))

    assert "Retrieved passage" in body
    assert "eu-ucc-952-2013#art163" in body
    assert "Requirement produced" in body
    assert "CURATED WORDING" in body


# ---------------------------------------------------------------------------
# With a model answering
# ---------------------------------------------------------------------------


def ai_on(monkeypatch, moves):
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "available_models", lambda refresh=False: {llm.PRIMARY_MODEL})
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    llm.reset_cache()

    def route(kwargs):
        system = kwargs["messages"][0]["content"]
        if agent.SYSTEM in system:
            return None
        if "You are an export compliance analyst" in system:
            return json.dumps(
                {
                    "requirements": [
                        {
                            "requirement_id": "REQ-COMMERCIAL-INVOICE",
                            "what_is_required": (
                                "You must be able to hand customs an invoice for "
                                "the goods in this consignment."
                            ),
                            "grounded_in": ["eu-ucc-952-2013#art163"],
                        }
                    ]
                }
            )
        return "{}"

    return install(
        monkeypatch,
        FakeClient(moves, router=route, default='{"tool": "finish", "arguments": {}}'),
    )


def move(tool, **arguments):
    return json.dumps(
        {
            "tool": tool,
            "arguments": arguments,
            "looking_for": arguments.pop("looking_for", "establishing the facts"),
        }
    )


def test_an_ai_interpreted_requirement_is_labelled_as_such(monkeypatch):
    ai_on(monkeypatch, [move("finish", reason="done")])
    body = body_of(walk_to_activity(app()))

    assert "AI INTERPRETED" in body
    assert "hand customs an invoice" in body
    assert "openai/gpt-oss-120b" in body


def test_the_agent_steps_are_shown_with_tool_and_observation(monkeypatch):
    ai_on(
        monkeypatch,
        [
            move("list_documents"),
            move("run_requirement_checks", requirement_id="REQ-DOCUMENT-CONSISTENCY"),
            move("finish", reason="the contradiction is identified"),
        ],
    )
    body = body_of(walk_to_activity(app()))

    assert "list_documents" in body
    assert "run_requirement_checks" in body
    assert "Decided to continue" in body
    assert "Decided to stop" in body
    assert "Looking for:" in body


def test_the_call_log_shows_what_each_call_was_for(monkeypatch):
    ai_on(monkeypatch, [move("finish", reason="done")])
    body = body_of(walk_to_activity(app()))

    assert "agent.plan_step" in body
    assert "Choosing the agent's next tool" in body
    assert "tokens used" in body


# ---------------------------------------------------------------------------
# TS-2: no chain-of-thought, anywhere
# ---------------------------------------------------------------------------


def test_the_page_shows_no_model_reasoning(monkeypatch):
    """The gateway hides it; this makes sure the view never reintroduces it."""
    ai_on(monkeypatch, [move("finish", reason="done")])
    body = body_of(walk_to_activity(app())).lower()

    for leak in ("<think>", "chain of thought", "reasoning:", "step 1: i need to"):
        assert leak not in body


def test_no_prompt_text_reaches_the_page(monkeypatch):
    ai_on(monkeypatch, [move("finish", reason="done")])
    body = body_of(walk_to_activity(app()))

    assert agent.SYSTEM[:60] not in body
    assert "AVAILABLE TOOLS" not in body


def test_the_activity_record_carries_no_prompts_or_completions(monkeypatch):
    ai_on(monkeypatch, [move("finish", reason="done")])
    at = walk_to_activity(app())
    case = at.session_state["ba_case"]

    blob = json.dumps([c.model_dump() for c in case.llm_calls])
    assert "EXPORT CASE" not in blob
    assert "RETRIEVED PASSAGES" not in blob
    assert agent.SYSTEM[:40] not in blob
