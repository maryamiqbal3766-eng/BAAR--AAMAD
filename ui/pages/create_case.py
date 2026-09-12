"""
Create Export Case.

Collects only what the MVP genuinely needs: product, destination, exporter
and shipment details. Nothing here is inferred or invented — the AI stages
that normalize the product and interpret requirements come later, and this
screen does not pretend otherwise.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import state
from core.errors import UnsupportedScopeError
from core.schemas import CaseProfile, ExporterInfo, ShipmentInfo
from modules.profile import RECOGNISED_PRODUCTS, normalize_product
from modules.retrieval import BLOCS
from ui import theme

#: DEMO SEED VALUES — the golden demo scenario, nothing more.
#: These pre-fill the form so the demo is quick to reach. They are not the
#: application's scope: coverage is decided by the corpus at run time.
DEMO_PRODUCT = "Leather bags"
DEMO_ORIGIN = "Pakistan"
DEMO_DESTINATION = "Germany"

#: Markets the form offers today. Pending the generic country intake, this is
#: drawn from the bloc the corpus actually covers rather than a list of its
#: own, so it cannot drift from what can be advised on.
SUPPORTED_DESTINATIONS: tuple[str, ...] = BLOCS["european union"]
SUPPORTED_PRODUCTS: tuple[str, ...] = RECOGNISED_PRODUCTS

OTHER_PRODUCT = "Other product (not yet supported)"
OTHER_DESTINATION = "Other destination (not yet supported)"

#: What the curated corpus genuinely covers, plus an honest way out.
PRODUCTS = [*SUPPORTED_PRODUCTS, OTHER_PRODUCT]
DESTINATIONS = [*SUPPORTED_DESTINATIONS, OTHER_DESTINATION]
INCOTERMS = ["", "EXW", "FCA", "FOB", "CFR", "CIF", "CPT", "DAP", "DDP"]


def _validate(values: dict) -> list[str]:
    """Deterministic input checks. Returns a list of plain-language problems."""
    problems: list[str] = []

    if not values["exporter_name"].strip():
        problems.append("Exporter company name is required.")
    if not values["buyer_name"].strip():
        problems.append("Buyer name is required.")
    if not values["invoice_number"].strip():
        problems.append("Invoice number is required.")

    quantity = values["quantity"].strip()
    if not quantity:
        problems.append("Quantity is required.")
    elif not any(character.isdigit() for character in quantity):
        problems.append(
            f'Quantity must include a number — "{quantity}" does not. '
            "For example: 500, or 500 units."
        )

    return problems


def _check_scope(product_raw: str, destination: str) -> None:
    """Refuse anything the curated corpus cannot genuinely support.

    We would rather say "not yet" than show an exporter a requirement set
    assembled from nothing.
    """
    if destination not in SUPPORTED_DESTINATIONS:
        raise UnsupportedScopeError(
            f"destination={destination!r}",
            user_message=(
                "BAAR-AAMAD currently covers exports to the European Union. "
                "Support for other markets needs authoritative sources for "
                "that market, which we have not curated yet."
            ),
        )

    normalized, _ = normalize_product(product_raw)
    if not normalized:
        raise UnsupportedScopeError(
            f"product={product_raw!r}",
            user_message=(
                f'BAAR-AAMAD could not recognise "{product_raw}" as a leather '
                "article. This release covers leather bags, belts, wallets, "
                "gloves, garments, cases and similar goods that touch the "
                "skin. Support for other products needs sources we have not "
                "curated yet."
            ),
        )


def _build_profile(values: dict) -> CaseProfile:
    """Map the form onto the shared contract. No AI fields are filled in."""
    return CaseProfile(
        product_raw=values["product_description"].strip() or values["product"],
        destination=values["destination"],
        exporter=ExporterInfo(
            name=values["exporter_name"].strip(),
            address=values["exporter_address"].strip(),
            contact=values["exporter_contact"].strip(),
            ntn_or_reg_no=values["exporter_ntn"].strip(),
        ),
        shipment=ShipmentInfo(
            buyer_name=values["buyer_name"].strip(),
            buyer_address=values["buyer_address"].strip(),
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
    empty. The case is the durable record, so seed the form from that rather
    than relying on how long widget state happens to survive.
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

    # The dropdown holds the recognised product; the free-text box holds the
    # exporter's own wording, but only when it differs from the dropdown.
    chosen = profile.product_normalized or profile.product_raw
    seed = {
        "product": chosen if chosen in PRODUCTS else DEMO_PRODUCT,
        "product_description": (
            profile.product_raw if profile.product_raw not in PRODUCTS else ""
        ),
        "destination": profile.destination
        if profile.destination in DESTINATIONS
        else DEMO_DESTINATION,
        "exporter_name": exporter.name,
        "exporter_contact": exporter.contact,
        "exporter_ntn": exporter.ntn_or_reg_no,
        "exporter_address": exporter.address,
        "buyer_name": shipment.buyer_name,
        "buyer_address": shipment.buyer_address,
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
    theme.masthead(f"CASE {case.case_id} &middot; EDITING" if editing else "NEW CASE")

    st.markdown(
        f'<div class="ba-eyebrow">Step 1 of 5 &middot; Find</div>'
        f'<div class="ba-h1">{"Edit export case" if editing else "Create export case"}'
        "</div>"
        '<div class="ba-lede">Tell BAAR-AAMAD what you are shipping and where. '
        "These details are compared against your documents later, so enter "
        "them as they appear on your paperwork.</div>",
        unsafe_allow_html=True,
    )
    theme.workflow_strip("Find")

    key = state.field_key  # stable widget identity; see core.state for why

    with st.form("create_case", border=True):
        theme.section("Product and destination")
        col_a, col_b = st.columns(2)
        product = col_a.selectbox("Product", PRODUCTS, key=key("product"))
        destination = col_b.selectbox(
            "Destination market",
            DESTINATIONS,
            # The list is alphabetical, so without this it would open on
            # Austria. Germany is the default the product is demonstrated on.
            index=DESTINATIONS.index(DEMO_DESTINATION),
            key=key("destination"),
        )
        description = st.text_input(
            "Describe your goods in your own words (optional)",
            key=key("product_description"),
            placeholder="e.g. handmade full-grain leather shoulder bags",
            help=(
                "If you fill this in, BAAR-AAMAD reads your description and "
                "works out which product it is, instead of using the dropdown."
            ),
        )

        theme.section("Exporter")
        exporter_name = st.text_input(
            "Company name *", key=key("exporter_name"), placeholder="Required"
        )
        col_c, col_d = st.columns(2)
        exporter_contact = col_c.text_input(
            "Contact (email or phone)", key=key("exporter_contact")
        )
        exporter_ntn = col_d.text_input(
            "NTN / registration number", key=key("exporter_ntn")
        )
        exporter_address = st.text_area(
            "Address", key=key("exporter_address"), height=80
        )

        theme.section("Shipment")
        buyer_name = st.text_input(
            "Buyer / consignee name *", key=key("buyer_name"), placeholder="Required"
        )
        buyer_address = st.text_area(
            "Buyer address", key=key("buyer_address"), height=80
        )

        col_e, col_f = st.columns(2)
        invoice_number = col_e.text_input(
            "Invoice number *", key=key("invoice_number"), placeholder="Required"
        )
        invoice_date = col_f.date_input(
            "Invoice date", value=None, format="YYYY-MM-DD", key=key("invoice_date")
        )

        col_g, col_h, col_i = st.columns(3)
        quantity = col_g.text_input(
            "Quantity *", key=key("quantity"), placeholder="e.g. 500"
        )
        declared_value = col_h.text_input(
            "Declared value", key=key("declared_value"), placeholder="e.g. EUR 25,000"
        )
        incoterm = col_i.selectbox(
            "Incoterm",
            INCOTERMS,
            key=key("incoterm"),
            format_func=lambda option: option or "—",
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

    # A free-text description, when given, is what the exporter actually
    # means — the dropdown is only the fallback.
    product_raw = description.strip() or product

    values = {
        "product": product,
        "product_description": description,
        "destination": destination,
        "exporter_name": exporter_name,
        "exporter_address": exporter_address,
        "exporter_contact": exporter_contact,
        "exporter_ntn": exporter_ntn,
        "buyer_name": buyer_name,
        "buyer_address": buyer_address,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date.isoformat() if invoice_date else "",
        "quantity": quantity,
        "declared_value": declared_value,
        "incoterm": incoterm,
    }

    try:
        _check_scope(product_raw, destination)
    except UnsupportedScopeError as exc:
        st.warning(exc.user_message, icon=":material/info:")
        return

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
