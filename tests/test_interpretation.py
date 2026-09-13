"""
RETRIEVED CHUNK -> AI INTERPRETATION -> STRUCTURED REQUIREMENT

The RAG step, exercised against a scripted model. These tests are the reason
the claim "the model interprets retrieved evidence" is allowed to be made:
they check that the passages actually reach the model, that the curated
answers do NOT, and that an ungrounded reading is rejected rather than shown.
"""

from __future__ import annotations

import json

import pytest

from core import llm
from core.schemas import CaseProfile, InterpretationSource
from modules.interpretation import (
    SYSTEM,
    build_prompt,
    gate,
    interpret,
    invented_citations,
)
from modules.requirements import build_requirements
from tests.test_llm import FakeClient, install


@pytest.fixture
def requirements(profile, corpus):
    return build_requirements(profile, corpus=corpus, use_ai=False).payload["requirements"]


@pytest.fixture(autouse=True)
def _clean_ledger():
    llm.clear_ledger()
    yield
    llm.clear_ledger()


def reading(**overrides) -> str:
    """A model response for REQ-COMMERCIAL-INVOICE, grounded by default."""
    entry = {
        "requirement_id": "REQ-COMMERCIAL-INVOICE",
        "title": "A commercial invoice for the goods",
        "what_is_required": (
            "You must be able to give customs an invoice describing the goods "
            "in this consignment."
        ),
        "why_required": "Customs needs it to check the declaration against the goods.",
        "when_it_applies": "On every consignment entering the customs territory.",
        "satisfying_evidence": ["A commercial invoice covering this consignment"],
        "needed_document_or_info": ["A commercial invoice"],
        "grounded_in": ["eu-ucc-952-2013#art163"],
    }
    entry.update(overrides)
    return json.dumps({"requirements": [entry]})


def ai_on(monkeypatch, response: str) -> FakeClient:
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "available_models", lambda refresh=False: {llm.PRIMARY_MODEL})
    llm.reset_cache()
    return install(monkeypatch, FakeClient([response]))


def find(requirements, requirement_id):
    return next(r for r in requirements if r.requirement_id == requirement_id)


# ---------------------------------------------------------------------------
# What the model is actually shown
# ---------------------------------------------------------------------------


def test_the_retrieved_passages_reach_the_model(profile, requirements):
    """If this fails, nothing in this file is RAG."""
    prompt, allowed, _ = build_prompt(profile, requirements)

    assert "eu-ucc-952-2013#art163" in allowed
    for requirement in requirements:
        for evidence in requirement.evidence:
            assert evidence.evidence_id in prompt
            assert evidence.excerpt in prompt, "the verbatim passage must be sent"


def test_the_case_reaches_the_model(profile, requirements):
    prompt, _, _ = build_prompt(profile, requirements)
    assert profile.product_raw in prompt
    assert profile.destination in prompt


def test_the_curated_answers_are_withheld(profile, requirements):
    """The model must read the law, not rephrase an answer it was handed."""
    prompt, _, _ = build_prompt(profile, requirements)

    for requirement in requirements:
        assert requirement.what_is_required not in prompt
        assert requirement.why_required not in prompt
        for item in requirement.satisfying_evidence:
            assert item not in prompt


def test_the_checks_are_never_offered_to_the_model(profile, requirements):
    """Deterministic validation is not the model's to influence."""
    prompt, _, _ = build_prompt(profile, requirements)
    for banned in ("fields_agree", "document_present", "fields_present", "quantity"):
        assert banned not in prompt


def test_the_system_prompt_forbids_inventing_citations():
    assert "word-for-word" in SYSTEM
    assert "do not invent" in SYSTEM.lower() or "never name" in SYSTEM.lower()


# ---------------------------------------------------------------------------
# The grounding gate
# ---------------------------------------------------------------------------


EVIDENCE = (
    "Article 163 The supporting documents required for the application of the "
    "provisions governing the customs procedure shall be in the declarant's "
    "possession. Union Customs Code Regulation (EU) No 952/2013"
)


def test_a_citation_present_in_the_evidence_is_fine():
    assert invented_citations("As Article 163 requires, keep the invoice.", EVIDENCE) == []


def test_a_citation_absent_from_the_evidence_is_caught():
    assert invented_citations("Article 12 also applies here.", EVIDENCE) == ["Article 12"]


def test_an_invented_regulation_number_is_caught():
    found = invented_citations("Under Regulation (EU) No 999/2001 you must...", EVIDENCE)
    assert found


def test_an_invented_url_is_caught():
    found = invented_citations("See https://example.org/rules for details.", EVIDENCE)
    assert found == ["https://example.org/rules"]


def test_the_gate_rejects_an_uncited_reading():
    _, _, reason = gate({"what_is_required": "x" * 40}, {"chunk-a"}, EVIDENCE)
    assert "cited no retrieved passage" in reason


def test_the_gate_rejects_a_citation_to_something_not_retrieved():
    """A hallucinated passage id taints the whole response."""
    accepted, _, reason = gate(
        {"what_is_required": "x" * 40, "grounded_in": ["chunk-that-does-not-exist"]},
        {"chunk-a"},
        EVIDENCE,
    )
    assert accepted == {}
    assert "not retrieved" in reason


def test_the_gate_accepts_a_grounded_reading():
    accepted, cited, reason = gate(
        {
            "what_is_required": "You must hold the supporting documents.",
            "satisfying_evidence": ["A commercial invoice"],
            "grounded_in": ["chunk-a"],
        },
        {"chunk-a"},
        EVIDENCE,
    )
    assert reason == ""
    assert cited == ["chunk-a"]
    assert accepted["what_is_required"].startswith("You must hold")


