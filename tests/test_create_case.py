"""
BAAR-AAMAD — CREATE EXPORT CASE
===============================

Two layers of test:

  * pure checks on the validation and scope-lock helpers, which need nothing
    but Python;
  * end-to-end runs of the real Streamlit app through AppTest, which drives
    the actual widgets and reruns without a browser.

The second layer is what proves the case survives Streamlit's rerun cycle.

Run:  .venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

#: Fields rendered with st.text_area rather than st.text_input.
TEXT_AREAS = {"exporter_address", "buyer_address"}

from core.state import field_key, format_case_id
from ui.pages.create_case import DEMO_CASE, REQUIRED_FIELDS, _validate, load_demo

#: A complete, valid intake. The values happen to be the demo shipment, but
#: intake accepts any product and any route — see test_intake_is_generic.
GOOD = {
    "product": "Genuine leather handbags",
    "origin_country": "Pakistan",
    "destination": "Germany",
    "hs_code": "4202.21",
    "exporter_name": "Sialkot Leather Crafts (Pvt) Ltd",
    "exporter_contact": "exports@sialkotleather.pk",
    "exporter_ntn": "3520212345678",
    "exporter_address": "Plot 14, Small Industrial Estate, Sialkot, Pakistan",
    "buyer_name": "Hoffmann Lederwaren GmbH",
    "buyer_address": "Gerberstrasse 22, 60313 Frankfurt am Main, Germany",
    "shipment_reference": "SHP-2026-0412",
    "invoice_number": "INV-2026-0412",
    "quantity": "500",
    "declared_value": "EUR 24,500",
}


def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def fill(at: AppTest, **overrides) -> AppTest:
    """Type the golden-path details into the form."""
    values = {**GOOD, **overrides}
    for name, value in values.items():
        key = field_key(name)
        if name in TEXT_AREAS:
            at.text_area(key=key).set_value(value)
        else:
            at.text_input(key=key).set_value(value)
    return at


def click(at: AppTest, label: str) -> AppTest:
    """Click a button by its visible label.

    Never click by index: buttons appear and disappear as the case gains
    documents, so positions are not stable.
    """
    matches = [b for b in at.button if label.lower() in b.label.lower()]
    if not matches:
        raise AssertionError(
            f"no button matching {label!r}; present: {[b.label for b in at.button]}"
        )
    matches[0].click().run()
    return at


def submit(at: AppTest) -> AppTest:
    """Submit the create/edit form, whichever label it is showing."""
    for label in ("Create export case", "Save changes"):
        if any(label.lower() in b.label.lower() for b in at.button):
            return click(at, label)
    raise AssertionError(f"form submit not found: {[b.label for b in at.button]}")


# ---------------------------------------------------------------------------
# Case IDs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "BA-001"), (2, "BA-002"), (42, "BA-042"), (999, "BA-999"), (1000, "BA-1000")],
)
def test_case_id_format(number, expected):
    assert format_case_id(number) == expected


# ---------------------------------------------------------------------------
# Validation helper (pure)
# ---------------------------------------------------------------------------


def test_validation_passes_on_good_input():
    assert _validate(GOOD) == []


def test_validation_reports_every_missing_required_field():
    problems = _validate({})
    assert len(problems) == len(REQUIRED_FIELDS)
    assert any("what you are exporting" in p for p in problems)
    assert any("Origin country" in p for p in problems)
    assert any("Destination country" in p for p in problems)
    assert any("Exporter company name" in p for p in problems)


def test_whitespace_only_counts_as_empty():
    assert _validate({**GOOD, "buyer_name": "   "})


def test_quantity_must_contain_a_number():
    problems = _validate({**GOOD, "quantity": "five hundred"})
    assert len(problems) == 1
    assert "must include a number" in problems[0]


def test_quantity_accepts_a_number_with_units():
    assert _validate({**GOOD, "quantity": "500 units"}) == []


# ---------------------------------------------------------------------------
# Intake is generic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("product", "origin", "destination"),
    [
        ("Genuine leather handbags", "Pakistan", "Germany"),
        ("Ceramic floor tiles", "Pakistan", "France"),
        ("Basmati rice", "Pakistan", "United Arab Emirates"),
        ("Cotton garments", "Bangladesh", "Japan"),
        ("Surgical instruments", "Pakistan", "United States"),
    ],
)
def test_intake_accepts_any_product_and_route(product, origin, destination):
    """Nothing is refused at the door. Coverage is decided afterwards."""
    values = {
        **GOOD,
        "product": product,
        "origin_country": origin,
        "destination": destination,
    }
    assert _validate(values) == []


def test_intake_has_no_product_or_destination_dropdown():
    """The leather dropdown and the Germany default are gone for good."""
    from ui.pages import create_case

    for banned in (
        "PRODUCTS",
        "DESTINATIONS",
        "SUPPORTED_PRODUCTS",
        "SUPPORTED_DESTINATIONS",
        "OTHER_PRODUCT",
        "OTHER_DESTINATION",
        "_check_scope",
    ):
        assert not hasattr(create_case, banned), f"{banned} is back in the intake"


def test_hs_code_is_optional():
    assert _validate({**GOOD, "hs_code": ""}) == []


def test_the_golden_demo_seed_is_demo_data_only():
    """Demo values may exist, but only as a seed the user can choose."""
    assert DEMO_CASE["product"] == "Genuine leather handbags"
    assert DEMO_CASE["origin_country"] == "Pakistan"
    assert DEMO_CASE["destination"] == "Germany"
    assert _validate(DEMO_CASE) == []


# ---------------------------------------------------------------------------
# The app, end to end
# ---------------------------------------------------------------------------


def test_landing_renders():
    at = app()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "BAAR" in body
    assert "Recheck" in body  # the workflow strip is present (CSS uppercases it)


def test_landing_has_no_chat_widgets():
    """This is a trade tool, not a chatbot."""
    at = app()
    assert len(at.chat_input) == 0
    assert len(at.chat_message) == 0


def test_create_case_produces_ba_001():
    at = app()
    click(at, "Start an export check")
    fill(at)
    submit(at)

    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "BA-001" in body
    assert "NOT STARTED" in body


def test_created_case_holds_what_was_entered():
    at = app()
    click(at, "Start an export check")
    fill(at)
    submit(at)

    body = " ".join(m.value for m in at.markdown)
    assert GOOD["product"] in body
    assert GOOD["destination"] in body
    assert GOOD["exporter_name"] in body
    assert GOOD["buyer_name"] in body
    assert GOOD["invoice_number"] in body
    assert GOOD["quantity"] in body


def test_case_survives_further_reruns():
    """Click something else; the case must still be there afterwards."""
    at = app()
    click(at, "Start an export check")
    fill(at)
    submit(at)
    assert "BA-001" in " ".join(m.value for m in at.markdown)

    at.run()  # a plain rerun, as any widget interaction would cause
    assert "BA-001" in " ".join(m.value for m in at.markdown)

    click(at, "Edit case details")
    at.run()
    assert "BA-001" in " ".join(m.value for m in at.markdown)


def test_edit_keeps_the_same_case_id():
    at = app()
    click(at, "Start an export check")
    fill(at)
    submit(at)

    click(at, "Edit case details")
    assert at.text_input(key=field_key("exporter_name")).value == GOOD["exporter_name"]

    at.text_input(key=field_key("quantity")).set_value("450")
    submit(at)

    body = " ".join(m.value for m in at.markdown)
    assert "BA-001" in body  # a correction is not a new case
    assert "BA-002" not in body
    assert "450" in body


def test_second_case_is_ba_002():
    at = app()
    click(at, "Start an export check")
    fill(at)
    submit(at)
    assert "BA-001" in " ".join(m.value for m in at.markdown)

    click(at, "Close case and start over")
    click(at, "Start an export check")
    fill(at)
    submit(at)

    assert "BA-002" in " ".join(m.value for m in at.markdown)


def test_empty_form_is_refused_with_guidance():
    at = app()
    click(at, "Start an export check")
    submit(at)

    assert not at.exception
    assert len(at.error) == 1
    message = at.error[0].value
    assert "Exporter company name is required." in message
    assert "Quantity is required." in message
    assert "BA-001" not in " ".join(m.value for m in at.markdown)  # no case created


def test_bad_quantity_is_refused_and_keeps_the_rest():
    at = app()
    click(at, "Start an export check")
    fill(at, quantity="five hundred")
    submit(at)

    assert len(at.error) == 1
    assert "must include a number" in at.error[0].value
    # what was typed is still on screen
    assert at.text_input(key=field_key("buyer_name")).value == GOOD["buyer_name"]


def test_an_unusual_route_is_accepted_at_intake():
    """Intake no longer refuses anything. Coverage is decided by the corpus.

    The old model rejected non-leather, non-Germany cases at the door. That
    was demo scope masquerading as product scope.
    """
    at = app()
    click(at, "Start an export check")
    fill(at, product="Ceramic floor tiles", origin_country="Pakistan",
         destination="France")
    submit(at)

    assert not at.exception
    assert len(at.error) == 0
    body = " ".join(m.value for m in at.markdown)
    assert "BA-001" in body
    assert "Ceramic floor tiles" in body
    assert "France" in body


def test_no_fabricated_analysis_is_shown():
    """Nothing may imply requirements were found or documents were read."""
    at = app()
    click(at, "Start an export check")
    fill(at)
    submit(at)

    body = " ".join(m.value for m in at.markdown)
    case = at.session_state["ba_case"]
    assert case.findings == []
    assert case.requirements == []
    assert "Not uploaded" in body  # documents shown as absent, not assessed
    for invented in ("SATISFIED", "Completed", "Needs correction", "Action required"):
        assert invented not in body
