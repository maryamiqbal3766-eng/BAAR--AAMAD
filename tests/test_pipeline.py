"""
BAAR-AAMAD — REASONING, ACTIONS, PASSPORT AND THE PIPELINE
==========================================================

Covers the second half of the workflow and the orchestrator that sequences
it, including the properties the whole design rests on: the pipeline is
idempotent, a failure never destroys a case, and RECHECK is the same run.
"""

from __future__ import annotations

import pytest

from core import orchestrator
from core.schemas import (
    DRAFT_BANNER,
    AssessmentState,
    CaseStatus,
    DocumentType,
    ExportCase,
    FindingLabel,
    StageName,
    StageStatus,
)
from modules import actions, passport as passport_module
from modules.reasoning import build_trace, build_traces

from tests.conftest import CERTIFICATE, INVOICE_500, PACKING_450, build_case


def assessed(case, corpus):
    """A case carried through findings, reasoning and actions."""
    from modules.findings import build_findings

    case.findings = build_findings(case, corpus=corpus, use_ai=False)
    case.reasoning = build_traces(case, use_ai=False)
    case.action_plan = actions.build_action_plan(case)
    case.checklists = actions.build_checklists(case)
    case.drafts = actions.build_drafts(case)
    case.passport = passport_module.build_passport(case)
    return case


# ---------------------------------------------------------------------------
# Reasoning — the "Why did BAAR-AAMAD flag this?" chain
# ---------------------------------------------------------------------------


def test_every_finding_gets_a_six_link_explanation(full_case, corpus):
    case = assessed(full_case, corpus)
    assert len(case.reasoning) == len(case.findings)

    for trace in case.reasoning:
        assert trace.requirement
        assert trace.source_evidence
        assert trace.your_document_evidence
        assert trace.comparison
        assert trace.conclusion
        assert trace.what_you_need_to_do


def test_the_explanation_quotes_the_real_source(full_case, corpus):
    case = assessed(full_case, corpus)
    trace = case.trace("F-REQ-DOCUMENT-CONSISTENCY")
    assert "Union Customs Code" in trace.source_evidence
    assert "accomplishment of customs formalities" in trace.source_evidence


def test_the_explanation_shows_the_exporters_own_values(full_case, corpus):
    """The quantity clash must be visible in the exporter's own numbers."""
    case = assessed(full_case, corpus)
    trace = case.trace("F-REQ-DOCUMENT-CONSISTENCY")
    assert "500" in trace.your_document_evidence
    assert "450" in trace.your_document_evidence
    assert "Does not agree" in trace.comparison


def test_a_verification_finding_explains_why_it_cannot_be_settled(full_case, corpus):
    case = assessed(full_case, corpus)
    trace = case.trace("F-REQ-CHROMIUM-VI")
    assert "chromium VI" in trace.source_evidence
    assert "cannot settle" in trace.conclusion or "verification" in trace.conclusion


def test_reasoning_reaches_no_new_verdict(full_case, corpus):
    """Explanations describe findings; they never overturn them."""
    case = assessed(full_case, corpus)
    consistency = case.finding("F-REQ-DOCUMENT-CONSISTENCY")
    trace = case.trace("F-REQ-DOCUMENT-CONSISTENCY")
    assert consistency.state is AssessmentState.INCONSISTENT
    assert "resolved" in trace.conclusion or "different values" in trace.conclusion


# ---------------------------------------------------------------------------
# Action plan
# ---------------------------------------------------------------------------


def test_action_plan_lists_only_work(full_case, corpus):
    case = assessed(full_case, corpus)
    assert case.action_plan
    for item in case.action_plan:
        finding = case.finding(item.finding_id)
        assert finding.state is not AssessmentState.SATISFIED
        assert item.problem
        assert item.why_it_matters
        assert item.action_required


def test_action_plan_is_ordered_by_priority(full_case, corpus):
    from core.rules import priority_rank

    case = assessed(full_case, corpus)
    ranks = [priority_rank(item.priority) for item in case.action_plan]
    assert ranks == sorted(ranks)


def test_a_clean_case_has_a_shorter_plan(fixed_case, full_case, corpus):
    before = assessed(full_case, corpus)
    after = assessed(fixed_case, corpus)
    assert len(after.action_plan) < len(before.action_plan)


# ---------------------------------------------------------------------------
# Missing information checklist
# ---------------------------------------------------------------------------


