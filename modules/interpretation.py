"""
BAAR-AAMAD — EVIDENCE INTERPRETATION
====================================

    RETRIEVED CHUNK -> AI INTERPRETATION -> STRUCTURED REQUIREMENT

This is the RAG step. The model is given the verbatim passages retrieval found
for this case, and nothing else, and asked what they require of this exporter.

WHAT THE MODEL IS GIVEN
-----------------------
  * the case: the goods as the exporter described them, origin, destination
  * the retrieved passages: chunk id, locator, and the exact text

WHAT THE MODEL IS NOT GIVEN
---------------------------
  * the curated prose for these requirements. It is not asked to rephrase an
    answer it can already see; it is asked to read the law and state the
    requirement. Handing it the curated wording would make this a paraphrase
    step wearing a RAG costume.
  * the deterministic checks, or which document types satisfy a requirement.
    Those are curated, Python runs them, and they are not the model's to
    choose. This is the line between "AI interprets" and "code verifies".

THE GROUNDING GATE
------------------
Everything the model returns is checked, in Python, before any of it is used:

  1. it must cite at least one passage, by id;
  2. every id it cites must be one that was actually retrieved for this case;
  3. it must not introduce a citation — a URL, a regulation number, an article
     reference — that does not appear in the passages it was given;
  4. the text must be non-trivial and within sane length.

A requirement that fails any of these keeps its curated wording and records
why. Failure is per requirement: one bad entry in a batch does not discard the
others.

That gate is the whole point. "The model cited a source" is worth nothing if
nobody checked that the source exists and was retrieved.
"""

from __future__ import annotations

import logging
import re

from core.schemas import (
    CaseProfile,
    Interpretation,
    InterpretationSource,
    Requirement,
)

log = logging.getLogger(__name__)

#: Fields the model is allowed to author. Everything else on a Requirement —
#: the id, the evidence, the citations, the expected document types, the
#: verification status — is structural and is never up for interpretation.
INTERPRETABLE_FIELDS = (
    "title",
    "what_is_required",
    "why_required",
    "when_it_applies",
    "satisfying_evidence",
    "needed_document_or_info",
)

#: Sanity bounds. A one-word "requirement" is not an interpretation, and a
#: thousand-word one is the model having written an essay instead.
MIN_STATEMENT_CHARS = 20
MAX_STATEMENT_CHARS = 1200
MAX_LIST_ITEMS = 6

#: Citation shapes the model must not introduce on its own. If one of these
#: appears in the output, the exact same string has to appear in the passages
#: the model was shown.
_CITATION_PATTERNS = (
    re.compile(r"https?://\S+"),
    re.compile(r"\bregulation\s*\(e[uc]\)\s*no\.?\s*[\d/]+", re.I),
    re.compile(r"\bdirective\s*\d+/\d+(/[a-z]+)?", re.I),
    re.compile(r"\barticle\s+\d+[a-z]?(\(\d+\))?", re.I),
    re.compile(r"\bannex\s+[ivxlc]+\b", re.I),
    re.compile(r"\bentry\s+\d+\b", re.I),
)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase with runs of non-alphanumerics flattened, for containment
    tests that should not care about spacing or punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def invented_citations(text: str, evidence_text: str) -> list[str]:
    """Citations in `text` that do not appear in the passages given.

    This is the non-fabrication rule made mechanical. A model that writes
    "Article 163" when Article 163 was in front of it is quoting; a model that
    writes "Article 12" when it was not is inventing, and the difference is
    decidable without asking the model anything.
    """
    haystack = _normalize(evidence_text)
    invented = []
    for pattern in _CITATION_PATTERNS:
        for match in pattern.findall(text):
            # findall returns tuples when a pattern has groups; we want the
            # whole match, so re-search for it.
            found = match if isinstance(match, str) else ""
            if not found:
                continue
            if _normalize(found) not in haystack:
                invented.append(found.strip())
    for match in re.finditer(r"\barticle\s+\d+[a-z]?", text, re.I):
        if _normalize(match.group(0)) not in haystack:
            invented.append(match.group(0))
    return sorted(set(invented))


