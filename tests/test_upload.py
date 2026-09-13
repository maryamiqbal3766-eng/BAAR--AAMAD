"""
BAAR-AAMAD — DOCUMENT UPLOAD
============================

Covers:
  * the door checks on an uploaded file (pure, no Streamlit)
  * attaching 2-3 PDFs to a real case through the running app
  * documents staying attached across Streamlit reruns
  * the Case ID and case details surviving uploads
  * replacing and removing a document
  * rejection messages for empty, non-PDF, fake-PDF and oversized files

Attaching a document also READS it — Document Intelligence runs immediately,
so the exporter sees what was found rather than an inert filename. Reading is
not checking: no requirement or finding may exist at this point.

Run:  .venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

import pytest

from core.errors import DocumentUnreadableError, UnsupportedDocumentError
from core.schemas import DocumentType, ExtractionMethod
from ui.pages.upload import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_TYPES,
    TYPE_LABELS,
    check_file,
    human_size,
)

from tests.test_create_case import GOOD, app, click, fill, submit
from tests.test_documents import CERTIFICATE, INVOICE, PACKING_450, PACKING_500

PDF_MIME = "application/pdf"


def pdf_bytes(body: str = "invoice") -> bytes:
    """A PDF header with no real body.

    Enough to pass the door checks, which only look at the signature — but
    deliberately NOT a parseable PDF, so it also exercises the unreadable
    path. Attach-flow tests use the real fixtures below instead.
    """
    return b"%PDF-1.7\n% " + body.encode() + b"\n%%EOF\n"


def invoice_pdf() -> bytes:
    return INVOICE.read_bytes()


def packing_450_pdf() -> bytes:
    return PACKING_450.read_bytes()


def packing_500_pdf() -> bytes:
    return PACKING_500.read_bytes()


def certificate_pdf() -> bytes:
    return CERTIFICATE.read_bytes()


def open_case(at):
    """Create the golden-path case and land on the upload screen."""
    click(at, "Start an export check")
    fill(at)
    submit(at)
    click(at, "Upload documents")
    return at


def attach(at, document_type: DocumentType, filename: str, data: bytes):
    """Choose a type, pick a file, press Attach.

    Buttons are found by label: once a document is attached the page grows
    Remove buttons, so index-based clicking would hit the wrong control.
    """
    at.selectbox(key="ba_upload_type").set_value(document_type)
    at.file_uploader[0].set_value((filename, data, PDF_MIME))
    click(at, "Attach document")
    return at


def body_of(at) -> str:
    return " ".join(m.value for m in at.markdown)


def case_of(at):
    return at.session_state["ba_case"]


# ---------------------------------------------------------------------------
# Door checks (pure)
# ---------------------------------------------------------------------------


def test_a_real_pdf_is_accepted():
    check_file("invoice.pdf", invoice_pdf())  # must not raise


def test_empty_file_is_rejected():
    with pytest.raises(DocumentUnreadableError) as excinfo:
        check_file("invoice.pdf", b"")
    assert "empty" in excinfo.value.user_message.lower()
    assert "invoice.pdf" in excinfo.value.user_message


def test_non_pdf_extension_is_rejected_as_unsupported():
    with pytest.raises(UnsupportedDocumentError) as excinfo:
        check_file("invoice.docx", b"PK\x03\x04 some zip")
    assert "UNSUPPORTED DOCUMENT" in excinfo.value.user_message


def test_file_named_pdf_but_not_a_pdf_is_rejected():
    """Renaming a JPEG to .pdf must not get through."""
    with pytest.raises(DocumentUnreadableError) as excinfo:
        check_file("invoice.pdf", b"\xff\xd8\xff\xe0 JFIF junk")
    assert "not a valid PDF" in excinfo.value.user_message


def test_oversized_file_is_rejected():
    oversized = b"%PDF-1.7\n" + b"x" * MAX_UPLOAD_BYTES
    with pytest.raises(DocumentUnreadableError) as excinfo:
        check_file("huge.pdf", oversized)
    assert "limit" in excinfo.value.user_message


def test_extension_check_is_case_insensitive():
    check_file("INVOICE.PDF", invoice_pdf())  # must not raise


@pytest.mark.parametrize(
    ("size", "expected"),
    [(0, "0 B"), (512, "512 B"), (2048, "2 KB"), (5 * 1024 * 1024, "5.0 MB")],
)
def test_human_size(size, expected):
    assert human_size(size) == expected


def test_all_three_document_types_are_supported():
    assert SUPPORTED_TYPES == [
        DocumentType.COMMERCIAL_INVOICE,
        DocumentType.PACKING_LIST,
        DocumentType.CERTIFICATE_OF_ORIGIN,
    ]
    assert all(document_type in TYPE_LABELS for document_type in SUPPORTED_TYPES)


# ---------------------------------------------------------------------------
# Attaching, through the running app
# ---------------------------------------------------------------------------


def test_upload_screen_opens_from_the_case():
    at = open_case(app())
    assert not at.exception
    body = body_of(at)
    assert "Upload your documents" in body
    assert "BA-001" in body
    for label in TYPE_LABELS.values():
        assert label in body


def test_every_slot_starts_empty():
    at = open_case(app())
    assert body_of(at).count("Not uploaded") == 3
    assert len(case_of(at).documents) == 0


def test_attach_one_pdf():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())

    assert not at.exception
    documents = case_of(at).documents
    assert len(documents) == 1
    assert documents[0].filename == "invoice.pdf"
    assert documents[0].document_type is DocumentType.COMMERCIAL_INVOICE
    assert documents[0].size_bytes == len(invoice_pdf())
    assert "invoice.pdf" in body_of(at)


def test_attach_three_pdfs():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())
    attach(at, DocumentType.CERTIFICATE_OF_ORIGIN, "origin.pdf", certificate_pdf())

    documents = case_of(at).documents
    assert len(documents) == 3
    assert {d.document_type for d in documents} == set(SUPPORTED_TYPES)

    body = body_of(at)
    for filename in ("invoice.pdf", "packing.pdf", "origin.pdf"):
        assert filename in body
    assert "Not uploaded" not in body
    assert "3 of 3 documents attached" in body


def test_the_bytes_are_actually_stored():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())

    document = case_of(at).documents[0]
    assert at.session_state["ba_files"][document.document_id] == invoice_pdf()


def test_documents_are_read_on_attach():
    """Attaching runs Document Intelligence straight away."""
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())

    for document in case_of(at).documents:
        assert document.readable
        assert document.extraction_method is ExtractionMethod.NATIVE_TEXT
        assert document.extracted is True
        assert document.page_count == 1
        assert document.raw_text_length > 0
        assert document.fields  # values were read out

    invoice = next(
        d for d in case_of(at).documents
        if d.document_type is DocumentType.COMMERCIAL_INVOICE
    )
    assert invoice.get("quantity") == "500"


def test_extracted_text_is_stored_beside_the_case():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    document = case_of(at).documents[0]
    assert "COMMERCIAL INVOICE" in at.session_state["ba_texts"][document.document_id]


def test_reading_is_not_checking():
    """Reading a document says nothing about whether requirements are met."""
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    body = body_of(at)
    assert "Nothing has been checked against export requirements yet" in body
    assert case_of(at).findings == []
    assert case_of(at).requirements == []


def test_an_unreadable_pdf_is_attached_but_flagged():
    """A scan with no text layer: kept, marked unreadable, re-upload asked for."""
    at = open_case(app())
    scanned = (PACKING_450.parent / "scanned_no_text.pdf").read_bytes()
    attach(at, DocumentType.PACKING_LIST, "scan.pdf", scanned)

    document = case_of(at).documents[0]
    assert document.readable is False
    assert document.extraction_method is ExtractionMethod.FAILED
    assert document.fields == {}
    # once as a banner, once inside the document's own detail panel
    assert len(at.error) == 2
    assert all("digital PDF" in error.value for error in at.error)


def test_wrong_type_selection_is_flagged_not_silently_corrected():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "packing.pdf", packing_450_pdf())

    assert len(at.warning) == 1
    assert "reads like a Packing List" in at.warning[0].value
    # the exporter's choice stands; we asked rather than reassigned
    assert case_of(at).documents[0].document_type is DocumentType.COMMERCIAL_INVOICE


# ---------------------------------------------------------------------------
# Surviving reruns — the point of the step
# ---------------------------------------------------------------------------


def test_documents_survive_a_plain_rerun():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())

    at.run()  # what any widget interaction causes
    at.run()

    documents = case_of(at).documents
    assert len(documents) == 2
    assert {d.filename for d in documents} == {"invoice.pdf", "packing.pdf"}
    assert "invoice.pdf" in body_of(at)


def test_documents_and_case_survive_navigating_away_and_back():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())

    click(at, "Back to case")
    body = body_of(at)
    assert "BA-001" in body
    assert GOOD["buyer_name"] in body  # case details intact
    assert "invoice.pdf" in body  # documents listed on the case screen

    # once documents are attached, the case page offers "Manage documents"
    click(at, "Manage documents")
    assert len(case_of(at).documents) == 2
    assert "packing.pdf" in body_of(at)


def test_case_id_is_unchanged_by_uploading():
    at = open_case(app())
    before = case_of(at).case_id
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())
    assert case_of(at).case_id == before == "BA-001"


def test_editing_case_details_keeps_the_documents():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())

    click(at, "Back to case")
    click(at, "Edit case details")
    at.text_input(key="ba_f_quantity").set_value("450")
    submit(at)

    assert case_of(at).case_id == "BA-001"
    assert len(case_of(at).documents) == 1
    assert "450" in body_of(at)


# ---------------------------------------------------------------------------
# Replacing and removing
# ---------------------------------------------------------------------------


def test_reuploading_a_type_replaces_it():
    """A corrected document replaces the old one; it is not a second file."""
    at = open_case(app())
    attach(at, DocumentType.PACKING_LIST, "packing-450.pdf", packing_450_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing-500.pdf", packing_500_pdf())

    documents = case_of(at).documents
    assert len(documents) == 1
    assert documents[0].filename == "packing-500.pdf"

    body = body_of(at)
    assert "packing-500.pdf" in body
    assert "packing-450.pdf" not in body


def test_replacing_drops_the_old_bytes():
    at = open_case(app())
    attach(at, DocumentType.PACKING_LIST, "old.pdf", packing_450_pdf())
    old_id = case_of(at).documents[0].document_id

    attach(at, DocumentType.PACKING_LIST, "new.pdf", packing_500_pdf())
    assert old_id not in at.session_state["ba_files"]
    assert len(at.session_state["ba_files"]) == 1


def test_remove_detaches_the_document():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing_450_pdf())
    assert len(case_of(at).documents) == 2

    # the first Remove button on the page belongs to the Commercial Invoice
    click(at, "Remove")

    documents = case_of(at).documents
    assert len(documents) == 1
    assert documents[0].document_type is DocumentType.PACKING_LIST
    assert "invoice.pdf" not in body_of(at)


def test_closing_the_case_clears_the_files():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())

    click(at, "Back to case")
    click(at, "Close case and start over")

    assert at.session_state["ba_case"] is None
    assert at.session_state["ba_files"] == {}


# ---------------------------------------------------------------------------
# Rejections, through the running app
# ---------------------------------------------------------------------------


def test_attaching_nothing_is_refused():
    at = open_case(app())
    click(at, "Attach document")  # with no file chosen

    assert len(at.error) == 1
    assert "Choose a PDF file" in at.error[0].value
    assert len(case_of(at).documents) == 0


def test_empty_pdf_is_refused_in_the_app():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", b"")

    assert not at.exception
    assert len(at.error) == 1
    assert "empty" in at.error[0].value.lower()
    assert len(case_of(at).documents) == 0


def test_fake_pdf_is_refused_in_the_app():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", b"just some text")

    assert len(at.error) == 1
    assert "not a valid PDF" in at.error[0].value
    assert len(case_of(at).documents) == 0


def test_a_rejected_upload_leaves_earlier_documents_alone():
    at = open_case(app())
    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "broken.pdf", b"")

    assert len(at.error) == 1
    documents = case_of(at).documents
    assert len(documents) == 1
    assert documents[0].filename == "invoice.pdf"
