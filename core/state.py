"""
BAAR-AAMAD — SESSION STATE
==========================

Streamlit re-runs the whole script on every click. Anything not held in
`st.session_state` is lost. This module is the one place that owns that
state, so no page has to reach into raw session keys.

SCOPE — this is deliberately the minimum needed for:

    LANDING -> CREATE CASE -> CASE CREATED

There is no pipeline here yet. The eight-stage orchestrator arrives later.

Case IDs are sequential and human-readable (BA-001, BA-002, ...) and live for
the lifetime of the browser session, which is all the MVP requires.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import streamlit as st

from .schemas import CaseProfile, DocumentEvidence, DocumentType, ExportCase

CASE_ID_PREFIX = "BA"


class Page(str, Enum):
    """The screens that exist so far."""

    LANDING = "LANDING"
    CREATE_CASE = "CREATE_CASE"
    CASE_CREATED = "CASE_CREATED"
    UPLOAD = "UPLOAD"
    PROCESSING = "PROCESSING"
    DASHBOARD = "DASHBOARD"
    FINDING = "FINDING"
    ACTION_PLAN = "ACTION_PLAN"
    PASSPORT = "PASSPORT"


_PAGE = "ba_page"
_CASE = "ba_case"
_COUNTER = "ba_case_counter"
_FILES = "ba_files"
_TEXTS = "ba_texts"
_DOC_COUNTER = "ba_doc_counter"


# ---------------------------------------------------------------------------
# Case IDs
# ---------------------------------------------------------------------------


def format_case_id(number: int) -> str:
    """Render a case number as BA-001. Pure function, unit-testable."""
    return f"{CASE_ID_PREFIX}-{number:03d}"


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def init_session() -> None:
    """Create the session keys once. Safe to call on every rerun."""
    st.session_state.setdefault(_PAGE, Page.LANDING)
    st.session_state.setdefault(_CASE, None)
    st.session_state.setdefault(_COUNTER, 0)
    st.session_state.setdefault(_FILES, {})
    st.session_state.setdefault(_TEXTS, {})
    st.session_state.setdefault(_DOC_COUNTER, 0)


# --- navigation -------------------------------------------------------------


def current_page() -> Page:
    return st.session_state.get(_PAGE, Page.LANDING)


def goto(page: Page) -> None:
    st.session_state[_PAGE] = page


# --- the case ---------------------------------------------------------------


def current_case() -> ExportCase | None:
    return st.session_state.get(_CASE)


def has_case() -> bool:
    return current_case() is not None


def create_case(profile: CaseProfile) -> ExportCase:
    """Allocate the next Case ID and store a new case in the session."""
    st.session_state[_COUNTER] = st.session_state.get(_COUNTER, 0) + 1
    case = ExportCase(
        case_id=format_case_id(st.session_state[_COUNTER]),
        profile=profile,
    )
    st.session_state[_CASE] = case
    return case


def replace_case_profile(profile: CaseProfile) -> ExportCase | None:
    """Update the open case in place, keeping its Case ID.

    Used when the exporter edits details they already entered. A correction
    is not a new export case.
    """
    case = current_case()
    if case is None:
        return None
    case.profile = profile
    st.session_state[_CASE] = case
    return case


def clear_case() -> None:
    """Close the current case. The ID counter keeps going up."""
    st.session_state[_CASE] = None
    st.session_state[_FILES] = {}
    st.session_state[_TEXTS] = {}
    clear_form_fields()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
#
# The DocumentEvidence record lives inside the case, because it is part of the
# shared contract and must stay serializable. The raw PDF bytes do NOT: they
# are held beside the case in a session-scoped store, keyed by document_id.
#
# Nothing here reads the file. Identification, text extraction and OCR belong
# to the Document Intelligence module and have not run at this point.


def _file_store() -> dict[str, bytes]:
    return st.session_state.setdefault(_FILES, {})


def file_bytes(document_id: str) -> bytes | None:
    """The stored PDF for a document, or None if it is no longer held."""
    return _file_store().get(document_id)


def _text_store() -> dict[str, str]:
    return st.session_state.setdefault(_TEXTS, {})


def document_text(document_id: str) -> str:
    """Text recovered from a document. Empty until it has been read.

    Held beside the case for the same reason as the PDF bytes: the case object
    stays small and serializable.
    """
    return _text_store().get(document_id, "")


def set_document_text(document_id: str, text: str) -> None:
    _text_store()[document_id] = text


def documents() -> list[DocumentEvidence]:
    case = current_case()
    return list(case.documents) if case else []


def document_for(document_type: DocumentType) -> DocumentEvidence | None:
    return next((d for d in documents() if d.document_type is document_type), None)


def attach_document(
    document_type: DocumentType, filename: str, data: bytes
) -> DocumentEvidence:
    """Store an uploaded PDF against the open case.

    Re-uploading a type REPLACES the previous file rather than adding a second
    one — correcting a document is not the same as attaching another. That is
    what makes FIX -> RECHECK work later.
    """
    case = current_case()
    if case is None:
        raise RuntimeError("attach_document called with no open case")

    existing = document_for(document_type)
    if existing is not None:
        remove_document(existing.document_id)

    st.session_state[_DOC_COUNTER] = st.session_state.get(_DOC_COUNTER, 0) + 1
    document_id = f"DOC-{st.session_state[_DOC_COUNTER]:03d}"

    evidence = DocumentEvidence(
        document_id=document_id,
        filename=filename,
        document_type=document_type,
        size_bytes=len(data),
        # extraction_method stays NOT_ATTEMPTED: nothing has read this file.
    )
    _file_store()[document_id] = data
    case.documents.append(evidence)
    st.session_state[_CASE] = case
    return evidence


_SELECTED = "ba_selected_finding"


def select_finding(finding_id: str) -> None:
    st.session_state[_SELECTED] = finding_id


def selected_finding():
    """The finding whose detail page is open, or None."""
    case = current_case()
    finding_id = st.session_state.get(_SELECTED)
    return case.finding(finding_id) if case and finding_id else None


def run_context():
    """A pipeline RunContext wired to this session's stores."""
    from core.orchestrator import RunContext

    return RunContext(
        use_ai=True, file_provider=file_bytes, text_sink=set_document_text
    )


