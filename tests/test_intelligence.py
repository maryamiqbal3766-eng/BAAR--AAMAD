"""
BAAR-AAMAD — REQUIREMENT INTELLIGENCE, VALIDATION AND FINDINGS
==============================================================

The heart of the system: does BAAR-AAMAD find the right requirements from
real sources, check them honestly against real documents, and reach the right
verdicts — including the golden demo's 500 vs 450 contradiction?

Every test here runs with use_ai=False, so what is proven is the
deterministic behaviour that must hold whether or not an API key is present.
"""

from __future__ import annotations

import pytest

from core.rules import case_status_for, label_for_state, priority_for_state
from core.schemas import (
    AssessmentState,
    CaseProfile,
    CaseStatus,
    CheckMethod,
    DocumentType,
    ExportCase,
    FindingLabel,
    Priority,
    VerificationStatus,
)
from modules import validation
from modules.corpus import CorpusError, load_corpus
from modules.findings import build_findings
from modules.profile import build_profile, normalize_product, product_terms
from modules.requirements import build_requirements, source_requirement_for
from modules.retrieval import search, tokenize

from tests.conftest import CERTIFICATE, INVOICE_500, PACKING_450, attach, build_case


# ---------------------------------------------------------------------------
# The corpus itself
# ---------------------------------------------------------------------------


def test_corpus_loads(corpus):
    assert corpus.sources
    assert corpus.chunks
    assert corpus.requirements


def test_every_chunk_has_a_real_citation(corpus):
    """No citation, no claim. Enforced at load time."""
    for chunk in corpus.chunks.values():
        assert chunk.text.strip()
        assert chunk.source_name.strip()
        assert chunk.source_url.startswith("https://")
        assert chunk.locator.strip()


def test_every_requirement_is_backed_by_a_chunk(corpus):
    for requirement in corpus.requirements:
        assert requirement.evidence_chunks
        for chunk_id in requirement.evidence_chunks:
            assert corpus.chunk(chunk_id) is not None


def test_requirement_ids_are_unique(corpus):
    ids = [r.requirement_id for r in corpus.requirements]
    assert len(ids) == len(set(ids))


def test_a_source_with_a_dangling_chunk_reference_is_rejected(tmp_path):
    (tmp_path / "bad.json").write_text(
        """
        {"source_id":"x","source_name":"X","source_url":"https://example.org",
         "chunks":[{"chunk_id":"x#1","locator":"1","text":"t"}],
         "requirements":[{"requirement_id":"R","title":"T","what_is_required":"w",
          "why_required":"y","when_it_applies":"a","evidence_chunks":["x#999"]}]}
        """,
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="unknown"):
        load_corpus(tmp_path)


def test_a_source_without_https_is_rejected(tmp_path):
    (tmp_path / "bad.json").write_text(
        '{"source_id":"x","source_name":"X","source_url":"http://example.org",'
        '"chunks":[{"chunk_id":"x#1","locator":"1","text":"t"}]}',
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="https"):
        load_corpus(tmp_path)


# ---------------------------------------------------------------------------
# Product understanding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description",
    [
        "Leather bags",
        "Handmade full-grain leather shoulder bags",
        "Basmati rice",
        "ceramic floor tiles",
        "surgical instruments",
        "lithium-ion battery packs",
    ],
)
def test_any_product_description_is_carried_through(description):
    """No product vocabulary lives in the application. Every case goes through."""
    normalized, characteristics = normalize_product(description)
    assert normalized == description
    assert characteristics == []


@pytest.mark.parametrize(
    "typed,expected",
    [
        ("  Leather   bags  ", "Leather bags"),
        ("Basmati rice.", "Basmati rice"),
        ("ceramic floor tiles,", "ceramic floor tiles"),
    ],
)
def test_normalization_only_tidies(typed, expected):
    """Whitespace and trailing punctuation, nothing else. The exporter's own
    capitalisation survives, because we quote their words back to them."""
    assert normalize_product(typed)[0] == expected


def test_an_empty_description_has_nothing_to_work_from():
    blank = CaseProfile(product_raw="   ", destination="Germany")
    result = build_profile(blank, use_ai=False)
    assert result.ok is False
    assert blank.product_normalized == ""


def test_no_product_category_is_invented():
    """The bug this replaced: everything nameable was called a leather article."""
    tiles = CaseProfile(product_raw="ceramic floor tiles", destination="Germany")
    build_profile(tiles, use_ai=False)
    terms = product_terms(tiles)
    assert "leather" not in terms
    assert terms == {"ceramic", "floor", "tile"}


def test_profile_never_states_a_classification(profile):
    """A tariff classification is a legal determination we do not make."""
    assert profile.classification_verification_status is (
        VerificationStatus.REQUIRES_VERIFICATION
    )
    assert "No tariff classification has been determined" in profile.classification_context


