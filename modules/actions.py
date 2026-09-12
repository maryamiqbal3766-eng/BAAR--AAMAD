"""
BAAR-AAMAD — GENERATIVE ACTION ENGINE
=====================================

Turns "here are your problems" into "here is what you should do next".

Three outputs, as the specification sets out:

  A. Action Plan          problem -> why it matters -> action required ->
                          what to provide -> status
  B. Missing Information Checklist   where a document exists but is incomplete
  C. Preparation draft    where a document is missing entirely

ON DRAFTS — the hard line this module must hold: BAAR-AAMAD never produces an
official document and never implies it has. A draft is assembled ONLY from
facts already present in the case, carries DRAFT — FOR HUMAN VERIFICATION at
the top, names every field it could not fill rather than inventing it, and
says plainly that it must be issued by the competent authority. A Certificate
of Origin draft is a worksheet for the chamber of commerce, not a certificate.
"""

from __future__ import annotations

from core.rules import priority_rank
from core.schemas import (
    DRAFT_BANNER,
    AssessmentState,
    ActionItem,
    DocumentType,
    ExportCase,
    Finding,
    MissingInfoChecklist,
    PreparationDraft,
)
from modules.findings import TYPE_NAMES

#: Fields a draft may fill, and where each one legitimately comes from.
#: Nothing is sourced from anywhere but the case itself.
DRAFT_TEMPLATES: dict[DocumentType, list[tuple[str, str]]] = {
    DocumentType.CERTIFICATE_OF_ORIGIN: [
        ("Exporter", "profile.exporter.name"),
        ("Exporter address", "profile.exporter.address"),
        ("Consignee", "profile.shipment.buyer_name"),
        ("Consignee address", "profile.shipment.buyer_address"),
        ("Description of goods", "document.product_description"),
        ("Country of origin", "document.country_of_origin"),
        ("Quantity", "document.quantity"),
        ("Invoice number", "profile.shipment.invoice_number"),
        ("Invoice date", "profile.shipment.invoice_date"),
    ],
    DocumentType.PACKING_LIST: [
        ("Exporter", "profile.exporter.name"),
        ("Consignee", "profile.shipment.buyer_name"),
        ("Invoice number", "profile.shipment.invoice_number"),
        ("Description of goods", "document.product_description"),
        ("Quantity", "document.quantity"),
        ("Country of origin", "document.country_of_origin"),
    ],
    DocumentType.COMMERCIAL_INVOICE: [
        ("Exporter", "profile.exporter.name"),
        ("Exporter address", "profile.exporter.address"),
        ("Consignee", "profile.shipment.buyer_name"),
        ("Consignee address", "profile.shipment.buyer_address"),
        ("Invoice number", "profile.shipment.invoice_number"),
        ("Invoice date", "profile.shipment.invoice_date"),
        ("Description of goods", "document.product_description"),
        ("Quantity", "document.quantity"),
        ("Declared value", "profile.shipment.declared_value"),
    ],
}

#: What a draft cannot supply, because only the issuing body can.
AUTHORITY_FIELDS: dict[DocumentType, list[str]] = {
    DocumentType.CERTIFICATE_OF_ORIGIN: [
        "Certificate number (assigned by the issuing chamber)",
        "Issuing authority name, stamp and signature",
        "Date of issue",
    ],
    DocumentType.PACKING_LIST: [
        "Number of packages",
        "Gross weight",
        "Net weight",
    ],
    DocumentType.COMMERCIAL_INVOICE: [
        "Unit price and totals",
        "Incoterm and place",
        "Payment terms",
    ],
}


# ---------------------------------------------------------------------------
# A. Action plan
# ---------------------------------------------------------------------------


def _why_it_matters(case: ExportCase, finding: Finding) -> str:
    requirement = case.requirement(finding.requirement_id)
    return requirement.why_required if requirement else finding.what_was_checked


def build_action_plan(case: ExportCase) -> list[ActionItem]:
    """One row per finding that needs the exporter to do something.

    Satisfied findings are deliberately left out: an action plan is a list of
    work, not a list of everything.
    """
    actionable = [
        finding
        for finding in case.findings
        if finding.state is not AssessmentState.SATISFIED
    ]
    actionable.sort(key=lambda f: (priority_rank(f.priority), f.requirement_id))

    plan = []
    for index, finding in enumerate(actionable, start=1):
        requirement = case.requirement(finding.requirement_id)
        plan.append(
            ActionItem(
                action_id=f"A-{index:02d}",
                finding_id=finding.finding_id,
                priority=finding.priority,
                problem=(
                    requirement.title if requirement else finding.requirement_id
                ),
                why_it_matters=_why_it_matters(case, finding),
                action_required=finding.next_action,
                what_to_provide=list(finding.what_to_provide),
                status=finding.label,
            )
        )
    return plan