def test_checklist_covers_present_documents_missing_values(profile, corpus):
    """A document that exists but is incomplete belongs on the checklist."""
    case = build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (CERTIFICATE, DocumentType.PACKING_LIST),  # filed as the wrong type
    )
    case = assessed(case, corpus)
    packing = next(
        (c for c in case.checklists if c.document_type is DocumentType.PACKING_LIST),
        None,
    )
    assert packing is not None
    assert "packages" in packing.missing_fields


def test_an_absent_document_is_not_a_checklist_entry(profile, corpus):
    case = build_case(profile, corpus, (INVOICE_500, DocumentType.COMMERCIAL_INVOICE))
    case = assessed(case, corpus)
    assert not any(
        c.document_type is DocumentType.CERTIFICATE_OF_ORIGIN for c in case.checklists
    )


# ---------------------------------------------------------------------------
# Preparation drafts — the hard safety line
# ---------------------------------------------------------------------------


def test_a_draft_is_offered_for_a_missing_certificate(profile, corpus):
    case = build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
    )
    case = assessed(case, corpus)
    draft = next(
        d for d in case.drafts if d.document_type is DocumentType.CERTIFICATE_OF_ORIGIN
    )
    assert draft.banner == DRAFT_BANNER
    assert actions.draft_is_safe(draft)


def test_a_draft_only_uses_facts_already_in_the_case(profile, corpus):
    case = build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
    )
    case = assessed(case, corpus)
    draft = next(
        d for d in case.drafts if d.document_type is DocumentType.CERTIFICATE_OF_ORIGIN
    )
    assert "Sialkot Leather Crafts (Pvt) Ltd" in draft.body
    assert "Pakistan" in draft.body
    assert "INV-2026-0412" in draft.body
    assert draft.prepared_from


def test_a_draft_never_invents_the_authority_fields(profile, corpus):
    """A certificate number and a stamp can only come from the issuing body."""
    case = build_case(
        profile,
        corpus,
        (INVOICE_500, DocumentType.COMMERCIAL_INVOICE),
        (PACKING_450, DocumentType.PACKING_LIST),
    )
    case = assessed(case, corpus)
    draft = next(
        d for d in case.drafts if d.document_type is DocumentType.CERTIFICATE_OF_ORIGIN
    )
    assert "To be completed by the issuing body" in draft.body
    assert "assigned by the issuing chamber" in draft.body
    assert "CO-PK-2026-8841" not in draft.body  # not copied from anywhere


def test_a_draft_never_claims_to_be_official(profile, corpus):
    case = build_case(profile, corpus, (INVOICE_500, DocumentType.COMMERCIAL_INVOICE))
    case = assessed(case, corpus)
    for draft in case.drafts:
        assert actions.draft_is_safe(draft)
        assert "certify" not in draft.body.lower()
        assert "BAAR-AAMAD does not issue official documents" in draft.disclaimer


def test_no_draft_when_the_document_is_already_there(full_case, corpus):
    case = assessed(full_case, corpus)
    assert not any(
        d.document_type is DocumentType.CERTIFICATE_OF_ORIGIN for d in case.drafts
    )


# ---------------------------------------------------------------------------
# Compliance Passport
# ---------------------------------------------------------------------------


def test_passport_sections(full_case, corpus):
    case = assessed(full_case, corpus)
    p = case.passport

    assert p.case_id == "BA-001"
    # The exporter's own words, not a category the application chose for them.
    assert p.product == "Handmade full-grain leather shoulder bags"
    assert p.destination == "Germany"
    assert p.case_status is CaseStatus.ACTION_REQUIRED
    assert sum(p.requirement_tally.values()) == len(case.findings)
    assert len(p.requirement_tally) == 4  # never a fifth row
    assert p.key_issues
    assert p.next_actions
    assert p.evidence_map


def test_passport_limits_are_respected(full_case, corpus):
    case = assessed(full_case, corpus)
    assert len(case.passport.key_issues) <= 3
    assert len(case.passport.next_actions) <= 3


def test_evidence_map_chains_requirement_to_source_to_document_to_finding(
    full_case, corpus
):
    case = assessed(full_case, corpus)
    row = next(
        r for r in case.passport.evidence_map if "agree across" in r.requirement
    )
    assert "Union Customs Code" in row.source
    assert row.source_url.startswith("https://")
    assert "500" in row.document_evidence and "450" in row.document_evidence
    assert row.finding == FindingLabel.NEEDS_CORRECTION.value


def test_every_evidence_row_cites_something(full_case, corpus):
    case = assessed(full_case, corpus)
    for row in case.passport.evidence_map:
        assert row.source
        assert row.source_url.startswith("https://")


