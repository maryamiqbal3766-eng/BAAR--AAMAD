"""
BAAR-AAMAD — SHARED DATA CONTRACT
=================================

This module is the SINGLE SOURCE OF TRUTH for every structure that moves
between modules. It is FROZEN: do not edit it on a feature branch.

    If you need a field added or changed, ask the Lead Architect.
    Changing this file unilaterally breaks every other module.

Rules that this contract encodes (from the BAAR-AAMAD specification):

  * No authoritative evidence  ->  no confident regulatory claim.
    Every Requirement carries `evidence` + `verification_status`. A
    Requirement with no RegulatoryEvidence MUST be REQUIRES_VERIFICATION.

  * There are FIVE internal assessment states and FOUR user-facing labels.
    Never show a raw internal state to the user. Use core.rules.label_for_state.

  * Priority is rule-based, never invented by an LLM.
    See core.rules.priority_for_state.

  * No numeric compliance score exists anywhere in this contract. By design.

  * Any generated document draft carries DRAFT_BANNER verbatim.

Pipeline these objects flow through:

    ExportCase -> CaseProfile -> Requirement[] (+RegulatoryEvidence)
               -> DocumentEvidence[] -> CheckResult[] -> Finding[]
               -> ReasoningTrace[] -> ActionItem[] -> Passport
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Mandatory banner on every generated preparation draft. Never alter this
#: string and never generate a document without it.
DRAFT_BANNER = "DRAFT — FOR HUMAN VERIFICATION"

#: SCOPE IS NOT DECLARED HERE.
#:
#: This contract is product-, origin- and destination-agnostic by design.
#: There is deliberately no list of supported products or markets in it.
#:
#: What BAAR-AAMAD can advise on is whatever the curated corpus in data/corpus
#: declares it covers, computed at load time — never a parallel allow-list
#: carried in code, which is how "leather bags to Germany" leaked out of the
#: golden demo and into the application itself.
#:
#: See modules.retrieval.assess_coverage for how a case is graded against the
#: corpus, and Coverage / CoverageAssessment below for how that is recorded.


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    """Common config. `extra="forbid"` catches contract drift immediately."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DocumentType(str, Enum):
    """The 2-3 document types supported by the MVP, plus the reject case."""

    COMMERCIAL_INVOICE = "COMMERCIAL_INVOICE"
    PACKING_LIST = "PACKING_LIST"
    CERTIFICATE_OF_ORIGIN = "CERTIFICATE_OF_ORIGIN"
    UNSUPPORTED = "UNSUPPORTED"


class ExtractionMethod(str, Enum):
    #: Uploaded but not yet read. The honest default — a stored document must
    #: never imply that text extraction has happened.
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    NATIVE_TEXT = "NATIVE_TEXT"  # digital PDF text layer (primary path)
    OCR = "OCR"  # fallback only
    FAILED = "FAILED"


class AssessmentState(str, Enum):
    """INTERNAL state. Five values. Never rendered directly to the user."""

    SATISFIED = "SATISFIED"
    MISSING = "MISSING"
    INCONSISTENT = "INCONSISTENT"
    REQUIRES_VERIFICATION = "REQUIRES_VERIFICATION"
    NOT_ASSESSED = "NOT_ASSESSED"


class FindingLabel(str, Enum):
    """USER-FACING label. Four values. Derived via core.rules, never set by hand."""

    COMPLETED = "Completed"
    ACTION_REQUIRED = "Action required"
    NEEDS_CORRECTION = "Needs correction"
    VERIFICATION_REQUIRED = "Verification required"


class Priority(str, Enum):
    """Rule-derived priority band. Subtitles live in core.rules.PRIORITY_SUBTITLE."""

    URGENT_HIGH = "URGENT / HIGH"
    MEDIUM = "MEDIUM"
    VERIFICATION = "VERIFICATION"
    SATISFIED = "SATISFIED"


class CaseStatus(str, Enum):
    """Categorical readiness. There is deliberately NO numeric score."""

    NOT_STARTED = "NOT STARTED"
    ACTION_REQUIRED = "ACTION REQUIRED"
    VERIFICATION_REQUIRED = "VERIFICATION REQUIRED"
    READY_FOR_HUMAN_REVIEW = "READY FOR HUMAN REVIEW"


class VerificationStatus(str, Enum):
    """Whether a requirement is backed by retrieved authoritative evidence."""

    SUPPORTED_BY_SOURCE = "SUPPORTED_BY_SOURCE"
    REQUIRES_VERIFICATION = "REQUIRES_VERIFICATION"