def test_the_exporters_own_words_reach_retrieval(profile):
    """What the corpus matches on comes from the exporter, not from code."""
    terms = product_terms(profile)
    assert {"leather", "bag"} <= terms
    assert "shoulder" in terms


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_tokenize_drops_stopwords():
    assert "the" not in tokenize("The leather and the bags")
    assert "leather" in tokenize("The leather and the bags")


def test_retrieval_finds_requirements_for_the_case(profile, corpus):
    hits = search(profile, corpus)
    assert hits
    assert all(hit.applicable for hit in hits)


def test_chromium_requirement_ranks_for_a_leather_bag(profile, corpus):
    hits = search(profile, corpus)
    assert "REQ-CHROMIUM-VI" in {hit.requirement.requirement_id for hit in hits}


def test_out_of_scope_destination_retrieves_nothing(corpus):
    elsewhere = CaseProfile(
        product_raw="Leather bags",
        product_normalized="Leather bags",
        destination="Japan",
    )
    assert search(elsewhere, corpus) == []


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


def test_requirements_are_built_with_citations(profile, corpus):
    result = build_requirements(profile, corpus=corpus, use_ai=False)
    assert result.ok
    requirements = result.payload["requirements"]
    assert len(requirements) >= 4

    for requirement in requirements:
        assert requirement.evidence, f"{requirement.requirement_id} has no evidence"
        for evidence in requirement.evidence:
            assert evidence.source_url.startswith("https://")
            assert evidence.excerpt.strip()


def test_requirement_without_checks_is_marked_for_verification(profile, corpus):
    """Chromium VI cannot be settled from an invoice, and says so."""
    result = build_requirements(profile, corpus=corpus, use_ai=False)
    chromium = next(
        r for r in result.payload["requirements"] if r.requirement_id == "REQ-CHROMIUM-VI"
    )
    assert chromium.verification_status is VerificationStatus.REQUIRES_VERIFICATION


def test_no_requirements_for_an_unsupported_market(corpus):
    elsewhere = CaseProfile(
        product_raw="Leather bags",
        product_normalized="Leather bags",
        destination="Japan",
    )
    result = build_requirements(elsewhere, corpus=corpus, use_ai=False)
    assert result.ok is False
    assert "cannot state the requirements" in result.reason
    assert result.payload["requirements"] == []


# ---------------------------------------------------------------------------
# Value comparison
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("500", "500", True),
        ("500", "450", False),
        ("500 units", "500 pcs", True),
        ("1,000", "1000", True),
        ("612.5", "612.50", True),
        ("500", "", None),
    ],
)
def test_number_comparison(left, right, expected):
    assert validation.values_agree(left, right, "number") is expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("Pakistan", "pakistan", True),
        ("Pakistan", "PAKISTAN ", True),
        ("Pakistan", "India", False),
        ("Sialkot Leather Crafts (Pvt) Ltd", "Sialkot Leather Crafts Limited", True),
        ("Hoffmann Lederwaren GmbH", "Hoffmann Lederwaren", True),
        ("INV-2026-0412", "INV-2026-0413", False),
    ],
)
def test_text_comparison(left, right, expected):
    assert validation.values_agree(left, right, "text") is expected


def test_numbers_never_reach_the_model(full_case, corpus, monkeypatch):
    """500 is not 450 in any wording. The model is not asked."""
    def explode(*args, **kwargs):
        raise AssertionError("the semantic engine was consulted about a number")

    monkeypatch.setattr(validation, "ai_same_thing", explode)
    findings = build_findings(full_case, corpus=corpus, use_ai=True)
    consistency = next(f for f in findings if f.requirement_id == "REQ-DOCUMENT-CONSISTENCY")
    assert consistency.state is AssessmentState.INCONSISTENT


# ---------------------------------------------------------------------------
# THE GOLDEN DEMO
# ---------------------------------------------------------------------------


def test_quantity_mismatch_is_detected(full_case, corpus):
    findings = build_findings(full_case, corpus=corpus, use_ai=False)
    consistency = next(f for f in findings if f.requirement_id == "REQ-DOCUMENT-CONSISTENCY")

    assert consistency.state is AssessmentState.INCONSISTENT
    assert consistency.label is FindingLabel.NEEDS_CORRECTION
    assert consistency.priority is Priority.MEDIUM
    assert "500" in consistency.what_we_found
    assert "450" in consistency.what_we_found


def test_the_mismatch_was_decided_by_python_not_a_model(full_case, corpus):
    findings = build_findings(full_case, corpus=corpus, use_ai=False)
    consistency = next(f for f in findings if f.requirement_id == "REQ-DOCUMENT-CONSISTENCY")
    quantity_check = next(
        c for c in consistency.checks if "quantity" in c.description.lower()
    )
    assert quantity_check.method is CheckMethod.DETERMINISTIC
    assert quantity_check.passed is False
    assert quantity_check.compared["COMMERCIAL_INVOICE.quantity"] == "500"
    assert quantity_check.compared["PACKING_LIST.quantity"] == "450"


