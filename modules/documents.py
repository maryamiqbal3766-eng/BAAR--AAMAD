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

#: Labels are tried IN ORDER, most specific first, and the first one that
#: yields a usable value wins. That ordering is what stops a bare "date"
#: stealing the value from "Invoice Date", or "origin" from "Country of
#: Origin" — put the precise wording above the loose one, always.
#:
#: These are SYNONYMS FOR THE SAME FIELD, not new fields. Real export paperwork
#: is written by hundreds of different forwarders and every one of them names
#: the same box differently; recognising "Sold To" as the buyer is reading the
#: document, not guessing at it.
FIELD_LABELS: dict[str, list[str]] = {
    "invoice_number": [
        "invoice no", "invoice number", "invoice #", "invoice ref",
        "inv no", "inv #", "commercial invoice no", "commercial invoice number",
        "invoice reference",
    ],
    "invoice_date": [
        "invoice date", "date of invoice", "dated", "inv date", "date",
    ],
    "issue_date": ["issue date", "date of issue", "issued on"],
    "certificate_number": [
        "certificate no", "certificate number", "certificate #", "cert no",
        "reference no",
    ],
    "issuing_authority": [
        "issuing authority", "issued by", "certifying authority",
        "chamber of commerce", "authority",
    ],
    "packing_list_number": [
        "packing list no", "packing list number", "packing list #", "p/l no",
        "pl no",
    ],
    "po_number": [
        "po number", "po no", "p.o. no", "p/o no", "purchase order no",
        "purchase order number", "purchase order", "order no", "order number",
        "customer order no", "po #",
    ],
    # "from" and "to" are deliberately absent. They are prose, not labels:
    # "Collected From: Sialkot" is not an exporter, and a document full of
    # ordinary sentences would otherwise report one. A wrong value is worse
    # than a missing one, so the loose wordings stay out.
    "exporter_name": [
        "exporter name", "exporter", "shipper name", "shipper", "seller",
        "consignor", "supplier", "beneficiary",
    ],
    "buyer_name": [
        "consignee name", "consignee", "buyer name", "buyer", "importer",
        "sold to", "bill to", "ship to", "messrs", "customer",
    ],
    "product_description": [
        "description of goods", "goods description", "description of items",
        "commodity description", "particulars of goods", "nature of goods",
        "goods", "commodity", "description",
    ],
    "hs_code": [
        "hs code", "hs-code", "h.s. code", "hs no", "hts code", "tariff code",
        "tariff heading", "commodity code", "customs tariff",
    ],
    "country_of_origin": [
        "country of origin", "origin country", "made in", "origin",
    ],
    "country_of_destination": [
        "country of destination", "destination country", "port of discharge",
        "final destination", "destination",
    ],
    "quantity": [
        "total quantity", "total qty", "quantity", "qty", "no of units",
        "number of units", "units", "pieces", "pcs",
    ],
    "declared_value": [
        "total value", "total amount", "invoice value", "total invoice value",
        "grand total", "amount", "total",
    ],
    "incoterm": [
        "incoterm", "incoterms", "delivery terms", "terms of delivery",
        "trade terms", "shipment terms", "price terms",
    ],
    "packages": [
        "number of packages", "total packages", "no of packages",
        "total cartons", "no of cartons", "packages", "cartons", "pkgs",
    ],
    "gross_weight": [
        "total gross weight", "gross weight", "gross wt", "g.w.", "gw",
    ],
    "net_weight": ["total net weight", "net weight", "net wt", "n.w.", "nw"],
}

#: Labels that mark the START of another value on the same line, so a value is
#: cut short rather than swallowing the next column. Column headers that are
#: not fields of ours are here too: a value must never run into "Unit Price".
_BOUNDARY_EXTRA = [
    "unit price", "rate", "amount", "currency", "marks and numbers", "marks",
    "vessel", "flight", "port of loading", "port of discharge", "date",
    "signature", "page", "address", "tel", "phone", "email", "ntn", "vat",
    "gst", "eori", "rex", "total",
]

