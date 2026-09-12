"""
BAAR-AAMAD — REQUIREMENT INTELLIGENCE
=====================================

    CASE PROFILE -> RAG -> SOURCE EVIDENCE -> STRUCTURED REQUIREMENTS

Turns retrieved source passages into the structured Requirement objects the
rest of the pipeline works from.

THE ABSOLUTE RULE, IMPLEMENTED TWICE OVER:

  * a requirement is only ever built from a curated source that was actually
    retrieved for this case — nothing is generated from a model's memory;
  * whatever happens, every requirement passes through
    core.rules.enforce_evidence_rule before it leaves this module, which
    forces REQUIRES VERIFICATION on anything lacking source evidence.

The optional LLM pass may only rephrase existing text into plainer language
for the exporter. It cannot add a requirement, drop one, change what evidence
would satisfy it, or touch a citation.
"""

from __future__ import annotations

import logging

from core.rules import enforce_evidence_rule
from core.schemas import (
    CaseProfile,
    ModuleResult,
    Requirement,
    VerificationStatus,
)
from modules.corpus import Corpus, SourceRequirement, get_corpus
from modules.retrieval import Hit, assess_coverage, search

log = logging.getLogger(__name__)


def to_requirement(
    source_requirement: SourceRequirement, corpus: Corpus, relevance: float = 0.0
) -> Requirement:
    """Build a contract Requirement from a curated one, carrying its citations."""
    evidence = corpus.evidence_for(source_requirement, relevance=relevance)

    # A requirement we cannot settle from documents alone is marked for
    # verification from the outset, not after it fails a check.
    status = (
        VerificationStatus.REQUIRES_VERIFICATION
        if source_requirement.verification_note or not source_requirement.checks
        else VerificationStatus.SUPPORTED_BY_SOURCE
    )

    requirement = Requirement(
        requirement_id=source_requirement.requirement_id,
        title=source_requirement.title,
        what_is_required=source_requirement.what_is_required,
        why_required=source_requirement.why_required,
        when_it_applies=source_requirement.when_it_applies,
        satisfying_evidence=list(source_requirement.satisfying_evidence),
        needed_document_or_info=list(source_requirement.needed_document_or_info),
        expected_document_types=list(source_requirement.expected_document_types),
        evidence=evidence,
        verification_status=status,
    )
    return enforce_evidence_rule(requirement)


def build_requirements(
    profile: CaseProfile, corpus: Corpus | None = None, use_ai: bool = True
) -> ModuleResult:
    """Find every requirement that applies to this case.

    Returns ok=False when the corpus has nothing for this product and market.
    That is a controlled outcome, not an error: the honest answer is that we
    cannot state requirements, never a guess at what they might be.
    """
    corpus = corpus or get_corpus()
    coverage = assess_coverage(profile, corpus)
    hits: list[Hit] = search(profile, corpus)

    if not hits:
        return ModuleResult(
            ok=False,
            reason=coverage.message,
            payload={"requirements": [], "coverage": coverage},
        )

    requirements = [to_requirement(hit.requirement, corpus, hit.score) for hit in hits]

    if use_ai:
        requirements = ai_plain_language(requirements)

    unsupported = [r.requirement_id for r in requirements if not r.evidence]
    if unsupported:  # should be impossible; loud if it ever happens
        log.error("requirements without evidence reached the case: %s", unsupported)

    return ModuleResult(
        ok=True,
        payload={
            "requirements": requirements,
            "coverage": coverage,
            "sources": sorted({e.source_name for r in requirements for e in r.evidence}),
        },
    )


def ai_plain_language(requirements: list[Requirement]) -> list[Requirement]:
    """Rewrite 'why it matters' for a non-specialist reader.

    Deliberately the narrowest possible use of a model in this module: it
    touches one explanatory sentence per requirement and nothing else. The
    requirement itself, the evidence, the citations and the verification
    status are untouched, so a bad rewrite costs clarity, never correctness.
    """
    from core import llm

    if not llm.is_configured() or not requirements:
        return requirements

    from pydantic import BaseModel, Field

    class Rewritten(BaseModel):
        explanations: dict[str, str] = Field(default_factory=dict)

    payload = "\n\n".join(
        f"[{r.requirement_id}]\nRequirement: {r.title}\n"
        f"Why: {r.why_required}\n"
        f"Source says: {' '.join(e.excerpt for e in r.evidence)}"
        for r in requirements
    )

    try:
        result = llm.complete_json(
            system=(
                "You rewrite export compliance explanations for a small "
                "business owner who is not a lawyer. Keep every fact and every "
                "number exactly as given. Do not add requirements, do not cite "
                "anything that is not already quoted, do not soften or "
                "strengthen what the source says. Two or three short sentences "
                "per requirement, keyed by its identifier."
            ),
            user=payload,
            schema=Rewritten,
            tier=llm.Tier.REASONING,
            max_tokens=1600,
        )
    except Exception as exc:
        log.warning("Plain-language pass unavailable, keeping curated text: %s", exc)
        return requirements

    by_id = {r.requirement_id: r for r in requirements}
    for requirement_id, explanation in result.explanations.items():
        requirement = by_id.get(requirement_id)
        if requirement and explanation and explanation.strip():
            requirement.why_required = explanation.strip()

    return requirements


def source_requirement_for(
    requirement_id: str, corpus: Corpus | None = None
) -> SourceRequirement | None:
    """The curated definition behind a requirement, including its checks."""
    corpus = corpus or get_corpus()
    return next(
        (r for r in corpus.requirements if r.requirement_id == requirement_id), None
    )
