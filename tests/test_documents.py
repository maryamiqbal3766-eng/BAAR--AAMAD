"""
BAAR-AAMAD — DOCUMENT INTELLIGENCE
==================================

Tested against the real demo PDFs in data/fixtures, not against invented
strings. The central case is the golden demo's contradiction:

    invoice_500.pdf       Quantity -> 500
    packing_list_450.pdf  Quantity -> 450

This module only reports what documents say. It must never conclude anything
about whether a requirement is satisfied — that is the Validation module's
job, and nothing here may pre-empt it.

Run:  .venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.schemas import DocumentEvidence, DocumentType, ExtractionMethod
from modules import documents
from modules.documents import (
    extract_fields,
    extract_text,
    identify_document_type,
    read_document,
    score_types,
)

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"

INVOICE = FIXTURES / "invoice_500.pdf"
PACKING_450 = FIXTURES / "packing_list_450.pdf"
PACKING_500 = FIXTURES / "packing_list_500.pdf"
CERTIFICATE = FIXTURES / "certificate_of_origin.pdf"
UNKNOWN = FIXTURES / "unknown_document.pdf"
NO_TEXT = FIXTURES / "scanned_no_text.pdf"


def load(path: Path) -> bytes:
    return path.read_bytes()


def evidence_for(document_type: DocumentType, filename: str) -> DocumentEvidence:
    return DocumentEvidence(
        document_id="DOC-001", filename=filename, document_type=document_type
    )


def read(path: Path, document_type: DocumentType):
    """Read a fixture as a given type. AI gap-fill off: deterministic only."""
    data = load(path)
    evidence = evidence_for(document_type, path.name)
    result = read_document(evidence, data, use_ai=False)
    return evidence, result


def test_every_fixture_exists():
    """If this fails, run data/fixtures/generate_fixtures.py."""
    for path in (INVOICE, PACKING_450, PACKING_500, CERTIFICATE, UNKNOWN, NO_TEXT):
        assert path.is_file(), f"missing fixture: {path.name}"


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def test_text_is_extracted_from_a_digital_pdf():
    extraction = extract_text(load(INVOICE))
    assert extraction.ok
    assert extraction.method is ExtractionMethod.NATIVE_TEXT
    assert extraction.page_count == 1
    assert "COMMERCIAL INVOICE" in extraction.text
    assert "INV-2026-0412" in extraction.text


def test_pdf_with_no_text_layer_is_reported_unreadable():
    """A scan, with no OCR toolchain installed: asked for, not guessed at."""
    extraction = extract_text(load(NO_TEXT))
    assert not extraction.ok
    assert extraction.method is ExtractionMethod.FAILED
    assert extraction.page_count == 1  # we still know how long it is
    assert extraction.failure
    assert "digital PDF" in extraction.failure


def test_corrupt_bytes_do_not_raise():
    extraction = extract_text(b"%PDF-1.7 this is not really a pdf body")
    assert not extraction.ok
    assert extraction.failure


def test_empty_bytes_do_not_raise():
    assert not extract_text(b"").ok


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (INVOICE, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
        (CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN),
    ],
)
def test_each_document_identifies_itself(path, expected):
    identified, score = identify_document_type(extract_text(load(path)).text)
    assert identified is expected
    assert score >= 0.6


def test_an_unrelated_document_is_not_forced_into_a_type():
    identified, score = identify_document_type(extract_text(load(UNKNOWN)).text)
    assert identified is DocumentType.UNSUPPORTED
    assert score == 0.0


def test_empty_text_identifies_as_unsupported():
    assert identify_document_type("") == (DocumentType.UNSUPPORTED, 0.0)


def test_a_packing_list_is_not_mistaken_for_an_invoice():
    """It quotes an invoice number, which must not outweigh its own title."""
    scores = score_types(extract_text(load(PACKING_450)).text)
    assert scores[DocumentType.PACKING_LIST] > scores[DocumentType.COMMERCIAL_INVOICE]


def test_a_certificate_is_not_mistaken_for_an_invoice():
    scores = score_types(extract_text(load(CERTIFICATE)).text)
    assert (
        scores[DocumentType.CERTIFICATE_OF_ORIGIN]
        > scores[DocumentType.COMMERCIAL_INVOICE]
    )


# ---------------------------------------------------------------------------
# Field extraction — the commercial invoice
# ---------------------------------------------------------------------------


def test_invoice_fields():
    evidence, result = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    assert result.ok
    assert evidence.readable
    assert evidence.extraction_method is ExtractionMethod.NATIVE_TEXT
    assert evidence.page_count == 1
    assert evidence.raw_text_length > 300

    assert evidence.get("invoice_number") == "INV-2026-0412"
    assert evidence.get("invoice_date") == "2026-09-02"
    assert evidence.get("exporter_name") == "Sialkot Leather Crafts (Pvt) Ltd"
    assert evidence.get("buyer_name") == "Hoffmann Lederwaren GmbH"
    assert evidence.get("country_of_origin") == "Pakistan"
    assert evidence.get("hs_code") == "4202.21"
    assert evidence.get("quantity") == "500"
    assert "leather shoulder bags" in evidence.get("product_description")


def test_address_lines_are_not_mistaken_for_names():
    """'Exporter Address:' must not be read as the exporter's name."""
    evidence, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    assert "Plot 14" not in evidence.get("exporter_name")
    assert "Gerberstrasse" not in evidence.get("buyer_name")