#: Only the fields each document type is actually expected to carry — we do
#: not extract everything a document happens to contain.
FIELDS_BY_TYPE: dict[DocumentType, list[str]] = {
    DocumentType.COMMERCIAL_INVOICE: [
        "invoice_number",
        "invoice_date",
        "po_number",
        "exporter_name",
        "buyer_name",
        "product_description",
        "hs_code",
        "country_of_origin",
        "country_of_destination",
        "quantity",
        "declared_value",
        "incoterm",
    ],
    DocumentType.PACKING_LIST: [
        "packing_list_number",
        "invoice_number",
        "po_number",
        "exporter_name",
        "buyer_name",
        "product_description",
        "country_of_origin",
        "country_of_destination",
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
        "hs_code",
        "country_of_origin",
        "country_of_destination",
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


#: Every label the extractor knows, longest first, used to find where one
#: value ends and the next label begins on a shared line.
_ALL_LABELS: list[str] = sorted(
    {label for labels in FIELD_LABELS.values() for label in labels} | set(_BOUNDARY_EXTRA),
    key=len,
    reverse=True,
)

#: A label, then its separator. FOUR separator styles, because real documents
#: use all four and the original extractor only understood the first:
#:
#:   "Invoice No: INV-1"      punctuation
#:   "Invoice No    INV-1"    column alignment (two or more spaces, or a tab)
#:   "No of Cartons 18"       a single space
#:   "INVOICE NO"             nothing — the value is in the box underneath
#:
#: The single space is allowed ONLY when the next token contains a digit. That
#: is what keeps "Exporter Address: ..." from being read as the exporter —
#: "Address:" has no digit in it — while still reading "Purchase Order
#: HLW-PO-88214". Losing that guard reintroduces the bug the strict original
#: was written to avoid.
_SEPARATOR = r"(?:\s*[:\-–—=]\s*|[ \t]{2,}|[ \t](?=\S*\d))"

#: Optional box number in front of a label: "1. Consignor", "(3) Origin".
_BOX_NUMBER = r"(?:\(?\d{1,2}[.)]\s*)?"

_BOUNDARY = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(re.escape(label) for label in _ALL_LABELS) + r")"
    + _SEPARATOR,
    re.I,
)


def _looks_like_a_label(line: str) -> bool:
    """Is this line a label/heading rather than a value?

    Used when a label sits alone above its value: we step down the document
    until we reach something that is not itself another box title.
    """
    stripped = re.sub(rf"^{_BOX_NUMBER}", "", line.strip()).rstrip(":").strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if lowered in _ALL_LABELS:
        return True
    # A short ALL-CAPS line with no digits is a box heading, not a value.
    return bool(
        len(stripped) <= 30
        and stripped.isupper()
        and not any(ch.isdigit() for ch in stripped)
    )


def _trim_at_next_label(value: str) -> str:
    """Cut a value where the next label starts on the same line.

    Two-column forms put "Invoice No: INV-1    Date: 2026-09-02" on one line.
    Without this the invoice number reads as "INV-1    Date: 2026-09-02" —
    which is not a value anybody can compare against anything.

    When the value begins with another label there is no value here at all:
    "EXPORTER          Invoice No   SLC/INV/1" is the exporter's BOX TITLE
    sharing a line with a different field. Returning "" sends the caller to
    look underneath, which is where the exporter's name actually is. Returning
    the text would report the invoice number as the exporter — a wrong value,
    which is worse than a missing one.
    """
    match = _BOUNDARY.search(value)
    if match:
        return value[: match.start()].strip(" \t:-–—,;")
    return value.strip()


def _is_table_header(line: str) -> bool:
    """Does this line name columns rather than state any value?

    Two labels alone are not enough: a boxed form puts "EXPORTER" and
    "Invoice No   SLC/INV/1" on one line, and that line DOES carry a value.
    A genuine header row is labels and nothing else — so take the labels out
    and see whether anything is left.
    """
    matches = list(_BOUNDARY_HEADER.finditer(line))
    if len(matches) < 2:
        return False
    remainder = _BOUNDARY_HEADER.sub("", line)
    return len(re.sub(r"[\s:|\-–—]", "", remainder)) <= 3


@dataclass
class _Candidate:
    value: str
    snippet: str
    score: float


def _candidates(lines: list[str], labels: list[str]) -> list[_Candidate]:
    """Every place in the document this field might be stated, best first.

    Collecting candidates rather than returning the first match matters: a
    table's header row ("Qty   Unit Price") matches the label but yields no
    number, and the original code gave up at that point instead of looking at
    the rows underneath.
    """
    found: list[_Candidate] = []

    for rank, label in enumerate(labels):
        # Later synonyms are looser wordings, so they score lower.
        base = 1.0 - (rank * 0.01)
        pattern = re.compile(
            rf"(?<![A-Za-z]){re.escape(label)}{_SEPARATOR}(?P<value>.*)$", re.I
        )

        for index, line in enumerate(lines):
            match = pattern.search(line)
            if match is None:
                continue

            # A label at the start of its line is likelier to be that line's
            # subject than one mentioned halfway through a sentence.
            at_line_start = match.start() <= 1
            value = _trim_at_next_label(match.group("value"))

            if value:
                found.append(
                    _Candidate(value, line.strip(), base + (0.2 if at_line_start else 0))
                )
                continue

            # No value on this line. Look in the box underneath — unless this
            # is a table's header row, in which case the line below is a data
            # row belonging to several columns at once and reading it whole
            # would report every column as this field's value.
            if _is_table_header(line):
                continue
            for following in lines[index + 1 : index + 4]:
                if _looks_like_a_label(following) or _is_table_header(following):
                    continue
                below = _trim_at_next_label(following)
                if below:
                    found.append(
                        _Candidate(
                            below, f"{line.strip()} / {following.strip()}", base - 0.1
                        )
                    )
                break

        # A bare label with no separator at all, sitting above its value —
        # including the numbered boxes a certificate of origin uses
        # ("1. Consignor", "3. Country of Origin").
        exact = re.compile(rf"^\s*{_BOX_NUMBER}{re.escape(label)}\s*:?\s*$", re.I)
        for index, line in enumerate(lines):
            if not exact.match(line):
                continue
            for following in lines[index + 1 : index + 4]:
                if _looks_like_a_label(following) or _is_table_header(following):
                    continue
                below = _trim_at_next_label(following)
                if below:
                    found.append(
                        _Candidate(
                            below, f"{line.strip()} / {following.strip()}", base - 0.1
                        )
                    )
                break

    found.sort(key=lambda c: -c.score)
    return found


def _table_candidates(lines: list[str], labels: list[str]) -> list[_Candidate]:
    """Read a value out of a column, when the label is a column heading.

    Handles the layout the label matcher cannot: a header row naming the
    columns, and the figures underneath it. Column position is taken from
    where the heading actually sits, so the columns may be in any order.

    Deliberately conservative — it only reports a value when exactly one data
    row is present. A multi-item invoice has several, and picking one of them,
    or adding them up, would be BAAR-AAMAD deciding what the total is. Where
    such a document states a total it is labelled, and the label matcher above
    has already found it.
    """
    found: list[_Candidate] = []

    for index, line in enumerate(lines):
        # A header row names at least two columns.
        headers = [m for m in _BOUNDARY_HEADER.finditer(line)]
        if len(headers) < 2:
            continue
        target = next(
            (m for m in headers if m.group(0).strip().lower() in labels), None
        )
        if target is None:
            continue

        column = target.start()
        rows = []
        for following in lines[index + 1 : index + 6]:
            if _BOUNDARY_HEADER.search(following) and len(
                list(_BOUNDARY_HEADER.finditer(following))
            ) >= 2:
                break  # another header: the table ended
            if following.strip():
                rows.append(following)
        if len(rows) != 1:
            continue  # zero rows, or several — say nothing rather than choose

        cell = _cell_at(rows[0], column)
        if cell:
            found.append(_Candidate(cell, rows[0].strip(), 0.7))

    return found


_BOUNDARY_HEADER = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(re.escape(label) for label in _ALL_LABELS) + r")(?![A-Za-z])",
    re.I,
)


