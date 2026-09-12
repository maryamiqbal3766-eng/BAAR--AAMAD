"""
BAAR-AAMAD — DOCUMENT INTELLIGENCE
==================================

    UPLOAD -> IDENTIFY -> EXTRACT TEXT -> EXTRACT FIELDS -> DOCUMENT EVIDENCE

Turns an uploaded PDF into structured DocumentEvidence: what kind of document
it is, what text it holds, and the specific values BAAR-AAMAD will later check
against the requirements.

TWO LAYERS, in the order the specification requires:

  1. Deterministic Python does the reading. Labelled values ("Quantity: 500
     units") are found by pattern, so the same PDF always yields the same
     answer. This is what makes the golden demo reproducible.

  2. An LLM fills ONLY the gaps the patterns could not, for documents whose
     wording is messier than our fixtures. It can add a missing field; it can
     never overwrite one Python already read, and if it fails the
     deterministic result stands untouched.

WHAT THIS MODULE MUST NOT DO: decide whether a document satisfies anything.
It reports what the document says. Matching, comparison and findings belong
to the Validation module.

Only fields BAAR-AAMAD actually needs are extracted. We do not harvest
everything a document happens to contain.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dataclass_field

from core.errors import OCRUnavailableError
from core.schemas import (
    DocumentEvidence,
    DocumentType,
    ExtractedField,
    ExtractionMethod,
    ModuleResult,
)

log = logging.getLogger(__name__)

#: Below this many characters we assume there is no usable text layer — the
#: document is a scan or a photograph — and fall back to OCR.
MIN_USEFUL_CHARS = 40

#: Confidence below this means the content does not look like the type at all.
IDENTIFICATION_FLOOR = 0.2


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


@dataclass
class TextExtraction:
    """The result of trying to get words out of a PDF."""

    text: str = ""
    page_count: int = 0
    method: ExtractionMethod = ExtractionMethod.FAILED
    failure: str = ""

    @property
    def ok(self) -> bool:
        return self.method in (ExtractionMethod.NATIVE_TEXT, ExtractionMethod.OCR)


def extract_text(data: bytes) -> TextExtraction:
    """Read a PDF's text, falling back to OCR when there is no text layer.

    Never raises. A document we cannot read is a normal outcome that the
    exporter is told about, not an error that breaks the case.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        return TextExtraction(failure=f"PDF support is not installed ({exc}).")

    from io import BytesIO

    try:
        reader = PdfReader(BytesIO(data))
        pages = list(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in pages).strip()
        page_count = len(pages)
    except Exception as exc:
        log.warning("PDF could not be parsed: %s", exc)
        return TextExtraction(
            failure=(
                "This PDF could not be opened. It may be damaged or password "
                "protected. Please re-save it and upload it again."
            )
        )

    if len(text) >= MIN_USEFUL_CHARS:
        return TextExtraction(
            text=text, page_count=page_count, method=ExtractionMethod.NATIVE_TEXT
        )

    # No usable text layer — this looks like a scan.
    try:
        ocr_text = _ocr(data)
    except OCRUnavailableError as exc:
        return TextExtraction(page_count=page_count, failure=exc.user_message)
    except Exception as exc:
        log.warning("OCR failed: %s", exc)
        return TextExtraction(
            page_count=page_count,
            failure=(
                "We could not read any text from this document. Please upload "
                "a clearer copy — a digital PDF works best."
            ),
        )

    if len(ocr_text.strip()) < MIN_USEFUL_CHARS:
        return TextExtraction(
            page_count=page_count,
            failure=(
                "We could not read any text from this document. Please upload "
                "a clearer copy — a digital PDF works best."
            ),
        )

    return TextExtraction(
        text=ocr_text.strip(), page_count=page_count, method=ExtractionMethod.OCR
    )


def ocr_available() -> bool:
    """Whether an OCR toolchain is installed in this deployment."""
    try:
        import pytesseract  # noqa: F401
        from pdf2image import convert_from_bytes  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr(data: bytes) -> str:
    """Optional fallback for scanned documents.

    OCR needs system binaries (tesseract, poppler) that we deliberately do not
    require, because the MVP's documents are digital PDFs and those binaries
    add deployment risk. Where they are installed this path just works; where
    they are not, the exporter is asked for a digital PDF instead.
    """
    if not ocr_available():
        raise OCRUnavailableError("pytesseract / pdf2image not installed")

    import pytesseract
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(data, dpi=200)
    return "\n".join(pytesseract.image_to_string(image) for image in images)


# ---------------------------------------------------------------------------
# Document identification
# ---------------------------------------------------------------------------


@dataclass
class Signature:
    """How a document type announces itself."""

    strong: list[str] = dataclass_field(default_factory=list)
    weak: list[str] = dataclass_field(default_factory=list)


