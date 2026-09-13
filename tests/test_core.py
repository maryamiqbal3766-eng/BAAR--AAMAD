"""
BAAR-AAMAD — CORE SMOKE TEST
============================

Covers the locked core specification:

  A  every core module imports
  B  every internal state maps to the correct label and priority
  C  NOT_ASSESSED never becomes a separate user-facing status
  D  a requirement with no evidence becomes REQUIRES_VERIFICATION
  E  case status is deterministic across every finding mix
  F  core.llm imports
  G  the gateway reports "not configured" when GROQ_API_KEY is absent

No real Groq call is made anywhere in this file.

Run:  .venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

import pytest

# --- A / F: imports ---------------------------------------------------------

from core import errors, llm, rules, schemas  # noqa: E402
from core.rules import (  # noqa: E402
    BLOCKING_STATES,
    OPEN_QUESTION_STATES,
    case_status_for,
    enforce_evidence_rule,
    label_for_state,
    priority_for_state,
    tally_labels,
)
from core.schemas import (  # noqa: E402
    DRAFT_BANNER,
    AssessmentState,
    CaseStatus,
    Finding,
    FindingLabel,
    HumanDecision,
    Priority,
    RegulatoryEvidence,
    Requirement,
    VerificationStatus,
)


def make_finding(
    state: AssessmentState,
    decision: HumanDecision = HumanDecision.PENDING,
    finding_id: str = "F1",
) -> Finding:
    """Build a Finding with its derived fields set the way the rules say."""
    return Finding(
        finding_id=finding_id,
        requirement_id="R1",
        state=state,
        label=label_for_state(state),
        priority=priority_for_state(state),
        human_decision=decision,
    )


def make_requirement(with_evidence: bool) -> Requirement:
    evidence = []
    if with_evidence:
        evidence = [
            RegulatoryEvidence(
                evidence_id="E1",
                source_name="Curated source",
                source_url="https://example.org/source",
                excerpt="Verbatim excerpt from the curated corpus.",
            )
        ]
    return Requirement(
        requirement_id="R1",
        title="Certificate of Origin",
        what_is_required="A valid Certificate of Origin.",
        why_required="It establishes the declared origin of the goods.",
        when_it_applies="Applies to this shipment.",
        evidence=evidence,
        verification_status=VerificationStatus.SUPPORTED_BY_SOURCE,
    )


# ---------------------------------------------------------------------------
# A — modules import
# ---------------------------------------------------------------------------


def test_core_modules_import():
    assert schemas is not None
    assert rules is not None
    assert errors is not None
    assert llm is not None


def test_draft_banner_is_exact():
    """An absolute rule: generated drafts carry this banner verbatim."""
    assert DRAFT_BANNER == "DRAFT — FOR HUMAN VERIFICATION"


# ---------------------------------------------------------------------------
# B — state -> label / priority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected_label", "expected_priority"),
    [
        (AssessmentState.SATISFIED, FindingLabel.COMPLETED, Priority.SATISFIED),
        (AssessmentState.MISSING, FindingLabel.ACTION_REQUIRED, Priority.URGENT_HIGH),
        (
            AssessmentState.INCONSISTENT,
            FindingLabel.NEEDS_CORRECTION,
            Priority.MEDIUM,
        ),
        (
            AssessmentState.REQUIRES_VERIFICATION,
            FindingLabel.VERIFICATION_REQUIRED,
            Priority.VERIFICATION,
        ),
        (
            AssessmentState.NOT_ASSESSED,
            FindingLabel.VERIFICATION_REQUIRED,
            Priority.VERIFICATION,
        ),
    ],
)
def test_state_maps_to_label_and_priority(state, expected_label, expected_priority):
    assert label_for_state(state) is expected_label
    assert priority_for_state(state) is expected_priority


def test_every_state_is_mapped():
    """No internal state may be left without a label or a priority."""
    for state in AssessmentState:
        assert label_for_state(state) in FindingLabel
        assert priority_for_state(state) in Priority


# ---------------------------------------------------------------------------
# C — NOT_ASSESSED is internal only
# ---------------------------------------------------------------------------


def test_exactly_four_user_facing_labels():
    assert len(list(FindingLabel)) == 4


def test_not_assessed_is_not_a_user_facing_label():
    label_values = {label.value.upper().replace(" ", "_") for label in FindingLabel}
    assert "NOT_ASSESSED" not in label_values


def test_not_assessed_folds_into_verification_required():
    assert label_for_state(AssessmentState.NOT_ASSESSED) is (
        FindingLabel.VERIFICATION_REQUIRED
    )


def test_not_assessed_adds_no_extra_tally_row():
    """A NOT_ASSESSED finding must not create a fifth row in the Passport."""
    labels = [
        label_for_state(AssessmentState.SATISFIED),
        label_for_state(AssessmentState.NOT_ASSESSED),
    ]
    tally = tally_labels(labels)
    assert len(tally) == 4
    assert tally[FindingLabel.VERIFICATION_REQUIRED] == 1


# ---------------------------------------------------------------------------
# D — the absolute evidence rule
# ---------------------------------------------------------------------------


def test_requirement_without_evidence_is_forced_to_verification():
    """No evidence -> no confident regulatory claim. Mechanically enforced."""
    req = make_requirement(with_evidence=False)
    assert req.verification_status is VerificationStatus.SUPPORTED_BY_SOURCE  # claimed
    enforce_evidence_rule(req)
    assert req.verification_status is VerificationStatus.REQUIRES_VERIFICATION  # denied


def test_requirement_with_evidence_keeps_its_status():
    req = make_requirement(with_evidence=True)
    enforce_evidence_rule(req)
    assert req.verification_status is VerificationStatus.SUPPORTED_BY_SOURCE


def test_evidence_carries_a_real_source_url():
    req = make_requirement(with_evidence=True)
    assert rules.has_source_backing(req) is True
    assert rules.has_source_backing(make_requirement(with_evidence=False)) is False


# ---------------------------------------------------------------------------
# E — case status
# ---------------------------------------------------------------------------


def test_case_status_no_findings():
    assert case_status_for([]) is CaseStatus.NOT_STARTED


def test_case_status_missing_blocks():
    findings = [
        make_finding(AssessmentState.SATISFIED, finding_id="F1"),
        make_finding(AssessmentState.MISSING, finding_id="F2"),
    ]
    assert case_status_for(findings) is CaseStatus.ACTION_REQUIRED


def test_case_status_inconsistent_blocks():
    """This is the golden demo's 500 vs 450 state."""
    findings = [
        make_finding(AssessmentState.SATISFIED, finding_id="F1"),
        make_finding(AssessmentState.INCONSISTENT, finding_id="F2"),
    ]
    assert case_status_for(findings) is CaseStatus.ACTION_REQUIRED


