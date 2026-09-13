"""
Document upload.

Accepts the three document types the MVP checks, stores them against the open
export case, and shows what is attached.

SCOPE — this screen only takes the file in at the door. It does not identify,
read, extract or OCR anything, and it must not imply that it has. Every
attached document stays marked NOT_ATTEMPTED until the Document Intelligence
module runs.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.errors import BaarAamadError, DocumentUnreadableError, UnsupportedDocumentError
from core.schemas import DocumentEvidence, DocumentType, ExtractionMethod
from modules import documents
from ui import theme

#: The three types the MVP checks, in the order an exporter thinks about them.
SUPPORTED_TYPES: list[DocumentType] = [
    DocumentType.COMMERCIAL_INVOICE,
    DocumentType.PACKING_LIST,
    DocumentType.CERTIFICATE_OF_ORIGIN,
]

TYPE_LABELS: dict[DocumentType, str] = {
    DocumentType.COMMERCIAL_INVOICE: "Commercial Invoice",
    DocumentType.PACKING_LIST: "Packing List",
    DocumentType.CERTIFICATE_OF_ORIGIN: "Certificate of Origin",
}

#: Every PDF begins with this signature, whatever the file is named.
PDF_MAGIC = b"%PDF-"

MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

_UPLOADER_SEQ = "ba_uploader_seq"
_LAST_MESSAGE = "ba_upload_message"

#: Field names shown in a friendly way. Anything not listed falls back to the
#: raw name with underscores replaced, so a new field never renders as blank.
FIELD_LABELS: dict[str, str] = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice Date",
    "issue_date": "Issue date",
    "certificate_number": "Certificate number",
    "issuing_authority": "Issuing authority",
    "packing_list_number": "Packing list number",
    "exporter_name": "Exporter",
    "buyer_name": "Consignee",
    "product_description": "Description of goods",
    "hs_code": "HS code",
    "country_of_origin": "Country of origin",
    "quantity": "Quantity",
    "declared_value": "Declared value",
    "incoterm": "Incoterm",
    "packages": "Packages",
    "gross_weight": "Gross weight (kg)",
    "net_weight": "Net weight (kg)",
}

METHOD_LABELS: dict[ExtractionMethod, str] = {
    ExtractionMethod.NOT_ATTEMPTED: "not read",
    ExtractionMethod.NATIVE_TEXT: "text layer",
    ExtractionMethod.OCR: "scanned, read by OCR",
    ExtractionMethod.FAILED: "could not be read",
}


def human_size(byte_count: int) -> str:
    """Readable file size. Exporters do not think in bytes."""
    if byte_count < 1024:
        return f"{byte_count} B"
    if byte_count < 1024 * 1024:
        return f"{byte_count / 1024:.0f} KB"
    return f"{byte_count / (1024 * 1024):.1f} MB"


def check_file(filename: str, data: bytes) -> None:
    """Accept or reject a file at the door. Raises a typed error if rejected.

    These are deterministic checks on the bytes themselves — no model, no
    parsing, no guessing what the document is.
    """
    if not data:
        raise DocumentUnreadableError(
            f"empty upload: {filename}",
            user_message=(
                f'"{filename}" is empty (0 bytes). Please check the file and '
                "upload it again."
            ),
        )

    if not filename.lower().endswith(".pdf"):
        raise UnsupportedDocumentError(
            f"not a pdf by extension: {filename}",
            user_message=(
                f'UNSUPPORTED DOCUMENT — "{filename}" is not a PDF. '
                "BAAR-AAMAD currently accepts PDF documents only."
            ),
        )

    if not data.startswith(PDF_MAGIC):
        raise DocumentUnreadableError(
            f"bad pdf signature: {filename}",
            user_message=(
                f'"{filename}" is named as a PDF but its contents are not a '
                "valid PDF. Please re-save or re-export it and try again."
            ),
        )

    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentUnreadableError(
            f"oversized upload: {len(data)} bytes",
            user_message=(
                f'"{filename}" is {human_size(len(data))}, which is over the '
                f"{MAX_UPLOAD_MB} MB limit. Please upload a smaller file."
            ),
        )


def _uploader_key() -> str:
    """A fresh key after each attach, so the uploader empties itself."""
    return f"ba_upload_{st.session_state.get(_UPLOADER_SEQ, 0)}"


def _status_line(document: DocumentEvidence) -> str:
    """One line summarising what reading the document produced."""
    parts = [human_size(document.size_bytes)]
    if document.page_count:
        parts.append(f"{document.page_count} page{'s' if document.page_count > 1 else ''}")
    parts.append(METHOD_LABELS[document.extraction_method])
    if document.readable and document.extracted:
        parts.append(f"{len(document.fields)} field{'s' if len(document.fields) != 1 else ''}")
    return " &middot; ".join(parts)


def _render_fields(document: DocumentEvidence) -> None:
    """The values read out of one document, with the line each came from."""
    if not document.readable:
        st.error(document.unreadable_reason)
        return
    if not document.fields:
        st.warning(
            "No expected values could be read from this document. The text was "
            "recovered, but none of the labelled fields BAAR-AAMAD looks for "
            "were found."
        )
        return

    theme.kv_table(
        [
            (
                FIELD_LABELS.get(name, name.replace("_", " ").title()),
                extracted.value or "",
            )
            for name, extracted in document.fields.items()
        ]
    )
    reported_by_model = [f for f in document.fields.values() if not f.raw_snippet]
    if reported_by_model:
        theme.note(
            f"{len(reported_by_model)} value(s) were reported by the AI reader "
            "because they were not in a labelled line. Check these carefully."
        )


def _render_slots() -> None:
    """One row per supported document type, attached or not."""
    for document_type in SUPPORTED_TYPES:
        document = state.document_for(document_type)
        label_col, detail_col, action_col = st.columns([3, 4, 1.4])

        label_col.markdown(
            f'<div class="ba-slot-key">{TYPE_LABELS[document_type]}</div>',
            unsafe_allow_html=True,
        )

        if document is None:
            detail_col.markdown(
                '<div class="ba-slot-val is-empty">Not uploaded</div>',
                unsafe_allow_html=True,
            )
            continue

        warning = "" if document.readable else " ba-unreadable"
        detail_col.markdown(
            f'<div class="ba-slot-val{warning}">{document.filename}'
            f'<span class="ba-slot-meta">{_status_line(document)}</span></div>',
            unsafe_allow_html=True,
        )
        if action_col.button(
            "Remove", key=f"rm_{document.document_id}", width="stretch"
        ):
            state.remove_document(document.document_id)
            st.rerun()

        with st.expander(f"What we read from {document.filename}"):
            _render_fields(document)


def render() -> None:
    case = state.current_case()
    if case is None:  # opened out of order, or the session was cleared
        state.goto(state.Page.LANDING)
        st.rerun()
        return

    theme.masthead(f"CASE {case.case_id}")
    st.markdown(
        '<div class="ba-eyebrow">Step 2 of 5 &middot; Check</div>'
        '<div class="ba-h1">Upload your documents</div>'
        '<div class="ba-lede">Attach the paperwork for this shipment as PDF '
        "files. BAAR-AAMAD checks these against the requirements for your "
        "product and destination.</div>",
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Check")

    # Result of the last attach, shown once after the rerun that stored it.
    message = st.session_state.pop(_LAST_MESSAGE, None)
    if message:
        kind, body = message
        {"error": st.error, "warning": st.warning, "success": st.success}[kind](body)

    theme.section("Documents for this case")
    _render_slots()

    theme.section("Attach a document")
    with st.form("attach_document", border=True):
        chosen_type = st.selectbox(
            "Document type",
            SUPPORTED_TYPES,
            format_func=lambda option: TYPE_LABELS[option],
            key="ba_upload_type",
        )
        uploaded = st.file_uploader(
            "PDF file",
            type=["pdf"],
            accept_multiple_files=False,
            key=_uploader_key(),
        )
        attach = st.form_submit_button("Attach document", type="primary")

    attached_count = len(state.documents())
    readable_count = sum(1 for d in state.documents() if d.readable)

    theme.section("Check this case")
    analysed = bool(case.findings)
    st.markdown(
        f'<div class="ba-para is-muted">{attached_count} of '
        f"{len(SUPPORTED_TYPES)} documents attached, {readable_count} readable."
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button(
        "Recheck this case" if analysed else "Check against requirements",
        type="primary",
        width="stretch",
    ):
        state.goto(state.Page.PROCESSING)
        st.rerun()

    left, right = st.columns([1, 1])
    with left:
        if st.button("← Back to case", width="stretch"):
            state.goto(state.Page.CASE_CREATED)
            st.rerun()
    with right:
        if analysed and st.button("View findings", width="stretch"):
            state.goto(state.Page.DASHBOARD)
            st.rerun()

    theme.note(
        "BAAR-AAMAD has read these documents and recorded what they say. "
        "<b>Nothing has been checked against export requirements yet</b> — no "
        "requirements have been identified for this case, and no document has "
        "been compared against another."
    )
    theme.disclaimer()

    if not attach:
        return

    if uploaded is None:
        st.error("Choose a PDF file before attaching.")
        return

    data = uploaded.getvalue()
    try:
        check_file(uploaded.name, data)
    except BaarAamadError as exc:
        st.error(exc.user_message)
        return

    replacing = state.document_for(chosen_type) is not None
    evidence = state.attach_document(chosen_type, uploaded.name, data)

    # Read it straight away, so the exporter sees what we actually found
    # rather than an inert filename.
    result = documents.read_document(evidence, data)
    state.set_document_text(evidence.document_id, result.payload.get("text", ""))
    state.touch_case()

    # Bump the uploader key so the control clears and the same file is not
    # re-attached on the next rerun.
    st.session_state[_UPLOADER_SEQ] = st.session_state.get(_UPLOADER_SEQ, 0) + 1

    if not result.ok:
        st.session_state[_LAST_MESSAGE] = ("error", result.reason)
    elif not result.payload.get("matches_selection", True):
        identified = result.payload.get("identified_type", DocumentType.UNSUPPORTED)
        if identified is DocumentType.UNSUPPORTED:
            note_text = (
                f'We read "{uploaded.name}", but its content does not look '
                f"like any document type BAAR-AAMAD checks. It has been kept "
                f"as a {TYPE_LABELS[chosen_type]} — please confirm that is "
                f"correct."
            )
        else:
            note_text = (
                f'You attached "{uploaded.name}" as a '
                f"{TYPE_LABELS[chosen_type]}, but its content reads like a "
                f"{TYPE_LABELS[identified]}. Please check you selected the "
                f"right type."
            )
        st.session_state[_LAST_MESSAGE] = ("warning", note_text)
    else:
        st.session_state[_LAST_MESSAGE] = (
            "success",
            f"{TYPE_LABELS[chosen_type]} "
            f"{'replaced' if replacing else 'attached'}: {uploaded.name} — "
            f"{len(evidence.fields)} field(s) read.",
        )

    st.rerun()