def test_every_extracted_field_keeps_the_line_it_came_from():
    evidence, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    for name, extracted in evidence.fields.items():
        assert extracted.raw_snippet, f"{name} has no source line"
        assert extracted.confidence == 1.0


# ---------------------------------------------------------------------------
# Field extraction — the packing lists, and the golden demo contradiction
# ---------------------------------------------------------------------------


def test_packing_list_450_fields():
    evidence, result = read(PACKING_450, DocumentType.PACKING_LIST)
    assert result.ok
    assert evidence.get("quantity") == "450"
    assert evidence.get("invoice_number") == "INV-2026-0412"
    assert evidence.get("packing_list_number") == "PL-2026-0412"
    assert evidence.get("packages") == "18"
    assert evidence.get("gross_weight") == "612.5"
    assert evidence.get("net_weight") == "540.0"


def test_the_golden_demo_contradiction_is_visible_in_the_evidence():
    """Invoice says 500, packing list says 450 — both read exactly."""
    invoice, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    packing, _ = read(PACKING_450, DocumentType.PACKING_LIST)

    assert invoice.get("quantity") == "500"
    assert packing.get("quantity") == "450"
    assert invoice.get("quantity") != packing.get("quantity")

    # and the two documents genuinely refer to the same shipment
    assert invoice.get("invoice_number") == packing.get("invoice_number")


def test_the_corrected_packing_list_agrees_with_the_invoice():
    """After the fix, the same extraction produces matching quantities."""
    invoice, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    packing, _ = read(PACKING_500, DocumentType.PACKING_LIST)
    assert invoice.get("quantity") == packing.get("quantity") == "500"


def test_quantities_are_reduced_to_bare_numbers():
    """'500 units' must arrive as 500 so comparison needs no re-parsing."""
    evidence, _ = read(PACKING_450, DocumentType.PACKING_LIST)
    assert evidence.get("quantity") == "450"
    assert "units" in evidence.fields["quantity"].raw_snippet  # original kept


# ---------------------------------------------------------------------------
# Field extraction — the certificate of origin
# ---------------------------------------------------------------------------


def test_certificate_fields():
    evidence, result = read(CERTIFICATE, DocumentType.CERTIFICATE_OF_ORIGIN)
    assert result.ok
    assert evidence.get("certificate_number") == "CO-PK-2026-8841"
    assert evidence.get("issue_date") == "2026-09-03"
    assert evidence.get("issuing_authority") == "Sialkot Chamber of Commerce and Industry"
    assert evidence.get("country_of_origin") == "Pakistan"
    assert evidence.get("invoice_number") == "INV-2026-0412"


# ---------------------------------------------------------------------------
# Only relevant fields
# ---------------------------------------------------------------------------


def test_only_fields_expected_for_the_type_are_extracted():
    """We do not harvest everything a document happens to contain."""
    invoice, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    assert set(invoice.fields) <= set(
        documents.FIELDS_BY_TYPE[DocumentType.COMMERCIAL_INVOICE]
    )
    # an invoice carries no packing figures
    assert "gross_weight" not in invoice.fields
    assert "packages" not in invoice.fields

    packing, _ = read(PACKING_450, DocumentType.PACKING_LIST)
    assert "incoterm" not in packing.fields
    assert "declared_value" not in packing.fields


def test_a_field_that_is_absent_is_simply_absent():
    """Nothing is filled in with a guess."""
    fields = extract_fields(DocumentType.COMMERCIAL_INVOICE, "COMMERCIAL INVOICE\n")
    assert fields == {}


def test_a_quantity_with_no_number_is_not_recorded():
    fields = extract_fields(
        DocumentType.PACKING_LIST, "PACKING LIST\nQuantity: to be confirmed\n"
    )
    assert "quantity" not in fields


# ---------------------------------------------------------------------------
# Mismatch and failure handling
# ---------------------------------------------------------------------------


