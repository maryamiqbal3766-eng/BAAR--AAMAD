"""
BAAR-AAMAD — DETERMINISTIC RULE ENGINE
======================================

Every derived classification in the system lives here, in plain Python.

An LLM may never decide any of the following:
  * the user-facing label for an assessment state
  * the priority band of a finding
  * the overall case status
  * whether a requirement is evidence-backed

These are rules, they are auditable, and they produce the same answer every
run. That reproducibility is what makes the golden demo trustworthy.
"""

from __future__ import annotations

from collections.abc import Sequence

from .schemas import (
    AssessmentState,
    CaseStatus,
    CoverageAssessment,
    Finding,
    FindingLabel,
    HumanDecision,
    Priority,
    Requirement,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# State -> user-facing label
# ---------------------------------------------------------------------------

#: Five internal states collapse onto four user-facing labels.
#:
#: NOT_ASSESSED IS INTERNAL ONLY. It has no label of its own and must never
#: reach the screen as a distinct status. We fold it into
#: VERIFICATION_REQUIRED: if we could not assess something, the honest
#: user-facing message is that a human must look at it.
#:
#: This dict is the ONLY place the fold happens. Nothing else in the codebase
#: may branch on NOT_ASSESSED for display purposes.
_LABEL_BY_STATE: dict[AssessmentState, FindingLabel] = {
    AssessmentState.SATISFIED: FindingLabel.COMPLETED,
    AssessmentState.MISSING: FindingLabel.ACTION_REQUIRED,
    AssessmentState.INCONSISTENT: FindingLabel.NEEDS_CORRECTION,
    AssessmentState.REQUIRES_VERIFICATION: FindingLabel.VERIFICATION_REQUIRED,
    AssessmentState.NOT_ASSESSED: FindingLabel.VERIFICATION_REQUIRED,
}

#: Glyphs used by the findings list and the Passport tally.
LABEL_GLYPH: dict[FindingLabel, str] = {
    FindingLabel.COMPLETED: "✓",
    FindingLabel.ACTION_REQUIRED: "✕",
    FindingLabel.NEEDS_CORRECTION: "⚠",
    FindingLabel.VERIFICATION_REQUIRED: "?",
}


def label_for_state(state: AssessmentState) -> FindingLabel:
    """Map an internal assessment state to its user-facing label."""
    return _LABEL_BY_STATE[state]


# ---------------------------------------------------------------------------
# State -> priority band
# ---------------------------------------------------------------------------

#: A blocking problem outranks a correctable one, which outranks a question.
_PRIORITY_BY_STATE: dict[AssessmentState, Priority] = {
    AssessmentState.MISSING: Priority.URGENT_HIGH,
    AssessmentState.INCONSISTENT: Priority.MEDIUM,
    AssessmentState.REQUIRES_VERIFICATION: Priority.VERIFICATION,
    AssessmentState.NOT_ASSESSED: Priority.VERIFICATION,
    AssessmentState.SATISFIED: Priority.SATISFIED,
}

#: Subtitles are fixed by the specification figure.
PRIORITY_SUBTITLE: dict[Priority, str] = {
    Priority.URGENT_HIGH: "Resolve first",
    Priority.MEDIUM: "Prepare / correct",
    Priority.VERIFICATION: "Human review required",
    Priority.SATISFIED: "No action required",
}

#: Display order of the priority bands.
PRIORITY_ORDER: list[Priority] = [
    Priority.URGENT_HIGH,
    Priority.MEDIUM,
    Priority.VERIFICATION,
    Priority.SATISFIED,
]


def priority_for_state(state: AssessmentState) -> Priority:
    """Map an internal assessment state to its priority band."""
    return _PRIORITY_BY_STATE[state]


def priority_rank(priority: Priority) -> int:
    """Sort key: lower sorts first."""
    return PRIORITY_ORDER.index(priority)


# ---------------------------------------------------------------------------
# Findings -> case status
# ---------------------------------------------------------------------------


#: States that block the case outright.
BLOCKING_STATES: frozenset[AssessmentState] = frozenset(
    {AssessmentState.MISSING, AssessmentState.INCONSISTENT}
)

#: States that leave an open question for a human.
#: NOT_ASSESSED sits here for the same reason it folds into the
#: "Verification required" label: we could not assess it, so a person must.
OPEN_QUESTION_STATES: frozenset[AssessmentState] = frozenset(
    {AssessmentState.REQUIRES_VERIFICATION, AssessmentState.NOT_ASSESSED}
)

#: A finding stops counting against the case once a human has acted on it at
#: the Human Review Gate. PENDING means nobody has looked at it yet.
RESOLVED_DECISIONS: frozenset[HumanDecision] = frozenset(
    {HumanDecision.ACCEPTED, HumanDecision.CORRECTED, HumanDecision.VERIFIED}
)


def is_unresolved(finding: Finding) -> bool:
    """True while a finding still counts against the case status.

    Note that the normal way a blocker clears is FIX -> RECHECK, which changes
    the finding's state to SATISFIED on the next run. The human-decision path
    exists for the Human Review Gate, where a person can verify or accept an
    item the system could not settle on its own.
    """
    return finding.human_decision not in RESOLVED_DECISIONS


def case_status_for(
    items: Sequence[Finding | AssessmentState],
    coverage: CoverageAssessment | None = None,
) -> CaseStatus:
    """Derive the Passport's CASE STATUS field.

    Categorical, never numeric, never decided by an LLM. Accepts either
    Finding objects (preferred — human decisions are honoured) or bare
    AssessmentState values (convenient for tests, all treated as unresolved).

    Order of precedence:
      any unresolved MISSING / INCONSISTENT     -> ACTION REQUIRED
      else any unresolved REQUIRES_VERIFICATION
           or NOT_ASSESSED                      -> VERIFICATION REQUIRED
      else                                      -> READY FOR HUMAN REVIEW

    READY FOR HUMAN REVIEW is deliberately the best attainable status. The
    system never declares a case "compliant" — that is the exporter's and the
    authorities' call, not ours.
    `coverage` is optional and only consulted when there are no findings, to
    tell two very different empty cases apart: one that has not been run, and
    one that ran and found no source that speaks to this route. The second has
    been assessed — the answer is simply that we cannot say — so it is
    VERIFICATION REQUIRED, not NOT STARTED.
    """
    if not items:
        if coverage is not None and not coverage.can_state_requirements:
            return CaseStatus.VERIFICATION_REQUIRED
        return CaseStatus.NOT_STARTED

    open_states = [
        item if isinstance(item, AssessmentState) else item.state
        for item in items
        if isinstance(item, AssessmentState) or is_unresolved(item)
    ]

    if any(s in BLOCKING_STATES for s in open_states):
        return CaseStatus.ACTION_REQUIRED

    if any(s in OPEN_QUESTION_STATES for s in open_states):
        return CaseStatus.VERIFICATION_REQUIRED

    return CaseStatus.READY_FOR_HUMAN_REVIEW


# ---------------------------------------------------------------------------
# The absolute rule: no evidence, no claim
# ---------------------------------------------------------------------------


def enforce_evidence_rule(requirement: Requirement) -> Requirement:
    """Force REQUIRES_VERIFICATION on any requirement lacking source evidence.

    This is the mechanical guarantee behind "no authoritative evidence = no
    confident regulatory claim". The Requirements module calls this on every
    requirement it produces, and the orchestrator calls it again defensively.
    A model cannot talk its way past it.
    """
    if not requirement.evidence:
        requirement.verification_status = VerificationStatus.REQUIRES_VERIFICATION
    return requirement


def has_source_backing(requirement: Requirement) -> bool:
    """True only if at least one evidence excerpt carries a real source URL."""
    return any(ev.source_url.strip() for ev in requirement.evidence)


# ---------------------------------------------------------------------------
# Passport helpers
# ---------------------------------------------------------------------------

#: The Passport figure shows at most three entries under each of these.
KEY_ISSUES_LIMIT = 3
NEXT_ACTIONS_LIMIT = 3


def tally_labels(labels: list[FindingLabel]) -> dict[FindingLabel, int]:
    """Count findings per user-facing label, always including zero counts."""
    return {label: labels.count(label) for label in FindingLabel}