def gate(
    proposal: dict[str, object],
    allowed_chunk_ids: set[str],
    evidence_text: str,
) -> tuple[dict[str, object], list[str], str]:
    """Decide what, if anything, of one proposed interpretation may be used.

    Returns (accepted fields, chunk ids cited, rejection reason). A non-empty
    reason means nothing was accepted.
    """
    cited = [str(c).strip() for c in (proposal.get("grounded_in") or []) if str(c).strip()]
    if not cited:
        return {}, [], "the model cited no retrieved passage"

    unknown = [c for c in cited if c not in allowed_chunk_ids]
    if unknown:
        # The serious one. A citation to something not retrieved is either a
        # hallucinated id or a passage from another case; either way nothing
        # in this response can be trusted.
        return {}, [], f"cited passages that were not retrieved: {', '.join(unknown)}"

    accepted: dict[str, object] = {}
    for name in INTERPRETABLE_FIELDS:
        value = proposal.get(name)
        if value is None:
            continue

        if isinstance(value, list):
            items = [str(v).strip() for v in value if str(v).strip()]
            items = [i for i in items if len(i) <= MAX_STATEMENT_CHARS][:MAX_LIST_ITEMS]
            if not items:
                continue
            fabricated = [c for i in items for c in invented_citations(i, evidence_text)]
            if fabricated:
                return {}, [], f"introduced citations not in the evidence: {', '.join(sorted(set(fabricated)))}"
            accepted[name] = items
            continue

        text = str(value).strip()
        if not text:
            continue
        # `title` is a label, so it is exempt from the prose length floor.
        floor = 3 if name == "title" else MIN_STATEMENT_CHARS
        if not (floor <= len(text) <= MAX_STATEMENT_CHARS):
            continue
        fabricated = invented_citations(text, evidence_text)
        if fabricated:
            return {}, [], f"introduced citations not in the evidence: {', '.join(fabricated)}"
        accepted[name] = text

    if not accepted:
        return {}, [], "the model returned nothing usable"
    return accepted, cited, ""


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------


SYSTEM = """\
You are an export compliance analyst. You are given passages quoted verbatim \
from authoritative regulatory sources, and an export case. For each \
requirement listed, read ONLY the passages attached to it and state what that \
law requires of this exporter.

Absolute rules:
- Use only what the passages say. You have no other knowledge of this law.
- Never name a regulation, article, annex, entry number or URL that does not \
appear word-for-word in the passages you were given.
- Never state a threshold, quantity, date or figure that is not in the passages.
- If the passages do not settle something, say so plainly rather than filling \
the gap.
- Write for a small business owner who is not a lawyer. Short sentences.
- In grounded_in, list the exact passage ids you used for that requirement.

You are interpreting evidence, not deciding compliance. Do not say whether \
this exporter complies, and do not invent what their documents contain.\
"""


def _evidence_block(requirements: list[Requirement]) -> tuple[str, set[str], str]:
    """The passages, formatted for the prompt.

    Returns the prompt block, the set of ids the model may cite, and the
    concatenated raw text the grounding gate checks citations against.
    """
    lines: list[str] = []
    allowed: set[str] = set()
    raw: list[str] = []

    seen: set[str] = set()
    for requirement in requirements:
        for evidence in requirement.evidence:
            if evidence.evidence_id in seen:
                continue
            seen.add(evidence.evidence_id)
            allowed.add(evidence.evidence_id)
            raw.append(f"{evidence.locator} {evidence.excerpt} {evidence.source_name}")
            lines.append(
                f"[{evidence.evidence_id}]\n"
                f"Source: {evidence.source_name}\n"
                f"Locator: {evidence.locator}\n"
                f"Text: {evidence.excerpt}"
            )
    return "\n\n".join(lines), allowed, "\n".join(raw)