#: A title phrase is worth far more than a supporting term, because a Packing
#: List also mentions an invoice number and a Certificate of Origin also
#: mentions goods.
STRONG_WEIGHT = 0.6
WEAK_WEIGHT = 0.1

SIGNATURES: dict[DocumentType, Signature] = {
    DocumentType.COMMERCIAL_INVOICE: Signature(
        strong=["commercial invoice"],
        weak=["unit price", "total value", "incoterm", "invoice date", "hs code"],
    ),
    DocumentType.PACKING_LIST: Signature(
        strong=["packing list"],
        weak=["gross weight", "net weight", "number of packages", "carton"],
    ),
    DocumentType.CERTIFICATE_OF_ORIGIN: Signature(
        strong=["certificate of origin"],
        weak=["issuing authority", "certificate no", "chamber of commerce"],
    ),
}


def score_types(text: str) -> dict[DocumentType, float]:
    """Score the text against every supported type. Deterministic."""
    haystack = text.lower()
    scores: dict[DocumentType, float] = {}
    for document_type, signature in SIGNATURES.items():
        score = sum(STRONG_WEIGHT for term in signature.strong if term in haystack)
        score += sum(WEAK_WEIGHT for term in signature.weak if term in haystack)
        scores[document_type] = round(min(score, 1.0), 2)
    return scores


def identify_document_type(text: str) -> tuple[DocumentType, float]:
    """Decide what this document is from its own content.

    Returns UNSUPPORTED when nothing scores above the floor, rather than
    forcing the closest guess.
    """
    if not text.strip():
        return DocumentType.UNSUPPORTED, 0.0

    scores = score_types(text)
    best_type = max(scores, key=lambda key: scores[key])
    best_score = scores[best_type]

    if best_score < IDENTIFICATION_FLOOR:
        return DocumentType.UNSUPPORTED, 0.0
    return best_type, best_score


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

#: Labels are tried in order, so the most specific wording comes first.
#: A label only matches when a separator follows it immediately, which is why
#: "Exporter Address:" does not get picked up as "Exporter:".
FIELD_LABELS: dict[str, list[str]] = {
    "invoice_number": ["invoice no", "invoice number", "invoice #", "inv no"],
    "invoice_date": ["invoice date"],
    "issue_date": ["issue date", "date of issue"],
    "certificate_number": ["certificate no", "certificate number"],
    "issuing_authority": ["issuing authority", "issued by"],
    "packing_list_number": ["packing list no", "packing list number"],
    "exporter_name": ["exporter", "shipper", "seller"],
    "buyer_name": ["consignee", "buyer", "importer"],
    "product_description": ["description of goods", "goods description", "description"],
    "hs_code": ["hs code", "hs-code", "tariff code", "tariff heading"],
    "country_of_origin": ["country of origin", "origin"],
    "quantity": ["total quantity", "quantity", "qty"],
    "declared_value": ["total value", "total amount", "invoice value"],
    "incoterm": ["incoterm", "delivery terms", "terms of delivery"],
    "packages": ["number of packages", "total packages", "packages"],
    "gross_weight": ["gross weight"],
    "net_weight": ["net weight"],
}

#: Only the fields each document type is actually expected to carry — we do
#: not extract everything a document happens to contain.
FIELDS_BY_TYPE: dict[DocumentType, list[str]] = {
    DocumentType.COMMERCIAL_INVOICE: [
        "invoice_number",
        "invoice_date",
        "exporter_name",
        "buyer_name",
        "product_description",
        "hs_code",
        "country_of_origin",
        "quantity",
        "declared_value",
        "incoterm",
    ],
    DocumentType.PACKING_LIST: [
        "packing_list_number",
        "invoice_number",
        "exporter_name",
        "buyer_name",
        "product_description",
        "country_of_origin",
        "quantity",
        "packages",
        "gross_weight",
        "net_weight",
    ],
    DocumentType.CERTIFICATE_OF_ORIGIN: [
        "certificate_number",
        "issue_date",
        "issuing_authority",
        "exporter_name",
        "buyer_name",
        "product_description",
        "country_of_origin",
        "quantity",
        "invoice_number",
    ],
}

#: Fields reduced to a bare number, so the deterministic validation engine can
#: compare 500 against 450 without re-parsing "500 units".
NUMERIC_FIELDS = {"quantity", "packages", "gross_weight", "net_weight"}

_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _first_number(text: str) -> str | None:
    """The first number in a string, with thousands separators removed."""
    match = _NUMBER.search(text)
    return match.group(0).replace(",", "") if match else None


def _find_labelled_value(lines: list[str], labels: list[str]) -> tuple[str, str] | None:
    """First (value, whole line) whose line starts with one of the labels."""
    for label in labels:
        pattern = re.compile(rf"^\s*{re.escape(label)}\s*[:\-–—]\s*(.+)$", re.I)
        for line in lines:
            match = pattern.match(line)
            if match and match.group(1).strip():
                return match.group(1).strip(), line.strip()
    return None