class Coverage(str, Enum):
    """How much of a case the curated corpus can actually speak to.

    This is the honest answer to "can BAAR-AAMAD advise on this shipment?",
    and it is graded rather than yes/no. A case for goods we hold no
    product-specific source for is NOT a failure: general customs sources may
    still apply, and saying exactly which parts went unassessed is far more
    useful — and far more truthful — than refusing the case outright.
    """

    #: Sources apply to this route AND to this kind of product.
    COVERED = "COVERED"
    #: Sources apply to the route, but none are specific to this product.
    PARTIALLY_COVERED = "PARTIALLY COVERED"
    #: No curated source applies. No requirements may be stated at all.
    NOT_COVERED = "NOT COVERED"


class CheckMethod(str, Enum):
    """Which of the two validation engines produced a result."""

    DETERMINISTIC = "DETERMINISTIC"  # Python: exact values, presence, dates
    SEMANTIC = "SEMANTIC"  # LLM: meaning, wording variation


class StageName(str, Enum):
    """Orchestrator stages, in execution order."""

    PROFILE = "PROFILE"
    REQUIREMENTS = "REQUIREMENTS"
    DOCUMENTS = "DOCUMENTS"
    VALIDATION = "VALIDATION"
    FINDINGS = "FINDINGS"
    REASONING = "REASONING"
    ACTIONS = "ACTIONS"
    PASSPORT = "PASSPORT"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    SKIPPED = "SKIPPED"  # module not implemented yet, or nothing to do
    FAILED = "FAILED"  # recoverable: case state is preserved


