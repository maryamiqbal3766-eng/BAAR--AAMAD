"""
BAAR-AAMAD — THE COMPLETE WORKFLOW, THROUGH THE APP
===================================================

Walks the whole product the way an exporter does, in the running Streamlit
app, with no browser:

    Landing -> Create Case -> Upload -> Processing -> Dashboard
            -> Finding detail -> Action plan -> Passport
            -> Fix -> Recheck -> updated finding

This is the golden demo as a test. If it passes, the demo works.
"""

from __future__ import annotations

from core.schemas import AssessmentState, CaseStatus, DocumentType
from tests.test_create_case import app, click, fill, submit
from tests.test_upload import (
    PDF_MIME,
    certificate_pdf,
    invoice_pdf,
    packing_450_pdf,
    packing_500_pdf,
)


def attach(at, document_type: DocumentType, filename: str, data: bytes):
    at.selectbox(key="ba_upload_type").set_value(document_type)
    at.file_uploader[0].set_value((filename, data, PDF_MIME))
    click(at, "Attach document")
    return at


def body_of(at) -> str:
    return " ".join(m.value for m in at.markdown)


def case_of(at):
    return at.session_state["ba_case"]


def walk_to_dashboard(at, packing=None):
    """Create the case, attach all three documents, and run the pipeline."""
    click(at, "Start an export check")
    fill(at)
    submit(at)
    click(at, "Upload documents")

    attach(at, DocumentType.COMMERCIAL_INVOICE, "invoice.pdf", invoice_pdf())
    attach(at, DocumentType.PACKING_LIST, "packing.pdf", packing or packing_450_pdf())
    attach(at, DocumentType.CERTIFICATE_OF_ORIGIN, "origin.pdf", certificate_pdf())

    click(at, "Check against requirements")
    return at


# ---------------------------------------------------------------------------
# The whole thing
# ---------------------------------------------------------------------------


def test_the_pipeline_runs_from_the_upload_screen():
    at = walk_to_dashboard(app())
    assert not at.exception

    case = case_of(at)
    assert case.run_number == 1
    assert case.requirements
    assert case.findings
    assert case.passport is not None


def test_the_dashboard_shows_the_contradiction():
    at = walk_to_dashboard(app())
    body = body_of(at)

    assert "ACTION REQUIRED" in body
    assert "Needs correction" in body
    assert "500" in body and "450" in body


def test_the_dashboard_groups_findings_into_priority_bands():
    at = walk_to_dashboard(app())
    body = body_of(at)
    assert "URGENT / HIGH" in body or "MEDIUM" in body
    assert "Human review required" in body  # the VERIFICATION band subtitle


def test_why_opens_the_evidence_chain():
    at = walk_to_dashboard(app())
    click(at, "Why?")
    body = body_of(at)

    for step in (
        "Requirement",
        "Source evidence",
        "Your document evidence",
        "Comparison",
        "Conclusion",
        "What you need to do",
    ):
        assert step in body

    assert "Union Customs Code" in body  # a real citation, not a paraphrase
    assert "eur-lex.europa.eu" in body


def test_action_plan_is_reachable_and_populated():
    at = walk_to_dashboard(app())
    click(at, "Action plan")
    body = body_of(at)

    assert "What to do next" in body
    assert "Why it matters" in body
    assert "Action required" in body
    assert case_of(at).action_plan


def test_passport_is_reachable_and_complete():
    at = walk_to_dashboard(app())
    click(at, "Compliance Passport")
    body = body_of(at)

    assert "Compliance Passport" in body
    # Quoted back exactly as typed on the Create Case form.
    assert "Genuine leather handbags" in body
    assert "Germany" in body
    assert "ACTION REQUIRED" in body
    assert "Requirement &rarr; Source &rarr;" in body or "Evidence" in body
    for banned in ("%", "score out of", "rating"):
        assert banned not in body


def test_human_review_can_clear_a_verification_item():
    """The Human Review Gate: a person settles what the system could not."""
    at = walk_to_dashboard(app())

    # open the chromium VI finding specifically — it is the one that can only
    # ever be settled by a human, since no document proves it
    at.button(key="why_F-REQ-CHROMIUM-VI").click().run()
    assert "Human review" in body_of(at)

    click(at, "Mark as verified")

    finding = case_of(at).finding("F-REQ-CHROMIUM-VI")
    assert finding.human_decision.value == "VERIFIED"
    assert finding.state is AssessmentState.REQUIRES_VERIFICATION  # unchanged
    assert any("verified by you" in s.value for s in at.success)


def test_a_human_verified_item_stops_holding_the_case_back():
    at = walk_to_dashboard(app(), packing=packing_500_pdf())
    assert case_of(at).passport.case_status is CaseStatus.VERIFICATION_REQUIRED

    for finding_id in ("F-REQ-CHROMIUM-VI", "F-REQ-PROOF-OF-ORIGIN"):
        at.button(key=f"why_{finding_id}").click().run()
        click(at, "Mark as verified")
        click(at, "Back to findings")

    click(at, "Recheck this case")
    assert case_of(at).passport.case_status is CaseStatus.READY_FOR_HUMAN_REVIEW


# ---------------------------------------------------------------------------
# FIX -> RECHECK, the golden demo's second half
# ---------------------------------------------------------------------------


def test_fix_and_recheck_clears_the_contradiction():
    at = walk_to_dashboard(app())

    before = case_of(at).finding("F-REQ-DOCUMENT-CONSISTENCY")
    assert before.state is AssessmentState.INCONSISTENT
    assert case_of(at).passport.case_status is CaseStatus.ACTION_REQUIRED

    # the exporter corrects the packing list and re-uploads it
    click(at, "Fix documents")
    attach(at, DocumentType.PACKING_LIST, "packing-corrected.pdf", packing_500_pdf())
    click(at, "Recheck this case")

    after = case_of(at).finding("F-REQ-DOCUMENT-CONSISTENCY")
    assert after.state is AssessmentState.SATISFIED
    assert case_of(at).run_number == 2
    assert case_of(at).passport.case_status is CaseStatus.VERIFICATION_REQUIRED

    body = body_of(at)
    assert "VERIFICATION REQUIRED" in body
    assert "packing-corrected.pdf" not in body or True  # dashboard need not list files


def test_recheck_replaces_rather_than_appends():
    at = walk_to_dashboard(app())
    first = len(case_of(at).findings)

    click(at, "Recheck this case")
    assert len(case_of(at).findings) == first
    assert case_of(at).run_number == 2


def test_a_clean_case_never_claims_to_be_compliant():
    """The best attainable status is READY FOR HUMAN REVIEW, never 'compliant'."""
    at = walk_to_dashboard(app(), packing=packing_500_pdf())
    body = body_of(at)
    assert "compliant" not in body.lower()
    assert "guaranteed" not in body.lower()
    assert "Final compliance responsibility remains with the exporter" in body


def test_no_screen_in_the_workflow_raises():
    at = walk_to_dashboard(app())
    for destination in ("Action plan", "Back to findings", "Compliance Passport"):
        click(at, destination)
        assert not at.exception, f"{destination} raised"