def touch_case() -> None:
    """Re-store the case after a module has mutated it in place.

    The object is already the one held in session state, so this is belt and
    braces — but it makes the write explicit at each call site.
    """
    case = current_case()
    if case is not None:
        st.session_state[_CASE] = case


def remove_document(document_id: str) -> None:
    """Detach a document and drop its bytes."""
    case = current_case()
    if case is None:
        return
    case.documents = [d for d in case.documents if d.document_id != document_id]
    _file_store().pop(document_id, None)
    _text_store().pop(document_id, None)
    st.session_state[_CASE] = case


# --- form fields ------------------------------------------------------------
# Form widgets own their own values via stable session_state keys. That is what
# keeps typing intact across Streamlit's reruns.
#
# Do NOT prefill a widget by passing `value=` a default that changes between
# runs: Streamlit derives widget identity partly from its arguments, so a
# moving default makes each rerun look like a brand-new widget and silently
# discards whatever the user typed. Use a fixed key instead.

FORM_PREFIX = "ba_f_"


def field_key(name: str) -> str:
    """Stable session_state key for one form field."""
    return f"{FORM_PREFIX}{name}"


def field_values() -> dict[str, Any]:
    """Everything currently held by the form widgets."""
    return {
        key.removeprefix(FORM_PREFIX): value
        for key, value in st.session_state.items()
        if key.startswith(FORM_PREFIX)
    }


def clear_form_fields() -> None:
    """Forget the form. Used when a case is closed."""
    for key in [k for k in st.session_state if k.startswith(FORM_PREFIX)]:
        del st.session_state[key]