class HumanDecision(str, Enum):
    """Human Review Gate outcome, per finding."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    CORRECTED = "CORRECTED"
    VERIFIED = "VERIFIED"


# ---------------------------------------------------------------------------
# Case profile  (owner: Lead / AI Product Understanding)
# ---------------------------------------------------------------------------


class CoverageAssessment(_Base):
    """What the corpus could and could not speak to for one case.

    Recorded on the case so that every downstream surface — the dashboard, the
    action plan, the Compliance Passport — can state the limits of what was
    actually checked. A Passport that does not disclose partial coverage
    overstates the work that was done.
    """

    level: Coverage = Coverage.NOT_COVERED
    route: str = Field(default="", description="Product, origin and destination.")

    matched_source_ids: list[str] = Field(default_factory=list)
    #: Sources written for this kind of product, e.g. a chemical restriction
    #: on the material. Their presence is what makes a case fully COVERED.
    product_specific_source_ids: list[str] = Field(default_factory=list)
    #: Sources that apply to any goods on this route, e.g. customs formalities.
    general_source_ids: list[str] = Field(default_factory=list)

    #: Plain-language statements of what was NOT assessed, shown to the user.
    unassessed: list[str] = Field(default_factory=list)
    message: str = ""

    @property
    def can_state_requirements(self) -> bool:
        return self.level is not Coverage.NOT_COVERED


class ExporterInfo(_Base):
    name: str = ""
    address: str = ""
    contact: str = ""
    ntn_or_reg_no: str = ""


class ShipmentInfo(_Base):
    buyer_name: str = ""
    buyer_address: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    declared_quantity: str = ""
    declared_value: str = ""
    incoterm: str = ""


class CaseProfile(_Base):
    """Normalized understanding of what is being exported, from where, to where."""

    product_raw: str = Field(description="Exactly what the user typed.")
    product_normalized: str = Field(default="", description="AI-normalized product name.")
    product_characteristics: list[str] = Field(default_factory=list)

    #: Where the goods originate. Origin decides duty treatment and which
    #: preferential schemes are even available, so it is a first-class part of
    #: the case rather than something inferred from the exporter's address.
    origin_country: str = ""

    #: No default. A contract that ships with a destination pre-filled biases
    #: every case created from it.
    destination: str = ""

    classification_context: str = Field(
        default="",
        description="e.g. an indicative tariff heading. NEVER a final legal classification.",
    )
    classification_verification_status: VerificationStatus = (
        VerificationStatus.REQUIRES_VERIFICATION
    )

    exporter: ExporterInfo = Field(default_factory=ExporterInfo)
    shipment: ShipmentInfo = Field(default_factory=ShipmentInfo)

    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Regulatory evidence + requirements  (owner: RAG / Requirements module)
# ---------------------------------------------------------------------------


class RegulatoryEvidence(_Base):
    """A retrieved excerpt from the CURATED corpus. Never LLM-authored.

    `source_name` and `source_url` come from corpus metadata, not from the
    model. This is what makes citations structural rather than hallucinated.
    """

    evidence_id: str
    source_name: str
    source_url: str
    excerpt: str = Field(description="Verbatim text from the corpus. Do not paraphrase.")
    locator: str = Field(default="", description="Section / article / page reference.")
    relevance: float = Field(default=0.0, description="Retriever score. Not a confidence.")


class Requirement(_Base):
    """One export requirement, interpreted from retrieved evidence.

    INVARIANT: if `evidence` is empty, `verification_status` MUST be
    REQUIRES_VERIFICATION. Enforced by core.rules.enforce_evidence_rule.
    """

    requirement_id: str
    title: str

    what_is_required: str
    why_required: str
    when_it_applies: str

    satisfying_evidence: list[str] = Field(
        default_factory=list,
        description="What would satisfy this, in plain language.",
    )
    needed_document_or_info: list[str] = Field(default_factory=list)
    expected_document_types: list[DocumentType] = Field(default_factory=list)

    evidence: list[RegulatoryEvidence] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.REQUIRES_VERIFICATION


# ---------------------------------------------------------------------------
# Document evidence  (owner: Document Intelligence module)
# ---------------------------------------------------------------------------


class ExtractedField(_Base):
    """One structured value pulled out of a document, with its provenance."""

    name: str = Field(description="Canonical field name, e.g. 'quantity'.")
    value: str | None = None
    raw_snippet: str = Field(default="", description="Source text the value came from.")
    confidence: float | None = Field(
        default=None, description="Extractor confidence 0-1. None if unknown."
    )


class DocumentEvidence(_Base):
    """What one uploaded document actually contains."""

    document_id: str
    filename: str
    document_type: DocumentType = DocumentType.UNSUPPORTED
    identification_confidence: float | None = None

    extraction_method: ExtractionMethod = ExtractionMethod.NOT_ATTEMPTED
    readable: bool = True
    unreadable_reason: str = ""

    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    size_bytes: int = 0
    raw_text_length: int = 0
    page_count: int = 0

    @property
    def extracted(self) -> bool:
        """True once a text/data extraction pass has actually run."""
        return self.extraction_method is not ExtractionMethod.NOT_ATTEMPTED

    uploaded_at: datetime = Field(default_factory=utcnow)

    def get(self, field_name: str) -> str | None:
        """Convenience accessor used heavily by the deterministic engine."""
        f = self.fields.get(field_name)
        return f.value if f else None


# ---------------------------------------------------------------------------
# Validation + findings  (owner: Validation module)
# ---------------------------------------------------------------------------


class CheckResult(_Base):
    """One atomic check. Records WHICH engine decided, for auditability."""

    check_id: str
    requirement_id: str
    method: CheckMethod
    description: str = Field(description="What was checked, in plain language.")
    passed: bool | None = Field(
        default=None, description="None means 'could not determine'."
    )
    detail: str = ""
    compared: dict[str, str | None] = Field(
        default_factory=dict,
        description="e.g. {'COMMERCIAL_INVOICE.quantity': '500', "
        "'PACKING_LIST.quantity': '450'}",
    )


class Finding(_Base):
    """The Findings Engine output: the single source of truth downstream.

    `label` and `priority` are DERIVED from `state` by core.rules. Do not set
    them by hand and do not let a model choose them.
    """

    finding_id: str
    requirement_id: str

    state: AssessmentState
    label: FindingLabel
    priority: Priority

    # The seven questions every requirement card must answer.
    what_was_checked: str = ""
    what_we_found: str = ""
    what_is_missing: str = ""
    what_to_provide: list[str] = Field(default_factory=list)
    next_action: str = ""

    checks: list[CheckResult] = Field(default_factory=list)
    regulatory_evidence_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)

    human_decision: HumanDecision = HumanDecision.PENDING


# ---------------------------------------------------------------------------
# Reasoning  (owner: Reasoning / Action module)
# ---------------------------------------------------------------------------


class ReasoningTrace(_Base):
    """Backs the 'Why did BAAR-AAMAD flag this?' button.

    The six links are fixed by specification. Render them in this order.
    Only `comparison` and `conclusion` may be LLM-authored prose; the rest
    are quoted from the requirement, the evidence and the document.
    """

    finding_id: str
    requirement: str
    source_evidence: str
    your_document_evidence: str
    comparison: str
    conclusion: str
    what_you_need_to_do: str


# ---------------------------------------------------------------------------
# Action engine  (owner: Reasoning / Action module)
# ---------------------------------------------------------------------------


class ActionItem(_Base):
    """One row of the Action Plan."""

    action_id: str
    finding_id: str
    priority: Priority
    problem: str
    why_it_matters: str
    action_required: str
    what_to_provide: list[str] = Field(default_factory=list)
    status: FindingLabel


class MissingInfoChecklist(_Base):
    """Document exists but required information is absent."""

    document_type: DocumentType
    missing_fields: list[str] = Field(default_factory=list)


class PreparationDraft(_Base):
    """Assistance for a MISSING document.

    This is NEVER an official certificate and must never be presented as one.
    `banner` is validated to equal DRAFT_BANNER before render.
    """

    draft_id: str
    document_type: DocumentType
    banner: str = DRAFT_BANNER
    prepared_from: list[str] = Field(
        default_factory=list,
        description="Which case facts this draft was assembled from.",
    )
    body: str = ""
    disclaimer: str = (
        "BAAR-AAMAD does not issue official documents. This draft is prepared "
        "from information already present in your export case and must be "
        "verified and issued by the competent authority or the exporter."
    )


# ---------------------------------------------------------------------------
# Compliance Passport  (owner: Reasoning / Action module)
# ---------------------------------------------------------------------------


class EvidenceMapRow(_Base):
    """REQUIREMENT -> SOURCE -> DOCUMENT EVIDENCE -> FINDING."""

    requirement: str
    source: str
    source_url: str = ""
    document_evidence: str
    finding: str


class Passport(_Base):
    """Flagship output. Section order is fixed by specification."""

    case_id: str
    product: str
    destination: str
    case_status: CaseStatus

    requirement_tally: dict[FindingLabel, int] = Field(default_factory=dict)
    key_issues: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    evidence_map: list[EvidenceMapRow] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=utcnow)
    run_number: int = 1


# ---------------------------------------------------------------------------
# Orchestration + the case itself  (owner: Lead)
# ---------------------------------------------------------------------------


class StageRecord(_Base):
    name: StageName
    status: StageStatus = StageStatus.PENDING
    message: str = ""
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def duration_s(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class ExportCase(_Base):
    """The whole case. Every module reads from and writes into this object."""

    case_id: str
    created_at: datetime = Field(default_factory=utcnow)
    run_number: int = Field(default=0, description="Increments on every RECHECK.")

    profile: CaseProfile | None = None
    #: What the corpus could speak to for this case. None until assessed.
    coverage: CoverageAssessment | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    documents: list[DocumentEvidence] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    reasoning: list[ReasoningTrace] = Field(default_factory=list)

    action_plan: list[ActionItem] = Field(default_factory=list)
    checklists: list[MissingInfoChecklist] = Field(default_factory=list)
    drafts: list[PreparationDraft] = Field(default_factory=list)
    passport: Passport | None = None

    stages: dict[StageName, StageRecord] = Field(default_factory=dict)

    #: True only when the case was loaded from a saved prior run. The UI MUST
    #: display this. Never present a replayed case as live AI processing.
    is_replay: bool = False
    replay_note: str = ""

    # -- lookups -----------------------------------------------------------

    def requirement(self, requirement_id: str) -> Requirement | None:
        return next(
            (r for r in self.requirements if r.requirement_id == requirement_id), None
        )

    def finding(self, finding_id: str) -> Finding | None:
        return next((f for f in self.findings if f.finding_id == finding_id), None)

    def document(self, document_type: DocumentType) -> DocumentEvidence | None:
        return next((d for d in self.documents if d.document_type == document_type), None)

    def trace(self, finding_id: str) -> ReasoningTrace | None:
        return next((t for t in self.reasoning if t.finding_id == finding_id), None)

    def evidence(self, evidence_id: str) -> RegulatoryEvidence | None:
        for req in self.requirements:
            for ev in req.evidence:
                if ev.evidence_id == evidence_id:
                    return ev
        return None

    def stage(self, name: StageName) -> StageRecord:
        return self.stages.setdefault(name, StageRecord(name=name))


# ---------------------------------------------------------------------------
# Module I/O envelopes
# ---------------------------------------------------------------------------


class ModuleResult(_Base):
    """Uniform return envelope for every team module.

    A module NEVER raises into the orchestrator for an expected failure. It
    returns ok=False with a reason, and the orchestrator preserves case state.
    """

    ok: bool = True
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
