"""
Case created.

Shows the export case exactly as it was entered. Nothing on this screen is
produced by AI yet, and the screen says so plainly rather than showing an
empty analysis panel that implies work has happened.
"""

from __future__ import annotations

import streamlit as st

from core import state
from core.rules import case_status_for
from ui import theme
from ui.pages.upload import SUPPORTED_TYPES, TYPE_LABELS


def render() -> None:
    case = state.current_case()
    if case is None:  # session cleared, or opened out of order
        state.goto(state.Page.LANDING)
        st.rerun()
        return

    profile = case.profile
    theme.masthead(f"CASE {case.case_id}")

    st.markdown(
        '<div class="ba-eyebrow">Export case opened</div>', unsafe_allow_html=True
    )
    head_left, head_right = st.columns([1, 1])
    with head_left:
        st.markdown(
            f'<div class="ba-caseid">{case.case_id}</div>', unsafe_allow_html=True
        )
    with head_right:
        # Derived by the deterministic rule engine, not set by hand. With no
        # findings yet this is NOT STARTED, which is the honest answer.
        status = case_status_for(case.findings)
        st.markdown(
            f'<div style="text-align:right"><span class="ba-pill">'
            f"{status.value}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("")
    theme.workflow_strip("Find")

    theme.section("Case")
    theme.kv_table(
        [
            ("Product", profile.product_raw),
            ("Destination", profile.destination),
            ("Opened", case.created_at.strftime("%d %b %Y, %H:%M UTC")),
        ]
    )

    theme.section("Exporter")
    theme.kv_table(
        [
            ("Company", profile.exporter.name),
            ("Address", profile.exporter.address),
            ("Contact", profile.exporter.contact),
            ("NTN / reg. no.", profile.exporter.ntn_or_reg_no),
        ]
    )

    theme.section("Shipment")
    theme.kv_table(
        [
            ("Buyer / consignee", profile.shipment.buyer_name),
            ("Buyer address", profile.shipment.buyer_address),
            ("Invoice number", profile.shipment.invoice_number),
            ("Invoice date", profile.shipment.invoice_date),
            ("Quantity", profile.shipment.declared_quantity),
            ("Declared value", profile.shipment.declared_value),
            ("Incoterm", profile.shipment.incoterm),
        ]
    )

    theme.section("Documents")
    # All three slots are always shown, so a missing document is visible as an
    # absence rather than simply not being on the page.
    theme.kv_table(
        [
            (
                TYPE_LABELS[document_type],
                attached.filename if (attached := state.document_for(document_type)) else "",
            )
            for document_type in SUPPORTED_TYPES
        ]
    )

    theme.section("What happens next")
    theme.note(
        "Upload your Commercial Invoice, Packing List and Certificate of "
        "Origin. BAAR-AAMAD will then find the applicable requirements, read "
        "your documents, and check one against the other. <b>Nothing has been "
        "read or analysed yet</b> — no requirements have been identified for "
        "this case."
    )

    if st.button("Upload documents", type="primary", width="stretch"):
        state.goto(state.Page.UPLOAD)
        st.rerun()

    left, right = st.columns([1, 1])
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