def test_correcting_the_packing_list_clears_the_finding(fixed_case, corpus):
    """After FIX -> RECHECK the contradiction is gone."""
    findings = build_findings(fixed_case, corpus=corpus, use_ai=False)
    consistency = next(f for f in findings if f.requirement_id == "REQ-DOCUMENT-CONSISTENCY")

    assert consistency.state is AssessmentState.SATISFIED
    assert consistency.label is FindingLabel.COMPLETED
    assert consistency.what_is_missing == ""


def test_case_status_moves_from_action_required_to_verification(full_case, fixed_case, corpus):
    before = build_findings(full_case, corpus=corpus, use_ai=False)
    after = build_findings(fixed_case, corpus=corpus, use_ai=False)

    assert case_status_for(before) is CaseStatus.ACTION_REQUIRED
    # Chromium VI and proof of origin still need a human — correctly.
    assert case_status_for(after) is CaseStatus.VERIFICATION_REQUIRED


# ---------------------------------------------------------------------------
# Missing documents
# ---------------------------------------------------------------------------


def test_missing_certificate_is_reported_as_action_required(profile, corpus):
    case = build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
    )
    findings = build_findings(case, corpus=corpus, use_ai=False)
    origin = next(f for f in findings if f.requirement_id == "REQ-PROOF-OF-ORIGIN")

    assert origin.state is AssessmentState.MISSING
    assert origin.label is FindingLabel.ACTION_REQUIRED
    assert origin.priority is Priority.URGENT_HIGH
    assert origin.what_to_provide
    assert "Recheck" in origin.next_action


def test_a_case_with_no_documents_is_all_action_and_verification(profile, corpus):
    case = build_case(profile, corpus)
    findings = build_findings(case, corpus=corpus, use_ai=False)

    assert findings
    assert case_status_for(findings) is CaseStatus.ACTION_REQUIRED
    assert not any(f.state is AssessmentState.SATISFIED for f in findings)


def test_an_unreadable_document_does_not_count_as_provided(profile, corpus):
    from tests.conftest import SCANNED

    case = build_case(profile, corpus, (INVOICE_500, DocumentType.COMMERCIAL_INVOICE))
    attach(case, SCANNED, DocumentType.PACKING_LIST)

    findings = build_findings(case, corpus=corpus, use_ai=False)
    packing = next(f for f in findings if f.requirement_id == "REQ-PACKING-LIST")

    assert packing.state is AssessmentState.MISSING
    assert "could not be read" in packing.what_we_found


# ---------------------------------------------------------------------------
# Verification items
# ---------------------------------------------------------------------------


def test_chromium_finding_needs_a_human(full_case, corpus):
    findings = build_findings(full_case, corpus=corpus, use_ai=False)
    chromium = next(f for f in findings if f.requirement_id == "REQ-CHROMIUM-VI")

    assert chromium.state is AssessmentState.REQUIRES_VERIFICATION
    assert chromium.label is FindingLabel.VERIFICATION_REQUIRED
    assert chromium.priority is Priority.VERIFICATION
    assert chromium.checks == []  # nothing was claimed to have been checked
    assert chromium.what_to_provide


def test_proof_of_origin_stays_a_verification_item_even_with_a_certificate(
    full_case, corpus
):
    """A chamber certificate is not a REX statement on origin. We say so."""
    origin = next(
        f
        for f in build_findings(full_case, corpus=corpus, use_ai=False)
        if f.requirement_id == "REQ-PROOF-OF-ORIGIN"
    )
    assert origin.state is AssessmentState.REQUIRES_VERIFICATION
    assert "REX" in origin.next_action or "customs broker" in origin.next_action


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_findings_are_ordered_most_urgent_first(profile, corpus):
    case = build_case(profile, corpus, (INVOICE_500, DocumentType.COMMERCIAL_INVOICE))
    findings = build_findings(case, corpus=corpus, use_ai=False)
    ranks = [priority_for_state(f.state) for f in findings]
    order = [Priority.URGENT_HIGH, Priority.MEDIUM, Priority.VERIFICATION, Priority.SATISFIED]
    assert ranks == sorted(ranks, key=order.index)


def test_every_finding_answers_all_seven_questions(full_case, corpus):
    findings = build_findings(full_case, corpus=corpus, use_ai=False)
    for finding in findings:
        assert finding.what_was_checked
        assert finding.what_we_found
        assert finding.next_action
        assert finding.regulatory_evidence_ids  # question 7: why this conclusion
        assert finding.label is label_for_state(finding.state)
        assert finding.priority is priority_for_state(finding.state)
        if finding.state is not AssessmentState.SATISFIED:
            assert finding.what_is_missing


def test_no_finding_invents_a_source(full_case, corpus):
    findings = build_findings(full_case, corpus=corpus, use_ai=False)
    known = set(corpus.chunks)
    for finding in findings:
        assert set(finding.regulatory_evidence_ids) <= known


def test_assessment_is_repeatable(full_case, corpus):
    first = build_findings(full_case, corpus=corpus, use_ai=False)
    second = build_findings(full_case, corpus=corpus, use_ai=False)
    assert [f.model_dump() for f in first] == [f.model_dump() for f in second]
