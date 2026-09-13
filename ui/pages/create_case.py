"""
Create Export Case.

Generic intake: any product, any origin, any destination. Whether BAAR-AAMAD
can actually advise on what is entered is decided afterwards, by the curated
corpus, and reported as coverage — it is not restricted at the door by a list
of products or markets.

Nothing here is inferred or invented. An HS code entered by the exporter is
recorded as theirs; BAAR-AAMAD does not determine classification.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import state
from core.schemas import CaseProfile, ExporterInfo, ShipmentInfo
from ui import theme

INCOTERMS = ["", "EXW", "FCA", "FOB", "CFR", "CIF", "CPT", "DAP", "DDP"]

#: GOLDEN DEMO SEED — the demonstration scenario, and nothing more.
#: These values pre-fill the form so the demo is quick to reach. They do not
#: define what the application supports.
DEMO_CASE: dict[str, str] = {
    "product": "Genuine leather handbags",
    "origin_country": "Pakistan",
    "destination": "Germany",
    "hs_code": "4202.21",
    "exporter_name": "Sialkot Leather Crafts (Pvt) Ltd",
    "exporter_address": "Plot 14, Small Industrial Estate, Sialkot, Punjab, Pakistan",
    "exporter_contact": "exports@sialkotleather.pk",
    "exporter_ntn": "3520212345678",
    "buyer_name": "Hoffmann Lederwaren GmbH",
    "buyer_address": "Gerberstrasse 22, 60313 Frankfurt am Main, Germany",
    "shipment_reference": "SHP-2026-0412",
    "invoice_number": "INV-2026-0412",
    "quantity": "500",
    "declared_value": "EUR 24,500",
    "incoterm": "FOB",
}

REQUIRED_FIELDS: dict[str, str] = {
    "product": "Tell us what you are exporting.",
    "origin_country": "Origin country is required.",
    "destination": "Destination country is required.",
    "exporter_name": "Exporter company name is required.",
    "buyer_name": "Buyer or consignee name is required.",
    "invoice_number": "Invoice number is required.",
    "quantity": "Quantity is required.",
}


def load_demo() -> None:
    """Populate the form with the golden demo scenario.

    Writes into the form's own widget keys, so it behaves exactly as if the
    exporter had typed it. The demo fixtures on disk are not touched.
    """
    for name, value in DEMO_CASE.items():
        st.session_state[state.field_key(name)] = value
    st.session_state[state.field_key("invoice_date")] = date(2026, 9, 2)


def _validate(values: dict) -> list[str]:
    """Deterministic input checks. Returns plain-language problems."""
    problems = [
        message
        for name, message in REQUIRED_FIELDS.items()
        if not str(values.get(name, "")).strip()
    ]

    quantity = str(values.get("quantity", "")).strip()
    if quantity and not any(character.isdigit() for character in quantity):
        problems.append(
            f'Quantity must include a number — "{quantity}" does not. '
            "For example: 500, or 500 units."
        )
    return problems


def _build_profile(values: dict) -> CaseProfile:
    """Map the form onto the shared contract. No AI fields are filled in."""
    return CaseProfile(
        product_raw=values["product"].strip(),
        origin_country=values["origin_country"].strip(),
        destination=values["destination"].strip(),
        hs_code=values["hs_code"].strip(),
        exporter=ExporterInfo(
            name=values["exporter_name"].strip(),
            address=values["exporter_address"].strip(),
            contact=values["exporter_contact"].strip(),
            ntn_or_reg_no=values["exporter_ntn"].strip(),
        ),
        shipment=ShipmentInfo(
            buyer_name=values["buyer_name"].strip(),
            buyer_address=values["buyer_address"].strip(),
            reference=values["shipment_reference"].strip(),
            invoice_number=values["invoice_number"].strip(),
            invoice_date=values["invoice_date"],
            declared_quantity=values["quantity"].strip(),
            declared_value=values["declared_value"].strip(),
            incoterm=values["incoterm"],
        ),
    )


def _seed_from_case() -> None:
    """Prefill the form from the open case when the widgets have no value.

    Streamlit discards widget state for widgets that were not rendered on the
    previous run, so arriving here from the case screen can find the keys
    empty. The case is the durable record, so seed from that.
    """
    case = state.current_case()
    if case is None or case.profile is None:
        return
    if state.field_key("product") in st.session_state:
        return  # the form already holds what the user typed

    profile = case.profile
    shipment, exporter = profile.shipment, profile.exporter

    try:
        parsed_date = date.fromisoformat(shipment.invoice_date)
    except ValueError:
        parsed_date = None

    seed = {
        "product": profile.product_raw,
        "origin_country": profile.origin_country,
        "destination": profile.destination,
        "hs_code": profile.hs_code,
        "exporter_name": exporter.name,
        "exporter_address": exporter.address,
        "exporter_contact": exporter.contact,
        "exporter_ntn": exporter.ntn_or_reg_no,
        "buyer_name": shipment.buyer_name,
        "buyer_address": shipment.buyer_address,
        "shipment_reference": shipment.reference,
        "invoice_number": shipment.invoice_number,
        "invoice_date": parsed_date,
        "quantity": shipment.declared_quantity,
        "declared_value": shipment.declared_value,
        "incoterm": shipment.incoterm if shipment.incoterm in INCOTERMS else "",
    }
    for name, value in seed.items():
        st.session_state[state.field_key(name)] = value


def render() -> None:
    editing = state.has_case()
    case = state.current_case()
    _seed_from_case()

    theme.masthead(f"Case {case.case_id} · Editing" if editing else "New export case")

    st.markdown(
        f'<div class="ba-eyebrow">Step 1 of 5 · Find</div>'
        f'<div class="ba-h1">{"Edit export case" if editing else "Create export case"}'
        "</div>"
        '<div class="ba-lede">Tell BAAR-AAMAD what you are shipping, where it '
        "comes from and where it is going. These details are compared against "
        "your documents later, so enter them as they appear on your "
        "paperwork.</div>",
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Find")

    if not editing:
        left, right = st.columns([1, 2])
        with left:
            if st.button("Load golden demo", width="stretch"):
                load_demo()
                st.rerun()
        with right:
            st.markdown(
                '<div class="ba-para is-muted" style="padding-top:.55rem">'
                "Fills the form with the demonstration shipment.</div>",
                unsafe_allow_html=True,
            )

    key = state.field_key  # stable widget identity; see core.state for why

    with st.form("create_case", border=True):
        theme.section("Export route")
        product = st.text_input(
            "What are you exporting? *",
            key=key("product"),
            placeholder="e.g. leather handbags, ceramic tiles, cotton garments",
        )

        col_a, col_b, col_c = st.columns([1, 1, 1])
        origin_country = col_a.text_input(
            "Origin country *", key=key("origin_country"), placeholder="e.g. Pakistan"
        )
        destination = col_b.text_input(
            "Destination country *", key=key("destination"), placeholder="e.g. Germany"
        )
        hs_code = col_c.text_input(
            "HS code (optional)", key=key("hs_code"), placeholder="e.g. 4202.21"
        )

        st.markdown(
            '<div class="ba-para is-muted">BAAR-AAMAD uses the authoritative '
            "evidence it holds for your product, origin and destination. "
            "Coverage varies, and the check will tell you exactly what it "
            "could and could not assess. Any HS code you enter is recorded as "
            "yours — BAAR-AAMAD does not determine classification.</div>",
            unsafe_allow_html=True,
        )

        theme.section("Exporter")
        exporter_name = st.text_input("Company name *", key=key("exporter_name"))
        exporter_address = st.text_area(
            "Address", key=key("exporter_address"), height=80
        )
        col_d, col_e = st.columns(2)
        exporter_contact = col_d.text_input(
            "Contact (email or phone)", key=key("exporter_contact")
        )
        exporter_ntn = col_e.text_input(
            "Registration / tax number", key=key("exporter_ntn")
        )

        theme.section("Shipment")
        buyer_name = st.text_input(
            "Buyer / consignee *", key=key("buyer_name")
        )
        buyer_address = st.text_area(
            "Buyer address", key=key("buyer_address"), height=80
        )

        col_f, col_g = st.columns(2)
        shipment_reference = col_f.text_input(
            "Shipment reference", key=key("shipment_reference")
        )
        invoice_number = col_g.text_input("Invoice number *", key=key("invoice_number"))

        col_h, col_i = st.columns(2)
        invoice_date = col_h.date_input(
            "Invoice Date", value=None, format="YYYY-MM-DD", key=key("invoice_date")
        )
        quantity = col_i.text_input(
            "Quantity *", key=key("quantity"), placeholder="e.g. 500"
        )

        col_j, col_k = st.columns(2)
        declared_value = col_j.text_input(
            "Declared value", key=key("declared_value"), placeholder="e.g. EUR 24,500"
        )
        incoterm = col_k.selectbox(
            "Incoterm",
            INCOTERMS,
            key=key("incoterm"),
            format_func=lambda option: option or "Not specified",
        )

        st.markdown("")
        submitted = st.form_submit_button(
            "Save changes" if editing else "Create export case", type="primary"
        )

    if st.button("← Back"):
        state.goto(state.Page.CASE_CREATED if editing else state.Page.LANDING)
        st.rerun()

    theme.disclaimer()

    if not submitted:
        return

    values = {
        "product": product,
        "origin_country": origin_country,
        "destination": destination,
        "hs_code": hs_code,
        "exporter_name": exporter_name,
        "exporter_address": exporter_address,
        "exporter_contact": exporter_contact,
        "exporter_ntn": exporter_ntn,
        "buyer_name": buyer_name,
        "buyer_address": buyer_address,
        "shipment_reference": shipment_reference,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date.isoformat() if invoice_date else "",
        "quantity": quantity,
        "declared_value": declared_value,
        "incoterm": incoterm,
    }

    problems = _validate(values)
    if problems:
        st.error(
            "Please complete the following before continuing:\n\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
        return

    profile = _build_profile(values)
    if editing:
        state.replace_case_profile(profile)
    else:
        state.create_case(profile)

    state.goto(state.Page.CASE_CREATED)
    st.rerun()
