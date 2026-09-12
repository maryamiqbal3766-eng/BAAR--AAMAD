"""
BAAR-AAMAD — FINDINGS ENGINE
============================

The single source of truth for everything downstream. Reasoning, the action
plan and the Passport all read from findings and never re-derive a verdict of
their own.

Each finding answers the seven questions the specification requires of a
requirement card:

    1  What is needed?            requirement.what_is_required
    2  Why is it needed?          requirement.why_required
    3  What did we find?          finding.what_we_found
    4  What is missing?           finding.what_is_missing
    5  What should I provide?     finding.what_to_provide
    6  What happens next?         finding.next_action
    7  Why this conclusion?       finding.checks + evidence ids

Label and priority are never chosen here — they are derived from the state by
core.rules, so a finding cannot present itself as less serious than it is.
"""

from __future__ import annotations

from core.rules import label_for_state, priority_for_state, priority_rank
from core.schemas import (
    AssessmentState,
    CheckResult,
    DocumentType,
    ExportCase,
    Finding,
    Requirement,
)
from modules.corpus import Corpus, SourceRequirement, get_corpus
from modules.validation import run_checks, state_for

TYPE_NAMES: dict[DocumentType, str] = {
    DocumentType.COMMERCIAL_INVOICE: "Commercial Invoice",
    DocumentType.PACKING_LIST: "Packing List",
    DocumentType.CERTIFICATE_OF_ORIGIN: "Certificate of Origin",
    DocumentType.UNSUPPORTED: "unrecognised document",
}


def _friendly(key: str) -> str:
    """Turn 'COMMERCIAL_INVOICE.quantity' into 'Commercial Invoice quantity'."""
    document_part, _, field_part = key.partition(".")
    try:
        name = TYPE_NAMES[DocumentType(document_part)]
    except ValueError:
        name = document_part.replace("_", " ").title()
    return f"{name} {field_part.replace('_', ' ')}".strip()


def _what_we_found(
    state: AssessmentState, results: list[CheckResult], requirement: Requirement
) -> str:
    """Plain language describing what the documents actually showed."""
    if state is AssessmentState.SATISFIED:
        passed = [r for r in results if r.passed is True]
        return (
            "We checked your documents and found everything this requirement "
            f"asks for. {' '.join(r.detail for r in passed[:2])}".strip()
        )

    if state is AssessmentState.MISSING:
        failures = [r for r in results if r.passed is False]
        return " ".join(r.detail for r in failures) or "Required evidence is absent."

    if state is AssessmentState.INCONSISTENT:
        clashes = [r for r in results if r.passed is False]
        lines = []
        for result in clashes:
            stated = ", ".join(
                f"{_friendly(key)}: {value}"
                for key, value in result.compared.items()
                if value
            )
            lines.append(stated or result.detail)
        return "We found different values in your documents — " + "; ".join(lines) + "."

    if state is AssessmentState.REQUIRES_VERIFICATION:
        decided = [r for r in results if r.passed is True]
        if decided:
            return (
                "Your documents cover the part of this we can check. "
                f"{decided[0].detail} What remains cannot be settled from "
                "paperwork alone."
            )
        return (
            "This requirement cannot be settled from the documents you "
            "uploaded. It needs confirmation from a person."
        )

    return (
        "There was not enough information to assess this requirement against "
        "your documents."
    )


def _what_is_missing(
    state: AssessmentState, results: list[CheckResult], requirement: Requirement
) -> str:
    if state is AssessmentState.SATISFIED:
        return ""
    if state is AssessmentState.MISSING:
        return " ".join(r.detail for r in results if r.passed is False)
    if state is AssessmentState.INCONSISTENT:
        return (
            "The documents do not agree. One of them is wrong and needs to be "
            "corrected before this shipment is declared."
        )
    if state is AssessmentState.REQUIRES_VERIFICATION:
        return (
            "Confirmation that this requirement is met, from a person "
            "qualified to give it."
        )
    return "Enough information to make this assessment."


def _next_action(
    state: AssessmentState, requirement: Requirement, note: str
) -> str:
    if state is AssessmentState.SATISFIED:
        return "No action needed. Keep this evidence with your export file."
    if state is AssessmentState.MISSING:
        first = requirement.needed_document_or_info[0] if requirement.needed_document_or_info else "the missing evidence"
        return (
            f"Provide {first.lower()}, then run Recheck so BAAR-AAMAD can "
            "check it against this case."
        )
    if state is AssessmentState.INCONSISTENT:
        return (
            "Decide which document is correct, correct the other one, upload "
            "the corrected version, then run Recheck."
        )
    if state is AssessmentState.REQUIRES_VERIFICATION:
        return note or (
            "Confirm this with your customs broker or the relevant authority "
            "before shipping."
        )
    return "Upload the remaining documents so this can be assessed."


def build_finding(
    case: ExportCase,
    requirement: Requirement,
    source_requirement: SourceRequirement,
    use_ai: bool = True,
) -> Finding:
    """Assess one requirement against the case and describe the outcome."""
    results = run_checks(case, source_requirement, use_ai=use_ai)
    state = state_for(source_requirement, results)

    checked = (
        " ".join(check.description + "." for check in source_requirement.checks)
        or "Whether the evidence in this case settles this requirement."
    )

    document_ids = sorted(
        {
            document.document_id
            for document in case.documents
            if document.document_type in source_requirement.expected_document_types
        }
    )

    return Finding(
        finding_id=f"F-{requirement.requirement_id}",
        requirement_id=requirement.requirement_id,
        state=state,
        label=label_for_state(state),
        priority=priority_for_state(state),
        what_was_checked=checked,
        what_we_found=_what_we_found(state, results, requirement),
        what_is_missing=_what_is_missing(state, results, requirement),
        what_to_provide=list(requirement.needed_document_or_info),
        next_action=_next_action(
            state, requirement, source_requirement.verification_note
        ),
        checks=results,
        regulatory_evidence_ids=[e.evidence_id for e in requirement.evidence],
        document_ids=document_ids,
    )


def build_findings(
    case: ExportCase, corpus: Corpus | None = None, use_ai: bool = True
) -> list[Finding]:
    """Assess every requirement on the case, most urgent first.

    Human review decisions are carried across a rebuild, but ONLY while the
    finding's state is unchanged. A person verifies a particular situation; if
    re-reading the documents changes that situation, their decision no longer
    applies and the item returns to pending rather than a stale approval
    hiding a new problem.
    """
    corpus = corpus or get_corpus()
    by_id = {r.requirement_id: r for r in corpus.requirements}
    previous = {f.finding_id: f for f in case.findings}

    findings = []
    for requirement in case.requirements:
        source_requirement = by_id.get(requirement.requirement_id)
        if source_requirement is None:
            continue
        finding = build_finding(case, requirement, source_requirement, use_ai)

        earlier = previous.get(finding.finding_id)
        if earlier is not None and earlier.state is finding.state:
            finding.human_decision = earlier.human_decision

        findings.append(finding)

    findings.sort(key=lambda f: (priority_rank(f.priority), f.requirement_id))
    return findings


def all_checks(findings: list[Finding]) -> list[CheckResult]:
    """Every check run across the case, for the audit trail."""
    return [check for finding in findings for check in finding.checks]
