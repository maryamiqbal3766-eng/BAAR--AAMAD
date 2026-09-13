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

WHICH PARTS THE MODEL MAY WRITE
-------------------------------
When AI is available, modules.interpretation gives the model the retrieved
passages and asks it to state the requirement from them. What comes back is
gated on grounding before any of it is used, and anything rejected keeps the
curated wording.

What the model may write is the PROSE: the title, what is required, why, when
it applies, and what would satisfy it. What it may never touch is the
STRUCTURE: which sources were retrieved, the citations, the expected document
types, the deterministic checks, and the verification status. Those decide
what is actually checked, and they stay in the corpus and in Python.
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
        # THE RAG STEP. The retrieved passages go to the model and come back
        # as this case's requirements. See modules/interpretation.py for what
        # the model is and is not shown, and for the grounding gate that
        # decides whether any of its answer may be used.
        from modules.interpretation import interpret

        requirements = interpret(profile, requirements)
        # The gate can only ever leave a requirement with its curated wording,
        # so the invariant below still holds on the AI path.
        requirements = [enforce_evidence_rule(r) for r in requirements]

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


def source_requirement_for(
    requirement_id: str, corpus: Corpus | None = None
) -> SourceRequirement | None:
    """The curated definition behind a requirement, including its checks."""
    corpus = corpus or get_corpus()
    return next(
        (r for r in corpus.requirements if r.requirement_id == requirement_id), None
    )