def _cell_at(row: str, column: int) -> str:
    """The whitespace-delimited cell of `row` nearest to character `column`."""
    best, best_distance = "", 10**6
    for match in re.finditer(r"\S+(?:[ ]\S+)*?(?=[ ]{2,}|$)", row):
        distance = abs(match.start() - column)
        if distance < best_distance:
            best, best_distance = match.group(0).strip(), distance
    # Too far from the heading to be that column.
    return best if best_distance <= 12 else ""


def extract_fields(
    document_type: DocumentType, text: str
) -> dict[str, ExtractedField]:
    """Pull the values BAAR-AAMAD needs out of the document text.

    Deterministic: no model, no inference. Every value returned is a verbatim
    span of the document. A field that is not clearly stated is simply absent,
    which is an honest answer and the one the exporter is shown.
    """
    wanted = FIELDS_BY_TYPE.get(document_type, [])
    lines = [line for line in text.splitlines() if line.strip()]
    found: dict[str, ExtractedField] = {}

    for name in wanted:
        labels = FIELD_LABELS[name]
        candidates = _candidates(lines, labels) + _table_candidates(lines, labels)

        for candidate in candidates:
            value = candidate.value
            if name in NUMERIC_FIELDS:
                number = _first_number(value)
                if number is None:
                    continue  # not a quantity; try the next candidate
                value = number
            if not value:
                continue

            found[name] = ExtractedField(
                name=name,
                value=value,
                raw_snippet=candidate.snippet,
                confidence=round(min(candidate.score, 1.0), 2),
            )
            break

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
    if not missing or not text.strip():
        return found
    if not llm.is_configured():
        llm.record_skipped(
            "documents.fill_field_gaps",
            llm.Tier.FAST,
            "no API key; keeping the fields the patterns found",
        )
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
        result = llm.complete_json(
            system=system,
            user=user,
            schema=Gaps,
            tier=llm.Tier.FAST,
            call_site="documents.fill_field_gaps",
        )
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
