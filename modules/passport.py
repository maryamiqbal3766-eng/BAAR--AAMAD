"""
BAAR-AAMAD — COMPLIANCE PASSPORT
================================

The flagship output. Section order is fixed by the specification:

    PRODUCT
    DESTINATION
    CASE STATUS
    REQUIREMENTS        tallied by the four user-facing labels
    KEY ISSUES          up to three
    NEXT ACTIONS        up to three
    EVIDENCE            REQUIREMENT -> SOURCE -> DOCUMENT EVIDENCE -> FINDING

Everything here is assembled from the case. Nothing is written by a model,
nothing is summarised into something the findings did not say, and there is
no score — a case is described, never graded.
"""

from __future__ import annotations

from core.rules import (
    KEY_ISSUES_LIMIT,
    NEXT_ACTIONS_LIMIT,
    case_status_for,
    priority_rank,
    tally_labels,
)
from core.schemas import (
    AssessmentState,
    DocumentType,
    EvidenceMapRow,
    ExportCase,
    Finding,
    Passport,
)
from modules.findings import TYPE_NAMES, _friendly


def _key_issues(case: ExportCase) -> list[str]:
    """The most serious unresolved findings, worst first."""
    open_findings = [
        finding
        for finding in case.findings
        if finding.state is not AssessmentState.SATISFIED
        and finding.human_decision.value == "PENDING"
    ]
    open_findings.sort(key=lambda f: (priority_rank(f.priority), f.requirement_id))

    issues = []
    for finding in open_findings[:KEY_ISSUES_LIMIT]:
        requirement = case.requirement(finding.requirement_id)
        title = requirement.title if requirement else finding.requirement_id
        issues.append(f"{title} — {finding.label.value}")
    return issues


def _next_actions(case: ExportCase) -> list[str]:
    """The first few things to do, taken verbatim from the action plan."""
    if case.action_plan:
        return [item.action_required for item in case.action_plan[:NEXT_ACTIONS_LIMIT]]
    return [
        finding.next_action
        for finding in case.findings
        if finding.state is not AssessmentState.SATISFIED
    ][:NEXT_ACTIONS_LIMIT]


def _document_summary(case: ExportCase, finding: Finding) -> str:
    """What the exporter's documents contributed to this finding."""
    values: list[str] = []
    seen: set[str] = set()
    for check in finding.checks:
        for key, value in check.compared.items():
            if value is None or key in seen:
                continue
            seen.add(key)
            values.append(f"{_friendly(key)}: {value}")
    if values:
        return "; ".join(values[:4])

    names = [
        f"{TYPE_NAMES.get(d.document_type, 'Document')} ({d.filename})"
        for d in case.documents
        if d.document_id in finding.document_ids
    ]
    return "; ".join(names) or "No document evidence"


def build_evidence_map(case: ExportCase) -> list[EvidenceMapRow]:
    """REQUIREMENT -> SOURCE -> DOCUMENT EVIDENCE -> FINDING, one row each."""
    rows: list[EvidenceMapRow] = []

    for finding in case.findings:
        requirement = case.requirement(finding.requirement_id)
        if requirement is None:
            continue

        first = requirement.evidence[0] if requirement.evidence else None
        source_name = first.source_name if first else "No source evidence"
        if first and first.locator:
            source_name = f"{source_name} ({first.locator})"

        rows.append(
            EvidenceMapRow(
                requirement=requirement.title,
                source=source_name,
                source_url=first.source_url if first else "",
                document_evidence=_document_summary(case, finding),
                finding=finding.label.value,
            )
        )
    return rows


def build_passport(case: ExportCase) -> Passport:
    """Assemble the Passport from the case as it currently stands."""
    profile = case.profile
    return Passport(
        case_id=case.case_id,
        product=(profile.product_normalized or profile.product_raw) if profile else "",
        destination=profile.destination if profile else "",
        case_status=case_status_for(case.findings),
        requirement_tally=tally_labels([f.label for f in case.findings]),
        key_issues=_key_issues(case),
        next_actions=_next_actions(case),
        evidence_map=build_evidence_map(case),
        run_number=case.run_number,
    )


def as_plain_text(passport: Passport) -> str:
    """A copyable version of the Passport, in the specification's order."""
    lines = [
        "BAAR-AAMAD EXPORT READINESS PASSPORT",
        "",
        f"CASE          {passport.case_id}",
        f"PRODUCT       {passport.product}",
        f"DESTINATION   {passport.destination}",
        f"CASE STATUS   {passport.case_status.value}",
        f"GENERATED     {passport.generated_at:%d %b %Y %H:%M} UTC (run {passport.run_number})",
        "",
        "REQUIREMENTS",
    ]
    lines += [
        f"  {count}  {label.value}" for label, count in passport.requirement_tally.items()
    ]

    lines += ["", "KEY ISSUES"]
    lines += (
        [f"  {i}. {issue}" for i, issue in enumerate(passport.key_issues, 1)]
        or ["  None outstanding."]
    )

    lines += ["", "NEXT ACTIONS"]
    lines += (
        [f"  {i}. {action}" for i, action in enumerate(passport.next_actions, 1)]
        or ["  None outstanding."]
    )

    lines += ["", "EVIDENCE", "  Requirement -> Source -> Document evidence -> Finding"]
    for row in passport.evidence_map:
        lines += [
            "",
            f"  {row.requirement}",
            f"    Source:   {row.source}",
            f"    URL:      {row.source_url}",
            f"    Document: {row.document_evidence}",
            f"    Finding:  {row.finding}",
        ]

    lines += [
        "",
        "BAAR-AAMAD provides evidence-backed decision support. Final compliance",
        "responsibility remains with the exporter and the relevant authorities.",
    ]
    return "\n".join(lines)
