"""
COVERAGE, ON SCREEN

The three-level model is computed correctly and has been for a while. What it
was not doing was reaching anybody: it lived in a stage message on a screen
that flashes past. These tests hold it on every surface that shows a result.

A reader who does not know the limits of what was checked cannot read the
findings correctly, so "it is in the data model" is not good enough.
"""

from __future__ import annotations

from core import llm, state
from core.schemas import Coverage, DocumentType
from modules.passport import as_plain_text, build_passport
from tests.test_create_case import GOOD, app, click, fill, submit
from tests.test_upload import PDF_MIME, certificate_pdf, invoice_pdf, packing_450_pdf


def body_of(at) -> str:
    return " ".join(m.value for m in at.markdown)


def attach(at, document_type, filename, data):
    at.selectbox(key="ba_upload_type").set_value(document_type)
    at.file_uploader[0].set_value((filename, data, PDF_MIME))
    click(at, "Attach document")
    return at


def walk(at, product: str = GOOD["product"]):
    click(at, "Start an export check")
    fill(at, product=product)
    submit(at)
    click(at, "Upload documents")
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())
    attach(at, DocumentType.CERTIFICATE_OF_ORIGIN, "origin.pdf", certificate_pdf())
    click(at, "Check against requirements")
    return at


# ---------------------------------------------------------------------------
# On every surface
# ---------------------------------------------------------------------------


def test_the_dashboard_states_the_coverage_level(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    body = body_of(walk(app()))
    assert "COVERED" in body
    assert "ba-cov" in body


def test_a_partially_covered_case_says_what_went_unassessed(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    body = body_of(walk(app(), product="ceramic floor tiles"))

    assert "PARTIALLY COVERED" in body
    assert "Not assessed" in body
    assert "ceramic floor tiles" in body
    assert "no curated source covers them" in body.lower()


def test_the_action_plan_repeats_the_coverage(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    at = walk(app(), product="ceramic floor tiles")
    click(at, "Action plan")
    body = body_of(at)

    assert "PARTIALLY COVERED" in body
    assert "Not assessed" in body


def test_the_passport_discloses_partial_coverage(monkeypatch):
    """A Passport that hides this overstates the work that was done."""
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    at = walk(app(), product="ceramic floor tiles")
    click(at, "Compliance Passport")
    body = body_of(at)

    assert "What was assessed" in body
    assert "PARTIALLY COVERED" in body
    assert "Not assessed" in body


def test_the_activity_view_shows_what_was_retrieved(monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    at = walk(app())
    click(at, "AI & agent activity")
    body = body_of(at)

    assert "What the corpus could speak to" in body
    assert "COVERED" in body


# ---------------------------------------------------------------------------
# And in the document itself
# ---------------------------------------------------------------------------


def test_coverage_travels_on_the_passport_object(full_case, corpus):
    from core.orchestrator import RunContext, run_to_completion

    run_to_completion(
        full_case,
        ctx=RunContext(use_ai=False, file_provider=lambda _: None, text_sink=lambda *_: None),
    )
    assert full_case.passport.coverage is not None
    assert full_case.passport.coverage.level is Coverage.COVERED


def test_the_plain_text_passport_states_coverage_before_findings(full_case, corpus):
    from core.orchestrator import RunContext, run_to_completion

    run_to_completion(
        full_case,
        ctx=RunContext(use_ai=False, file_provider=lambda _: None, text_sink=lambda *_: None),
    )
    text = as_plain_text(full_case.passport)

    assert "COVERAGE      COVERED" in text
    assert text.index("WHAT COULD BE ASSESSED") < text.index("REQUIREMENTS")


def test_the_plain_text_passport_lists_what_was_not_assessed(profile, corpus):
    from core.schemas import CaseProfile, ExportCase
    from modules.profile import build_profile
    from modules.requirements import build_requirements

    tiles = CaseProfile(
        product_raw="ceramic floor tiles", origin_country="Pakistan", destination="Germany"
    )
    build_profile(tiles, use_ai=False)
    case = ExportCase(case_id="BA-009", profile=tiles)
    result = build_requirements(tiles, corpus=corpus, use_ai=False)
    case.requirements = result.payload["requirements"]
    case.coverage = result.payload["coverage"]

    text = as_plain_text(build_passport(case))
    assert "COVERAGE      PARTIALLY COVERED" in text
    assert "WHAT WAS NOT ASSESSED" in text
    assert "ceramic floor tiles" in text


def test_a_fully_covered_case_lists_nothing_unassessed(full_case, corpus):
    from core.orchestrator import RunContext, run_to_completion

    run_to_completion(
        full_case,
        ctx=RunContext(use_ai=False, file_provider=lambda _: None, text_sink=lambda *_: None),
    )
    assert as_plain_text(full_case.passport).count("WHAT WAS NOT ASSESSED") == 0
