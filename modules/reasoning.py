"""
BAAR-AAMAD — REASONING
======================

Builds the chain behind the "Why did BAAR-AAMAD flag this?" button. The
specification fixes both its shape and its order:

    Requirement
        -> Source evidence
        -> Your document evidence
        -> Comparison
        -> Conclusion
        -> What you need to do

Five of those six links are QUOTED, not written: the requirement text, the
source excerpt with its citation, the values read from the exporter's own
documents, and the next action all come straight from the case. Only the
comparison and the conclusion are prose, and even those are assembled from
the deterministic check results before any model is involved.

An optional LLM pass may make those two links read more naturally. It is
given the finished chain and may only rewrite wording — it never sees a
choice to make, because the verdict was already decided by Python.
"""

from __future__ import annotations

import logging

from core.schemas import (
    AssessmentState,
    ExportCase,
    Finding,
    ReasoningTrace,
)
from modules.findings import TYPE_NAMES, _friendly

log = logging.getLogger(__name__)


def _source_evidence(case: ExportCase, finding: Finding) -> str:
    """The quoted passages behind this requirement, with their citations."""
    lines = []
    for evidence_id in finding.regulatory_evidence_ids:
        evidence = case.evidence(evidence_id)
        if evidence is None:
            continue
        locator = f", {evidence.locator}" if evidence.locator else ""
        lines.append(f'"{evidence.excerpt}"\n— {evidence.source_name}{locator}')
    return "\n\n".join(lines) or "No source evidence is attached to this finding."


def _document_evidence(case: ExportCase, finding: Finding) -> str:
    """What the exporter's own documents say, value by value."""
    lines: list[str] = []
    seen: set[str] = set()

    for check in finding.checks:
        for key, value in check.compared.items():
            if value is None or key in seen:
                continue
            seen.add(key)
            lines.append(f"{_friendly(key)}: {value}")

    if lines:
        return "\n".join(lines)

    if not case.documents:
        return "No documents have been uploaded to this case."

    named = ", ".join(
        f"{TYPE_NAMES.get(d.document_type, 'Document')} ({d.filename})"
        for d in case.documents
    )
    return f"Nothing in the uploaded documents bears on this requirement. Read: {named}."


def _comparison(finding: Finding) -> str:
    """What was compared against what, and how each comparison came out."""
    if not finding.checks:
        return (
            "This requirement was not compared against your documents, because "
            "paperwork alone cannot settle it."
        )

    lines = []
    for check in finding.checks:
        if check.passed is True:
            mark = "Agrees"
        elif check.passed is False:
            mark = "Does not agree"
        else:
            mark = "Could not be determined"
        engine = "checked exactly" if check.method.value == "DETERMINISTIC" else "read for meaning"
        lines.append(f"{mark} — {check.description} ({engine}). {check.detail}")
    return "\n".join(lines)


def _conclusion(finding: Finding) -> str:
    if finding.state is AssessmentState.SATISFIED:
        return (
            "Your documents provide what this requirement asks for, so it is "
            "recorded as complete for this case."
        )
    if finding.state is AssessmentState.MISSING:
        return (
            "Evidence this requirement depends on is not present in your case, "
            "so it cannot be treated as met."
        )
    if finding.state is AssessmentState.INCONSISTENT:
        return (
            "Your documents describe the same shipment but state different "
            "values, so they cannot all be correct. The difference has to be "
            "resolved before this case is consistent."
        )
    if finding.state is AssessmentState.REQUIRES_VERIFICATION:
        return (
            "BAAR-AAMAD cannot settle this from the evidence available, so it "
            "is marked for human verification rather than assumed either way."
        )
    return (
        "There was not enough information to assess this requirement, so no "
        "conclusion has been drawn."
    )


def build_trace(case: ExportCase, finding: Finding) -> ReasoningTrace:
    """Assemble one finding's six-link explanation. Deterministic."""
    requirement = case.requirement(finding.requirement_id)
    requirement_text = (
        f"{requirement.title} — {requirement.what_is_required}"
        if requirement
        else finding.requirement_id
    )

    return ReasoningTrace(
        finding_id=finding.finding_id,
        requirement=requirement_text,
        source_evidence=_source_evidence(case, finding),
        your_document_evidence=_document_evidence(case, finding),
        comparison=_comparison(finding),
        conclusion=_conclusion(finding),
        what_you_need_to_do=finding.next_action,
    )


def build_traces(case: ExportCase, use_ai: bool = True) -> list[ReasoningTrace]:
    """One explanation per finding, in the findings' own order."""
    traces = [build_trace(case, finding) for finding in case.findings]
    if use_ai:
        traces = ai_polish(case, traces)
    return traces


def ai_polish(case: ExportCase, traces: list[ReasoningTrace]) -> list[ReasoningTrace]:
    """Make the conclusion read like a person wrote it.

    Only `conclusion` is offered for rewriting, and only for findings that
    already have a verdict. The model cannot change the verdict, the evidence,
    the comparison or the action — those are quoted from the case. If it is
    unavailable, the assembled wording stands.
    """
    from core import llm

    if not llm.is_configured() or not traces:
        return traces

    from pydantic import BaseModel, Field

    class Polished(BaseModel):
        conclusions: dict[str, str] = Field(default_factory=dict)

    payload = "\n\n".join(
        f"[{trace.finding_id}]\n"
        f"Requirement: {trace.requirement}\n"
        f"What the documents show: {trace.your_document_evidence}\n"
        f"Comparison: {trace.comparison}\n"
        f"Current wording: {trace.conclusion}"
        for trace in traces
    )

    try:
        result = llm.complete_json(
            system=(
                "You rewrite a compliance conclusion for a small exporter. "
                "Keep the verdict exactly as it is — never soften a problem, "
                "never declare something resolved, never add a requirement or "
                "a source. Restate the same conclusion in two plain sentences, "
                "referring to the specific values shown. Key each by its "
                "finding identifier."
            ),
            user=payload,
            schema=Polished,
            tier=llm.Tier.REASONING,
            max_tokens=1800,
        )
    except Exception as exc:
        log.warning("Reasoning polish unavailable, keeping assembled text: %s", exc)
        return traces

    by_id = {trace.finding_id: trace for trace in traces}
    for finding_id, conclusion in result.conclusions.items():
        trace = by_id.get(finding_id)
        if trace and conclusion and conclusion.strip():
            trace.conclusion = conclusion.strip()
    return traces
