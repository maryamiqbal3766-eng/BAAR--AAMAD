"""
BAAR-AAMAD — TWO-ENGINE VALIDATION
==================================

                          EVIDENCE
                             |
              +--------------+--------------+
              |                             |
     DETERMINISTIC ENGINE            AI SEMANTIC ENGINE
     exact values, presence          meaning, wording variation
     dates, quantities, ids          "same thing, said differently"
              |                             |
              +--------------+--------------+
                             |
                      FINDINGS ENGINE

The deterministic engine decides everything that can be decided exactly:

    Quantity = 500 on the invoice
    Quantity = 450 on the packing list
    -> INCONSISTENT.  No model required, and none permitted.

The semantic engine is only consulted for text fields that disagree
literally, to answer one narrow question: is this the same thing written
differently? "Sialkot Leather Crafts (Pvt) Ltd" against "Sialkot Leather
Crafts Private Limited" is an equivalence, not a contradiction. It can
downgrade a literal mismatch to agreement; it can never create a mismatch,
and it is never consulted about a number.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from core.schemas import (
    AssessmentState,
    CheckMethod,
    CheckResult,
    DocumentEvidence,
    DocumentType,
    ExportCase,
)
from modules.corpus import Check, SourceRequirement

log = logging.getLogger(__name__)

#: Corporate forms that carry no identifying information when comparing names.
_COMPANY_NOISE = re.compile(
    r"\b(pvt|private|ltd|limited|llc|inc|incorporated|gmbh|co|company|corp|"
    r"corporation|plc|sa|bv|nv|kg|ag)\b",
    re.I,
)


def normalize_text(value: str) -> str:
    """Fold away differences that carry no meaning for a comparison."""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    folded = folded.lower().replace("&", " and ")
    folded = _COMPANY_NOISE.sub(" ", folded)
    folded = re.sub(r"[^a-z0-9 ]+", " ", folded)
    return " ".join(folded.split())


def normalize_number(value: str) -> float | None:
    """The numeric value of a field, or None if it does not hold one."""
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def values_agree(left: str, right: str, compare: str) -> bool | None:
    """Do two field values say the same thing? None when undecidable."""
    if compare == "number":
        left_number, right_number = normalize_number(left), normalize_number(right)
        if left_number is None or right_number is None:
            return None
        return left_number == right_number

    left_text, right_text = normalize_text(left), normalize_text(right)
    if not left_text or not right_text:
        return None
    return left_text == right_text


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------


def _readable_document(
    case: ExportCase, document_type: DocumentType
) -> DocumentEvidence | None:
    """A document only counts as present if we could actually read it."""
    document = case.document(document_type)
    return document if document and document.readable else None


def _check_id(requirement_id: str, index: int) -> str:
    return f"{requirement_id}#c{index + 1}"


def _run_document_present(
    case: ExportCase, requirement_id: str, check: Check, index: int
) -> CheckResult:
    document = _readable_document(case, check.document_type)
    attached = case.document(check.document_type)

    if document is not None:
        detail = f"{document.filename} was provided and read."
    elif attached is not None:
        detail = (
            f"{attached.filename} was provided but could not be read, so it "
            f"cannot support this requirement."
        )
    else:
        detail = "No document of this type has been provided for this case."

    return CheckResult(
        check_id=_check_id(requirement_id, index),
        requirement_id=requirement_id,
        method=CheckMethod.DETERMINISTIC,
        description=check.description,
        passed=document is not None,
        detail=detail,
        compared={check.document_type.value: document.filename if document else None},
    )


def _run_fields_present(
    case: ExportCase, requirement_id: str, check: Check, index: int
) -> CheckResult:
    document = _readable_document(case, check.document_type)
    if document is None:
        return CheckResult(
            check_id=_check_id(requirement_id, index),
            requirement_id=requirement_id,
            method=CheckMethod.DETERMINISTIC,
            description=check.description,
            passed=None,
            detail="Cannot be checked: the document itself is not available.",
        )

    missing = [name for name in check.fields if not document.get(name)]
    compared = {
        f"{check.document_type.value}.{name}": document.get(name)
        for name in check.fields
    }

    detail = (
        "Every required value was found."
        if not missing
        else f"Not found in {document.filename}: {', '.join(missing)}."
    )
    return CheckResult(
        check_id=_check_id(requirement_id, index),
        requirement_id=requirement_id,
        method=CheckMethod.DETERMINISTIC,
        description=check.description,
        passed=not missing,
        detail=detail,
        compared=compared,
    )


def _run_fields_agree(
    case: ExportCase, requirement_id: str, check: Check, index: int, use_ai: bool
) -> CheckResult:
    """Compare one field across the documents that carry it."""
    field_name = check.fields[0] if check.fields else ""
    present: dict[str, tuple[str, DocumentEvidence]] = {}

    for document_type in check.document_types:
        document = _readable_document(case, document_type)
        if document is None:
            continue
        value = document.get(field_name)
        if value:
            present[document_type.value] = (value, document)

    compared = {f"{key}.{field_name}": value for key, (value, _) in present.items()}
    check_id = _check_id(requirement_id, index)

    if len(present) < 2:
        return CheckResult(
            check_id=check_id,
            requirement_id=requirement_id,
            method=CheckMethod.DETERMINISTIC,
            description=check.description,
            passed=None,
            detail=(
                "Fewer than two documents state this value, so there is "
                "nothing to compare yet."
            ),
            compared=compared,
        )

    keys = list(present)
    baseline_key = keys[0]
    baseline_value = present[baseline_key][0]
    disagreements: list[str] = []
    undecidable = False

    for other_key in keys[1:]:
        other_value = present[other_key][0]
        verdict = values_agree(baseline_value, other_value, check.compare)
        if verdict is None:
            undecidable = True
        elif not verdict:
            disagreements.append(other_key)

    if not disagreements:
        if undecidable:
            return CheckResult(
                check_id=check_id,
                requirement_id=requirement_id,
                method=CheckMethod.DETERMINISTIC,
                description=check.description,
                passed=None,
                detail="These values could not be compared reliably.",
                compared=compared,
            )
        return CheckResult(
            check_id=check_id,
            requirement_id=requirement_id,
            method=CheckMethod.DETERMINISTIC,
            description=check.description,
            passed=True,
            detail=f"All documents state the same value: {baseline_value}.",
            compared=compared,
        )

    # A literal text mismatch may still be the same thing said differently.
    # Numbers are never sent to the model: 500 is not 450, in any wording.
    if use_ai and check.compare == "text":
        equivalent, why = ai_same_thing(field_name, compared)
        if equivalent:
            return CheckResult(
                check_id=check_id,
                requirement_id=requirement_id,
                method=CheckMethod.SEMANTIC,
                description=check.description,
                passed=True,
                detail=why or "These entries refer to the same thing.",
                compared=compared,
            )

    readable = ", ".join(
        f"{key.replace('_', ' ').title()}: {value}"
        for key, value in (
            (key, present[key][0]) for key in keys
        )
    )
    return CheckResult(
        check_id=check_id,
        requirement_id=requirement_id,
        method=CheckMethod.DETERMINISTIC,
        description=check.description,
        passed=False,
        detail=f"These documents disagree — {readable}.",
        compared=compared,
    )


def ai_same_thing(field_name: str, values: dict[str, str | None]) -> tuple[bool, str]:
    """Is a literal mismatch actually an equivalence?

    Narrow by design. The model is asked one yes/no question about wording,
    and only ever to REMOVE a false alarm. If it is unavailable or unsure,
    the deterministic mismatch stands — which is the specification's rule
    that a failed semantic comparison falls back to structured checks.
    """
    from core import llm

    if not llm.is_configured():
        llm.record_skipped(
            "validation.semantic_comparison",
            llm.Tier.REASONING,
            "no API key; the literal mismatch stands",
        )
        return False, ""

    from pydantic import BaseModel

    class Verdict(BaseModel):
        same: bool
        reason: str = ""

    listing = "\n".join(f"- {key}: {value}" for key, value in values.items())
    try:
        verdict = llm.complete_json(
            system=(
                "You judge whether trade document entries refer to the same "
                "real-world thing despite different wording — abbreviations, "
                "legal suffixes, spelling variants, word order. Answer true "
                "only if you are confident they are the same. Different "
                "quantities, amounts, dates or reference numbers are never "
                "the same. When in doubt answer false."
            ),
            user=f"Field: {field_name}\nEntries:\n{listing}\n\nSame thing?",
            schema=Verdict,
            tier=llm.Tier.REASONING,
            max_tokens=300,
            call_site="validation.semantic_comparison",
        )
    except Exception as exc:
        log.warning("Semantic comparison unavailable, keeping literal result: %s", exc)
        return False, ""

    return bool(verdict.same), verdict.reason.strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_RUNNERS = {
    "document_present": _run_document_present,
    "fields_present": _run_fields_present,
}


def run_checks(
    case: ExportCase, source_requirement: SourceRequirement, use_ai: bool = True
) -> list[CheckResult]:
    """Run every check a curated requirement declares, in order."""
    results: list[CheckResult] = []
    for index, check in enumerate(source_requirement.checks):
        requirement_id = source_requirement.requirement_id
        if check.kind == "fields_agree":
            results.append(
                _run_fields_agree(case, requirement_id, check, index, use_ai)
            )
        else:
            runner = _RUNNERS.get(check.kind)
            if runner is None:  # the corpus loader rejects unknown kinds
                log.error("no runner for check kind %r", check.kind)
                continue
            results.append(runner(case, requirement_id, check, index))
    return results


def state_for(
    source_requirement: SourceRequirement, results: list[CheckResult]
) -> AssessmentState:
    """Decide a requirement's internal state from its check results.

    Order matters, and is deterministic:

      no checks at all              -> REQUIRES_VERIFICATION
      something required is absent  -> MISSING
      documents contradict          -> INCONSISTENT
      everything passed             -> SATISFIED, unless the curated source
                                       says a human must confirm it
      nothing could be decided      -> NOT_ASSESSED
    """
    if not source_requirement.checks:
        return AssessmentState.REQUIRES_VERIFICATION

    paired = list(zip(results, source_requirement.checks, strict=False))

    failed_presence = any(
        result.passed is False and check.kind in ("document_present", "fields_present")
        for result, check in paired
    )
    if failed_presence:
        return AssessmentState.MISSING

    if any(result.passed is False for result in results):
        return AssessmentState.INCONSISTENT

    if all(result.passed is True for result in results):
        if source_requirement.verification_note:
            return AssessmentState.REQUIRES_VERIFICATION
        return AssessmentState.SATISFIED

    return AssessmentState.NOT_ASSESSED