# ---------------------------------------------------------------------------
# B. Missing information checklist
# ---------------------------------------------------------------------------


def build_checklists(case: ExportCase) -> list[MissingInfoChecklist]:
    """Where a document IS present but does not carry everything needed.

    A wholly absent document is not a checklist entry — that is an action, and
    it appears in the plan instead.
    """
    missing_by_type: dict[DocumentType, list[str]] = {}

    for finding in case.findings:
        if finding.state is AssessmentState.SATISFIED:
            continue
        for check in finding.checks:
            if check.passed is not False:
                continue
            for key, value in check.compared.items():
                if value is not None or "." not in key:
                    continue
                type_name, _, field_name = key.partition(".")
                try:
                    document_type = DocumentType(type_name)
                except ValueError:
                    continue
                document = case.document(document_type)
                if document is None or not document.readable:
                    continue  # absent document -> action plan, not checklist
                label = field_name.replace("_", " ")
                missing_by_type.setdefault(document_type, [])
                if label not in missing_by_type[document_type]:
                    missing_by_type[document_type].append(label)

    return [
        MissingInfoChecklist(document_type=document_type, missing_fields=fields)
        for document_type, fields in sorted(
            missing_by_type.items(), key=lambda item: item[0].value
        )
        if fields
    ]


# ---------------------------------------------------------------------------
# C. Preparation drafts
# ---------------------------------------------------------------------------


def _case_value(case: ExportCase, path: str) -> str:
    """Resolve one draft field from the case. Returns '' when unknown.

    'document.x' means "whatever the exporter's own documents already say",
    taken from the first readable document that carries it.
    """
    profile = case.profile
    if profile is None:
        return ""

    if path.startswith("profile."):
        target = profile
        for part in path.split(".")[1:]:
            target = getattr(target, part, "")
            if target == "":
                return ""
        return str(target)

    if path.startswith("document."):
        field_name = path.split(".", 1)[1]
        for document in case.documents:
            if not document.readable:
                continue
            value = document.get(field_name)
            if value:
                return value
    return ""


def build_draft(case: ExportCase, document_type: DocumentType) -> PreparationDraft:
    """Assemble a preparation worksheet for a missing document.

    Every line is either a fact already in this case or an explicit blank.
    Nothing is inferred, and nothing is presented as issued.
    """
    template = DRAFT_TEMPLATES.get(document_type, [])
    lines: list[str] = []
    sources: list[str] = []

    for label, path in template:
        value = _case_value(case, path)
        if value:
            lines.append(f"{label}: {value}")
            origin = "your case details" if path.startswith("profile.") else "your uploaded documents"
            if origin not in sources:
                sources.append(origin)
        else:
            lines.append(f"{label}: ______________________  (not known to BAAR-AAMAD)")

    authority = AUTHORITY_FIELDS.get(document_type, [])
    if authority:
        lines.append("")
        lines.append("To be completed by the issuing body or by you:")
        lines.extend(f"  - {item}" for item in authority)

    return PreparationDraft(
        draft_id=f"D-{document_type.value}",
        document_type=document_type,
        prepared_from=sources or ["no case information was available"],
        body="\n".join(lines),
    )


def build_drafts(case: ExportCase) -> list[PreparationDraft]:
    """A worksheet for each supported document the case is missing."""
    drafts = []
    for finding in case.findings:
        if finding.state is not AssessmentState.MISSING:
            continue
        requirement = case.requirement(finding.requirement_id)
        if requirement is None:
            continue
        for document_type in requirement.expected_document_types:
            if document_type not in DRAFT_TEMPLATES:
                continue
            existing = case.document(document_type)
            if existing is not None and existing.readable:
                continue
            if any(d.document_type is document_type for d in drafts):
                continue
            drafts.append(build_draft(case, document_type))
    return drafts


def draft_is_safe(draft: PreparationDraft) -> bool:
    """A draft must carry its banner and must not claim to be official."""
    if draft.banner != DRAFT_BANNER:
        return False
    forbidden = ("hereby certify", "is hereby issued", "officially certified")
    body = draft.body.lower()
    return not any(phrase in body for phrase in forbidden)


def document_label(document_type: DocumentType) -> str:
    return TYPE_NAMES.get(document_type, document_type.value.replace("_", " ").title())
