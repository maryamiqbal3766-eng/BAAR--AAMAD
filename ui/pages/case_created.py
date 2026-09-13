"""
Case overview.

A compact summary, the three document slots at a glance, and one clear next
step. Nothing on this screen is produced by AI, and it says so rather than
showing an empty analysis panel that implies work has happened.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.rules import case_status_for
from core.schemas import CaseStatus, DocumentType
from ui import theme
from ui.pages.upload import SUPPORTED_TYPES, TYPE_LABELS, human_size

STATUS_TONE: dict[CaseStatus, str] = {
    CaseStatus.ACTION_REQUIRED: "is-action",
    CaseStatus.VERIFICATION_REQUIRED: "is-verify",
    CaseStatus.READY_FOR_HUMAN_REVIEW: "is-ready",
    CaseStatus.NOT_STARTED: "",
}


def _route(profile) -> str:
    origin = profile.origin_country.strip() or "Origin not set"
    destination = profile.destination.strip() or "Destination not set"
    return f"{origin} &rarr; {destination}"


def document_row(document_type: DocumentType) -> None:
    """One compact row per supported document, attached or not."""
    document = state.document_for(document_type)
    label = TYPE_LABELS[document_type]

    if document is None:
        st.markdown(
            f'<div class="ba-doc"><div><div class="ba-doc-name">{label}</div>'
            f'<div class="ba-doc-meta is-empty">No file attached</div></div>'
            f'<div class="ba-doc-state is-off">Not uploaded</div></div>',
            unsafe_allow_html=True,
        )
        return

    if not document.readable:
        st.markdown(
            f'<div class="ba-doc"><div><div class="ba-doc-name">{label}</div>'
            f'<div class="ba-doc-meta is-bad">{document.filename} — could not '
            f'be read</div></div>'
            f'<div class="ba-doc-state is-bad">Unreadable</div></div>',
            unsafe_allow_html=True,
        )
        return

    detail = f"{document.filename} · {human_size(document.size_bytes)}"
    if document.extracted:
        detail += f" · {len(document.fields)} values read"
    st.markdown(
        f'<div class="ba-doc"><div><div class="ba-doc-name">{label}</div>'
        f'<div class="ba-doc-meta">{detail}</div></div>'
        f'<div class="ba-doc-state is-on">Uploaded</div></div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    case = state.current_case()
    if case is None:  # session cleared, or opened out of order
        state.goto(state.Page.LANDING)
        st.rerun()
        return

    profile = case.profile
    status = case_status_for(case.findings)

    theme.masthead(f"Case {case.case_id}")

    head_left, head_right = st.columns([2, 1])
    with head_left:
        st.markdown(
            f'<div class="ba-eyebrow">Export case</div>'
            f'<div class="ba-h1">{case.case_id}</div>',
            unsafe_allow_html=True,
        )
    with head_right:
        st.markdown(
            f'<div style="text-align:right;padding-top:1.6rem">'
            f'<span class="ba-status {STATUS_TONE[status]}">{status.value}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

    theme.workflow_strip("Find")

    theme.summary_grid(
        [
            ("Product", profile.product_raw),
            ("Route", _route(profile)),
            ("Exporter", profile.exporter.name),
            ("Shipment reference", profile.shipment.reference or profile.shipment.invoice_number),
        ]
    )

    theme.section("Documents")
    for document_type in SUPPORTED_TYPES:
        document_row(document_type)

    attached = len([d for d in state.documents() if d.readable])
    if attached:
        if st.button("Check against requirements", type="primary", width="stretch"):
            state.goto(state.Page.PROCESSING)
            st.rerun()
        if st.button("Manage documents", width="stretch"):
            state.goto(state.Page.UPLOAD)
            st.rerun()
    else:
        theme.section("What happens next")
        st.markdown(
            '<div class="ba-para">Upload your shipment documents. BAAR-AAMAD '
            "will find the requirements that apply, read what your documents "
            "say, and check one against the other.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Upload documents", type="primary", width="stretch"):
            state.goto(state.Page.UPLOAD)
            st.rerun()

    with st.expander("Full case details"):
        theme.kv_table(
            [
                ("Product", profile.product_raw),
                ("Origin country", profile.origin_country),
                ("Destination country", profile.destination),
                ("HS code (as declared by you)", profile.hs_code),
                ("Opened", case.created_at.strftime("%d %b %Y, %H:%M UTC")),
            ]
        )
        theme.kv_table(
            [
                ("Exporter", profile.exporter.name),
                ("Address", profile.exporter.address),
                ("Contact", profile.exporter.contact),
                ("Registration / tax no.", profile.exporter.ntn_or_reg_no),
            ]
        )
        theme.kv_table(
            [
                ("Buyer / consignee", profile.shipment.buyer_name),
                ("Buyer address", profile.shipment.buyer_address),
                ("Shipment reference", profile.shipment.reference),
                ("Invoice number", profile.shipment.invoice_number),
                ("Invoice date", profile.shipment.invoice_date),
                ("Quantity", profile.shipment.declared_quantity),
                ("Declared value", profile.shipment.declared_value),
                ("Incoterm", profile.shipment.incoterm),
            ]
        )

    left, right = st.columns(2)
    with left:
        if st.button("Edit case details", width="stretch"):
            state.goto(state.Page.CREATE_CASE)
            st.rerun()
    with right:
        if st.button("Close case and start over", width="stretch"):
            state.clear_case()
            state.goto(state.Page.LANDING)
            st.rerun()

    theme.disclaimer()