def test_case_status_verification_required():
    findings = [
        make_finding(AssessmentState.SATISFIED, finding_id="F1"),
        make_finding(AssessmentState.REQUIRES_VERIFICATION, finding_id="F2"),
    ]
    assert case_status_for(findings) is CaseStatus.VERIFICATION_REQUIRED


def test_case_status_not_assessed_also_requires_verification():
    findings = [make_finding(AssessmentState.NOT_ASSESSED)]
    assert case_status_for(findings) is CaseStatus.VERIFICATION_REQUIRED


def test_case_status_all_satisfied():
    """After the golden demo fix + recheck, the case reaches this state."""
    findings = [
        make_finding(AssessmentState.SATISFIED, finding_id="F1"),
        make_finding(AssessmentState.SATISFIED, finding_id="F2"),
    ]
    assert case_status_for(findings) is CaseStatus.READY_FOR_HUMAN_REVIEW


def test_blocker_outranks_verification():
    """Precedence: a blocker wins over an open question."""
    findings = [
        make_finding(AssessmentState.REQUIRES_VERIFICATION, finding_id="F1"),
        make_finding(AssessmentState.MISSING, finding_id="F2"),
    ]
    assert case_status_for(findings) is CaseStatus.ACTION_REQUIRED


def test_human_resolved_finding_stops_blocking():
    """'Unresolved' in the spec: the Human Review Gate can settle an item."""
    findings = [
        make_finding(
            AssessmentState.REQUIRES_VERIFICATION,
            decision=HumanDecision.VERIFIED,
            finding_id="F1",
        )
    ]
    assert case_status_for(findings) is CaseStatus.READY_FOR_HUMAN_REVIEW


def test_bare_states_still_work():
    """Convenience form used by tests and quick checks."""
    assert case_status_for([AssessmentState.MISSING]) is CaseStatus.ACTION_REQUIRED
    assert case_status_for([AssessmentState.SATISFIED]) is (
        CaseStatus.READY_FOR_HUMAN_REVIEW
    )


def test_blocking_and_question_sets_are_disjoint_and_complete():
    assert not (BLOCKING_STATES & OPEN_QUESTION_STATES)
    covered = BLOCKING_STATES | OPEN_QUESTION_STATES | {AssessmentState.SATISFIED}
    assert covered == set(AssessmentState)


def test_no_numeric_compliance_score_anywhere():
    """By design there is no score field. Guard against one creeping in."""
    banned = {"score", "compliance_score", "percentage", "percent", "rating"}
    for model in (schemas.Passport, schemas.Finding, schemas.ExportCase):
        assert not banned & set(model.model_fields)


# ---------------------------------------------------------------------------
# F / G — the Groq gateway
# ---------------------------------------------------------------------------


def test_llm_module_imports_without_a_key():
    assert llm.Tier.REASONING and llm.Tier.FAST
    assert llm.MODEL_PREFERENCES[llm.Tier.REASONING]
    assert llm.MODEL_PREFERENCES[llm.Tier.FAST]


def test_no_deprecated_llama_chat_models_are_preferred():
    """These stopped being callable on Groq on 2026-08-16."""
    dead = {"llama-3.1-8b-instant", "llama-3.3-70b-versatile"}
    for models in llm.MODEL_PREFERENCES.values():
        assert not dead & set(models)


def test_gateway_reports_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_dotenv_loaded", True)  # don't read a real .env
    llm.reset_cache()

    assert llm.api_key() is None
    assert llm.is_configured() is False

    report = llm.resolution_report()
    assert report["configured"] is False
    assert "GROQ_API_KEY" in report["error"]


def test_gateway_raises_typed_error_without_key(monkeypatch):
    """It fails cleanly with a message an exporter can understand."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_dotenv_loaded", True)
    llm.reset_cache()

    with pytest.raises(errors.LLMUnavailableError) as excinfo:
        llm.available_models(refresh=True)
    assert "not configured" in excinfo.value.user_message


def test_gateway_sees_a_key_when_one_is_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setattr(llm, "_dotenv_loaded", True)
    llm.reset_cache()
    assert llm.is_configured() is True
    llm.reset_cache()


def test_strip_fences_handles_fenced_json():
    assert llm._strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert llm._strip_fences('{"a": 1}') == '{"a": 1}'