def test_the_gate_never_accepts_structural_fields():
    accepted, _, _ = gate(
        {
            "what_is_required": "You must hold the supporting documents.",
            "requirement_id": "REQ-SOMETHING-ELSE",
            "expected_document_types": ["COMMERCIAL_INVOICE"],
            "evidence": [{"evidence_id": "made-up"}],
            "verification_status": "SUPPORTED_BY_SOURCE",
            "grounded_in": ["chunk-a"],
        },
        {"chunk-a"},
        EVIDENCE,
    )
    for structural in (
        "requirement_id",
        "expected_document_types",
        "evidence",
        "verification_status",
    ):
        assert structural not in accepted


# ---------------------------------------------------------------------------
# End to end, with a scripted model
# ---------------------------------------------------------------------------


def test_a_grounded_reading_replaces_the_curated_wording(monkeypatch, profile, requirements):
    curated = find(requirements, "REQ-COMMERCIAL-INVOICE").what_is_required
    ai_on(monkeypatch, reading())

    interpret(profile, requirements)
    invoice = find(requirements, "REQ-COMMERCIAL-INVOICE")

    assert invoice.interpretation.source is InterpretationSource.AI_INTERPRETED
    assert invoice.what_is_required != curated
    assert "give customs an invoice" in invoice.what_is_required
    assert invoice.interpretation.grounded_in == ["eu-ucc-952-2013#art163"]
    assert invoice.interpretation.model == llm.PRIMARY_MODEL
    assert "what_is_required" in invoice.interpretation.fields_from_ai


def test_provenance_survives_into_the_requirement(monkeypatch, profile, requirements):
    """retrieved chunk -> interpretation -> requirement must be traceable."""
    ai_on(monkeypatch, reading())
    interpret(profile, requirements)

    invoice = find(requirements, "REQ-COMMERCIAL-INVOICE")
    cited = invoice.interpretation.grounded_in[0]
    assert cited in {e.evidence_id for e in invoice.evidence}


def test_an_ungrounded_reading_is_refused_and_says_why(monkeypatch, profile, requirements):
    curated = find(requirements, "REQ-COMMERCIAL-INVOICE").what_is_required
    ai_on(monkeypatch, reading(grounded_in=["some-passage-we-never-retrieved"]))

    interpret(profile, requirements)
    invoice = find(requirements, "REQ-COMMERCIAL-INVOICE")

    assert invoice.interpretation.source is InterpretationSource.CURATED
    assert invoice.what_is_required == curated
    assert "not retrieved" in invoice.interpretation.fallback_reason


def test_an_invented_citation_is_refused(monkeypatch, profile, requirements):
    curated = find(requirements, "REQ-COMMERCIAL-INVOICE").what_is_required
    ai_on(
        monkeypatch,
        reading(what_is_required="Under Article 12 you must hold an invoice for the goods."),
    )

    interpret(profile, requirements)
    invoice = find(requirements, "REQ-COMMERCIAL-INVOICE")

    assert invoice.interpretation.source is InterpretationSource.CURATED
    assert invoice.what_is_required == curated
    assert "citations not in the evidence" in invoice.interpretation.fallback_reason


def test_one_bad_reading_does_not_discard_the_others(monkeypatch, profile, requirements):
    good = json.loads(reading())["requirements"][0]
    bad = dict(good, requirement_id="REQ-PACKING-LIST", grounded_in=["invented-id"])
    ai_on(monkeypatch, json.dumps({"requirements": [good, bad]}))

    interpret(profile, requirements)

    assert find(requirements, "REQ-COMMERCIAL-INVOICE").interpretation.source is (
        InterpretationSource.AI_INTERPRETED
    )
    assert find(requirements, "REQ-PACKING-LIST").interpretation.source is (
        InterpretationSource.CURATED
    )


def test_a_requirement_cannot_be_supported_by_another_requirements_evidence(
    monkeypatch, profile, requirements
):
    """A customs passage must not be allowed to justify a chemical rule."""
    ai_on(
        monkeypatch,
        reading(requirement_id="REQ-CHROMIUM-VI", grounded_in=["eu-ucc-952-2013#art163"]),
    )
    interpret(profile, requirements)

    chromium = find(requirements, "REQ-CHROMIUM-VI")
    assert chromium.interpretation.source is InterpretationSource.CURATED
    assert "not retrieved" in chromium.interpretation.fallback_reason


def test_a_model_failure_keeps_every_curated_requirement(monkeypatch, profile, requirements):
    before = {r.requirement_id: r.what_is_required for r in requirements}
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "available_models", lambda refresh=False: {llm.PRIMARY_MODEL})
    llm.reset_cache()
    install(monkeypatch, FakeClient([Exception("network is down")] * llm.MAX_ATTEMPTS))

    interpret(profile, requirements)

    for requirement in requirements:
        assert requirement.what_is_required == before[requirement.requirement_id]
        assert requirement.interpretation.source is InterpretationSource.CURATED
        assert requirement.interpretation.fallback_reason


def test_without_a_key_the_fallback_is_recorded_not_silent(monkeypatch, profile, requirements):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    interpret(profile, requirements)

    assert llm.ledger()[0].call_site == "requirements.interpret_evidence"
    assert llm.ledger()[0].outcome is llm.Outcome.NOT_CONFIGURED
    assert requirements[0].interpretation.fallback_reason


def test_citations_are_never_touched_by_interpretation(monkeypatch, profile, requirements):
    before = {
        r.requirement_id: [(e.evidence_id, e.excerpt, e.source_url) for e in r.evidence]
        for r in requirements
    }
    ai_on(monkeypatch, reading())
    interpret(profile, requirements)

    for requirement in requirements:
        after = [(e.evidence_id, e.excerpt, e.source_url) for e in requirement.evidence]
        assert after == before[requirement.requirement_id]