def test_passport_has_no_score(full_case, corpus):
    case = assessed(full_case, corpus)
    dumped = case.passport.model_dump_json().lower()
    for banned in ("score", "percent", "rating", "grade"):
        assert banned not in dumped


def test_passport_plain_text_is_complete(full_case, corpus):
    case = assessed(full_case, corpus)
    text = passport_module.as_plain_text(case.passport)

    for heading in (
        "PRODUCT",
        "DESTINATION",
        "CASE STATUS",
        "REQUIREMENTS",
        "KEY ISSUES",
        "NEXT ACTIONS",
        "EVIDENCE",
    ):
        assert heading in text
    assert "Final compliance" in text
    assert "BA-001" in text


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


def test_pipeline_runs_every_stage(full_case, run_context):
    outcomes = orchestrator.run_to_completion(full_case, ctx=run_context)

    assert len(outcomes) == len(orchestrator.STAGE_ORDER)
    assert all(o.status is StageStatus.COMPLETE for o in outcomes)
    for name in orchestrator.STAGE_ORDER:
        assert full_case.stage(name).status is StageStatus.COMPLETE
        assert full_case.stage(name).message


def test_pipeline_populates_the_whole_case(full_case, run_context):
    orchestrator.run_to_completion(full_case, ctx=run_context)

    assert full_case.requirements
    assert full_case.checks
    assert full_case.findings
    assert full_case.reasoning
    assert full_case.action_plan
    assert full_case.passport is not None
    assert full_case.run_number == 1


def test_pipeline_is_idempotent(full_case, run_context):
    """Running twice must produce the same case. This is what makes Recheck safe."""
    orchestrator.run_to_completion(full_case, ctx=run_context)
    first = [f.model_dump() for f in full_case.findings]

    orchestrator.run_to_completion(full_case, ctx=run_context)
    second = [f.model_dump() for f in full_case.findings]

    assert first == second
    assert len(full_case.findings) == len(first)  # nothing appended
    assert full_case.run_number == 2


def test_pipeline_detects_the_golden_demo_contradiction(full_case, run_context):
    orchestrator.run_to_completion(full_case, ctx=run_context)
    consistency = full_case.finding("F-REQ-DOCUMENT-CONSISTENCY")
    assert consistency.state is AssessmentState.INCONSISTENT
    assert full_case.passport.case_status is CaseStatus.ACTION_REQUIRED


def test_recheck_after_the_fix_clears_it(fixed_case, run_context):
    orchestrator.recheck(fixed_case, ctx=run_context)
    consistency = fixed_case.finding("F-REQ-DOCUMENT-CONSISTENCY")
    assert consistency.state is AssessmentState.SATISFIED
    assert fixed_case.passport.case_status is CaseStatus.VERIFICATION_REQUIRED


def test_a_failing_stage_preserves_the_case(profile, corpus, monkeypatch, run_context):
    """A failure stops the run without losing anything already computed."""
    case = ExportCase(case_id="BA-009", profile=profile)

    def boom(case_, ctx):
        raise RuntimeError("retrieval exploded")

    monkeypatch.setitem(orchestrator.STAGE_RUNNERS, StageName.REQUIREMENTS, boom)
    outcomes = orchestrator.run_to_completion(case, ctx=run_context)

    assert outcomes[-1].status is StageStatus.FAILED
    assert case.stage(StageName.PROFILE).status is StageStatus.COMPLETE
    assert case.stage(StageName.REQUIREMENTS).status is StageStatus.FAILED
    assert case.profile is not None  # the case survived
    assert case.case_id == "BA-009"
    assert orchestrator.failed_stage(case) is not None


def test_an_unsupported_market_fails_cleanly(corpus, run_context):
    from core.schemas import CaseProfile

    case = ExportCase(
        case_id="BA-010",
        profile=CaseProfile(product_raw="Leather bags", destination="Japan"),
    )
    outcomes = orchestrator.run_to_completion(case, ctx=run_context)

    failed = [o for o in outcomes if o.status is StageStatus.FAILED]
    assert failed
    assert "cannot state the requirements" in failed[0].message
    assert case.findings == []  # nothing was invented to fill the gap


def test_progress_reporting(full_case, run_context):
    done, total = orchestrator.progress(full_case)
    assert (done, total) == (0, 8)

    orchestrator.run_to_completion(full_case, ctx=run_context)
    done, total = orchestrator.progress(full_case)
    assert (done, total) == (8, 8)
    assert orchestrator.has_run(full_case)