def extract_fields(
    document_type: DocumentType, text: str
) -> dict[str, ExtractedField]:
    """Pull the values BAAR-AAMAD needs out of the document text.

    Deterministic: no model, no inference. A field that is not clearly
    labelled is simply absent, which is an honest answer.
    """
    wanted = FIELDS_BY_TYPE.get(document_type, [])
    lines = [line for line in text.splitlines() if line.strip()]
    found: dict[str, ExtractedField] = {}

    for name in wanted:
        hit = _find_labelled_value(lines, FIELD_LABELS[name])
        if hit is None:
            continue
        raw_value, source_line = hit

        value = raw_value
        if name in NUMERIC_FIELDS:
            number = _first_number(raw_value)
            if number is None:
                continue  # a quantity with no number in it is not a quantity
            value = number

        found[name] = ExtractedField(
            name=name,
            value=value,
            raw_snippet=source_line,
            confidence=1.0,  # read verbatim from a labelled line
        )

    return found


# ---------------------------------------------------------------------------
# Optional AI gap-fill
# ---------------------------------------------------------------------------


def ai_fill_gaps(
    document_type: DocumentType,
    text: str,
    found: dict[str, ExtractedField],
) -> dict[str, ExtractedField]:
    """Ask the model only for fields the patterns could not find.

    Strictly additive. A value Python read is never replaced, and any failure
    leaves the deterministic result exactly as it was — the specification's
    rule that a failed semantic pass falls back to structured checks.
    """
    from core import llm

    missing = [name for name in FIELDS_BY_TYPE.get(document_type, []) if name not in found]
    if not missing or not text.strip() or not llm.is_configured():
        return found

    from pydantic import BaseModel, Field as PydanticField

    class Gaps(BaseModel):
        values: dict[str, str | None] = PydanticField(default_factory=dict)

    system = (
        "You read trade documents and report values that are present in them. "
        "Return only values that genuinely appear in the document text. If a "
        "value is not present, return null for it. Never infer, calculate or "
        "invent a value."
    )
    user = (
        f"Document type: {document_type.value}\n"
        f"Report these fields if present: {', '.join(missing)}\n\n"
        f"Document text:\n{text[:6000]}"
    )

    try:
        result = llm.complete_json(system=system, user=user, schema=Gaps, tier=llm.Tier.FAST)
    except Exception as exc:
        log.warning("AI gap-fill unavailable, keeping deterministic fields: %s", exc)
        return found

    for name, value in result.values.items():
        if name not in missing or value is None or not str(value).strip():
            continue
        cleaned = str(value).strip()
        if name in NUMERIC_FIELDS:
            number = _first_number(cleaned)
            if number is None:
                continue
            cleaned = number
        found[name] = ExtractedField(
            name=name,
            value=cleaned,
            raw_snippet="",  # the model reported it; there is no matched line
            confidence=0.5,  # lower than a verbatim match, deliberately
        )

    return found


# ---------------------------------------------------------------------------
# The module entry point
# ---------------------------------------------------------------------------


def read_document(
    evidence: DocumentEvidence, data: bytes, use_ai: bool = True
) -> ModuleResult:
    """Read one uploaded PDF and fill in its DocumentEvidence.

    `evidence` is updated in place. The document's assigned type is NOT
    changed: the exporter chose it, and if the content disagrees we report the
    disagreement rather than silently reassigning the document.

    The payload carries:
        text                 the extracted text
        identified_type      what the content looks like
        identified_score     confidence in that
        matches_selection    whether content and selection agree
    """
    extraction = extract_text(data)
    evidence.page_count = extraction.page_count
    evidence.extraction_method = extraction.method

    if not extraction.ok:
        evidence.readable = False
        evidence.unreadable_reason = extraction.failure
        evidence.raw_text_length = 0
        evidence.fields = {}
        evidence.identification_confidence = None
        return ModuleResult(ok=False, reason=extraction.failure, payload={"text": ""})

    evidence.readable = True
    evidence.unreadable_reason = ""
    evidence.raw_text_length = len(extraction.text)

    identified_type, identified_score = identify_document_type(extraction.text)
    scores = score_types(extraction.text)
    evidence.identification_confidence = scores.get(evidence.document_type, 0.0)

    fields = extract_fields(evidence.document_type, extraction.text)
    if use_ai:
        fields = ai_fill_gaps(evidence.document_type, extraction.text, fields)
    evidence.fields = fields

    return ModuleResult(
        ok=True,
        payload={
            "text": extraction.text,
            "identified_type": identified_type,
            "identified_score": identified_score,
            "matches_selection": identified_type is evidence.document_type,
        },
    )