def test_mismatch_is_reported_not_silently_corrected():
    """A packing list filed as an invoice keeps the exporter's choice."""
    evidence, result = read(PACKING_450, DocumentType.COMMERCIAL_INVOICE)

    assert result.ok
    assert result.payload["matches_selection"] is False
    assert result.payload["identified_type"] is DocumentType.PACKING_LIST
    assert evidence.document_type is DocumentType.COMMERCIAL_INVOICE  # unchanged


def test_confidence_reflects_the_assigned_type():
    right, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    wrong, _ = read(PACKING_450, DocumentType.COMMERCIAL_INVOICE)
    assert right.identification_confidence >= 0.6
    assert wrong.identification_confidence < right.identification_confidence


def test_unreadable_document_is_recorded_safely():
    evidence, result = read(NO_TEXT, DocumentType.COMMERCIAL_INVOICE)

    assert result.ok is False
    assert evidence.readable is False
    assert evidence.extraction_method is ExtractionMethod.FAILED
    assert evidence.unreadable_reason
    assert evidence.fields == {}
    assert evidence.raw_text_length == 0
    assert evidence.page_count == 1


def test_an_unrelated_pdf_is_read_but_yields_nothing_useful():
    evidence, result = read(UNKNOWN, DocumentType.COMMERCIAL_INVOICE)
    assert result.ok  # the text came out fine
    assert result.payload["identified_type"] is DocumentType.UNSUPPORTED
    assert result.payload["matches_selection"] is False
    assert evidence.fields == {}  # none of the expected values are there


# ---------------------------------------------------------------------------
# AI gap-fill — merge behaviour, without calling the API
# ---------------------------------------------------------------------------


def test_ai_is_skipped_when_no_key_is_configured(monkeypatch):
    from core import llm

    monkeypatch.setattr(llm, "is_configured", lambda: False)
    before = extract_fields(
        DocumentType.COMMERCIAL_INVOICE, extract_text(load(INVOICE)).text
    )
    after = documents.ai_fill_gaps(
        DocumentType.COMMERCIAL_INVOICE, extract_text(load(INVOICE)).text, dict(before)
    )
    assert after == before


def test_ai_fills_only_missing_fields_and_never_overwrites(monkeypatch):
    from core import llm

    text = "COMMERCIAL INVOICE\nInvoice No: INV-1\n"
    found = extract_fields(DocumentType.COMMERCIAL_INVOICE, text)
    assert found["invoice_number"].value == "INV-1"

    class FakeGaps:
        values = {
            "invoice_number": "WRONG-999",  # must be ignored: already known
            "buyer_name": "Hoffmann Lederwaren GmbH",  # must be accepted
            "quantity": "500 units",  # must be accepted, as a number
        }

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "complete_json", lambda **kwargs: FakeGaps())

    filled = documents.ai_fill_gaps(DocumentType.COMMERCIAL_INVOICE, text, dict(found))

    assert filled["invoice_number"].value == "INV-1"  # not overwritten
    assert filled["invoice_number"].confidence == 1.0
    assert filled["buyer_name"].value == "Hoffmann Lederwaren GmbH"
    assert filled["buyer_name"].confidence == 0.5  # lower than a verbatim read
    assert filled["quantity"].value == "500"  # normalized


def test_ai_failure_leaves_deterministic_fields_untouched(monkeypatch):
    from core import llm

    text = extract_text(load(INVOICE)).text
    found = extract_fields(DocumentType.COMMERCIAL_INVOICE, text)

    def boom(**kwargs):
        raise RuntimeError("groq is down")

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "complete_json", boom)

    assert documents.ai_fill_gaps(
        DocumentType.COMMERCIAL_INVOICE, text, dict(found)
    ) == found


def test_ai_nulls_are_ignored(monkeypatch):
    from core import llm

    text = "COMMERCIAL INVOICE\n"

    class FakeGaps:
        values = {"buyer_name": None, "quantity": "   "}

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "complete_json", lambda **kwargs: FakeGaps())

    assert documents.ai_fill_gaps(DocumentType.COMMERCIAL_INVOICE, text, {}) == {}


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_reading_reaches_no_conclusions():
    """Document Intelligence reports; it does not judge."""
    evidence, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    serialized = evidence.model_dump_json()
    for verdict in ("SATISFIED", "MISSING", "INCONSISTENT", "REQUIRES_VERIFICATION"):
        assert verdict not in serialized


def test_reading_is_repeatable():
    """The same PDF must always produce the same answer."""
    first, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    second, _ = read(INVOICE, DocumentType.COMMERCIAL_INVOICE)
    assert first.model_dump(exclude={"uploaded_at"}) == second.model_dump(
        exclude={"uploaded_at"}
    )