def build_prompt(profile: CaseProfile, requirements: list[Requirement]) -> tuple[str, set[str], str]:
    passages, allowed, raw = _evidence_block(requirements)

    wanted = "\n".join(
        f"- {r.requirement_id} — interpret from passages: "
        f"{', '.join(e.evidence_id for e in r.evidence)}"
        for r in requirements
    )

    prompt = (
        "EXPORT CASE\n"
        f"  Goods, as the exporter described them: {profile.product_raw}\n"
        f"  Origin: {profile.origin_country or 'not stated'}\n"
        f"  Destination: {profile.destination or 'not stated'}\n"
    )
    if profile.product_characteristics:
        prompt += "  Observed characteristics: " + "; ".join(
            profile.product_characteristics
        ) + "\n"

    prompt += (
        f"\nRETRIEVED PASSAGES\n\n{passages}\n\n"
        f"REQUIREMENTS TO INTERPRET\n{wanted}\n"
    )
    return prompt, allowed, raw


def interpret(
    profile: CaseProfile, requirements: list[Requirement]
) -> list[Requirement]:
    """Replace curated prose with the model's reading of the evidence.

    Mutates and returns the same Requirement objects. Anything the gate
    rejects keeps the wording it already had, so the worst case of this
    function is the behaviour of the function not existing.
    """
    from core import llm

    if not requirements:
        return requirements

    if not llm.is_configured():
        llm.record_skipped(
            "requirements.interpret_evidence",
            llm.Tier.REASONING,
            "no API key; requirements keep their curated wording",
        )
        for requirement in requirements:
            requirement.interpretation = Interpretation(
                source=InterpretationSource.CURATED,
                fallback_reason="the AI service is not configured",
            )
        return requirements

    from pydantic import BaseModel, Field

    class ReadRequirement(BaseModel):
        requirement_id: str
        title: str = ""
        what_is_required: str = ""
        why_required: str = ""
        when_it_applies: str = ""
        satisfying_evidence: list[str] = Field(default_factory=list)
        needed_document_or_info: list[str] = Field(default_factory=list)
        grounded_in: list[str] = Field(default_factory=list)

    class Reading(BaseModel):
        requirements: list[ReadRequirement] = Field(default_factory=list)

    user, allowed, raw_evidence = build_prompt(profile, requirements)

    try:
        reading = llm.complete_json(
            system=SYSTEM,
            user=user,
            schema=Reading,
            tier=llm.Tier.REASONING,
            max_tokens=3000,
            call_site="requirements.interpret_evidence",
        )
    except Exception as exc:
        log.warning("Evidence interpretation unavailable, keeping curated text: %s", exc)
        for requirement in requirements:
            requirement.interpretation = Interpretation(
                source=InterpretationSource.CURATED,
                fallback_reason="the AI service did not return a usable reading",
            )
        return requirements

    model = next(
        (c.model for c in reversed(llm.ledger())
         if c.call_site == "requirements.interpret_evidence" and c.model),
        "",
    )
    proposals = {r.requirement_id: r for r in reading.requirements}

    for requirement in requirements:
        proposal = proposals.get(requirement.requirement_id)
        if proposal is None:
            requirement.interpretation = Interpretation(
                source=InterpretationSource.CURATED,
                model=model,
                fallback_reason="the model did not return a reading for this requirement",
            )
            continue

        # Only the evidence retrieved FOR THIS REQUIREMENT may support it.
        # Allowing any retrieved passage would let a customs passage justify a
        # chemical requirement.
        own_ids = {e.evidence_id for e in requirement.evidence}
        accepted, cited, reason = gate(
            proposal.model_dump(), own_ids & allowed, raw_evidence
        )

        if reason:
            log.info(
                "interpretation rejected for %s: %s", requirement.requirement_id, reason
            )
            requirement.interpretation = Interpretation(
                source=InterpretationSource.CURATED,
                model=model,
                fallback_reason=reason,
            )
            continue

        for name, value in accepted.items():
            setattr(requirement, name, value)

        requirement.interpretation = Interpretation(
            source=InterpretationSource.AI_INTERPRETED,
            model=model,
            grounded_in=cited,
            fields_from_ai=sorted(accepted),
        )

    return requirements
