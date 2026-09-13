"""
BAAR-AAMAD — CURATED SOURCE LIBRARY
===================================

Loads and validates the authoritative sources in data/corpus.

This is the only place regulatory evidence may come from. If a statement is
not traceable to a chunk loaded here, BAAR-AAMAD does not make it.

The loader is strict on purpose: a malformed source file, a requirement that
points at a chunk that does not exist, or a source with no URL is a fault we
want to see at startup, not a quietly missing citation in front of a judge.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.errors import CorpusEmptyError
from core.schemas import DocumentType, RegulatoryEvidence

log = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"

VALID_CHECK_KINDS = {"document_present", "fields_present", "fields_agree"}


# ---------------------------------------------------------------------------
# In-memory shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One quoted passage of an authoritative source."""

    chunk_id: str
    locator: str
    text: str
    source_id: str
    source_name: str
    source_url: str

    def as_evidence(self, relevance: float = 0.0) -> RegulatoryEvidence:
        """Convert to the shared contract's evidence object.

        The citation travels with the text, so a requirement can never end up
        on screen quoting something without saying where it came from.
        """
        return RegulatoryEvidence(
            evidence_id=self.chunk_id,
            source_name=self.source_name,
            source_url=self.source_url,
            excerpt=self.text,
            locator=self.locator,
            relevance=relevance,
        )


@dataclass(frozen=True)
class Check:
    """A deterministic check that the Validation module knows how to run."""

    kind: str
    description: str
    document_type: DocumentType | None = None
    document_types: tuple[DocumentType, ...] = ()
    fields: tuple[str, ...] = ()
    compare: str = "text"


@dataclass(frozen=True)
class SourceRequirement:
    """A requirement as curated against its source, before it meets a case."""

    requirement_id: str
    title: str
    what_is_required: str
    why_required: str
    when_it_applies: str
    satisfying_evidence: tuple[str, ...]
    needed_document_or_info: tuple[str, ...]
    expected_document_types: tuple[DocumentType, ...]
    evidence_chunks: tuple[str, ...]
    keywords: tuple[str, ...]
    checks: tuple[Check, ...]
    verification_note: str = ""
    source_id: str = ""


#: Wildcards a source may declare, meaning "this dimension does not narrow me".
ANY_PRODUCT = "any goods"
ANY_ORIGIN = "any origin"


@dataclass
class Source:
    source_id: str
    source_name: str
    source_url: str
    publisher: str
    retrieved_at: str
    products: tuple[str, ...]
    origins: tuple[str, ...]
    destinations: tuple[str, ...]
    #: How to NAME this source's product scope to a person. `products` is a
    #: matching vocabulary — it may hold two dozen wordings of the same kind of
    #: goods so an exporter's own phrasing can be recognised — and reading that
    #: list aloud tells nobody anything. Optional; falls back to the list.
    scope_label: str = ""
    chunks: dict[str, Chunk] = field(default_factory=dict)
    requirements: tuple[SourceRequirement, ...] = ()

    @property
    def describe_products(self) -> str:
        if self.scope_label:
            return self.scope_label
        return ", ".join(self.products)

    @property
    def is_product_specific(self) -> bool:
        """True when this source is written for a kind of goods.

        A source declaring `any goods` speaks to the route — customs
        formalities, origin procedure — not to what is in the box. That
        distinction is what separates COVERED from PARTIALLY COVERED.
        """
        return bool(self.products) and not any(
            term.strip().lower() == ANY_PRODUCT for term in self.products
        )


@dataclass
class Corpus:
    sources: dict[str, Source] = field(default_factory=dict)

    @property
    def chunks(self) -> dict[str, Chunk]:
        return {cid: c for s in self.sources.values() for cid, c in s.chunks.items()}

    @property
    def requirements(self) -> list[SourceRequirement]:
        return [r for s in self.sources.values() for r in s.requirements]

    def chunk(self, chunk_id: str) -> Chunk | None:
        return self.chunks.get(chunk_id)

    def coverage_summary(self) -> dict[str, list[str]]:
        """What this library actually covers, as declared by its own sources.

        The single place the application should ask "what can we advise on?".
        Nothing anywhere else may carry a parallel list of supported products
        or markets — that is how demo scope leaks into the product.
        """
        products: set[str] = set()
        origins: set[str] = set()
        destinations: set[str] = set()

        for source in self.sources.values():
            products.update(source.products)
            origins.update(source.origins)
            destinations.update(source.destinations)

        return {
            "products": sorted(products),
            "origins": sorted(origins),
            "destinations": sorted(destinations),
        }

    def describe_coverage(self) -> str:
        """One readable sentence for an error message or a landing page.

        Reads each source's own scope label rather than its matching
        vocabulary, so this stays a sentence and not an inventory.
        """
        summary = self.coverage_summary()
        destinations = summary["destinations"]
        products = sorted(
            {
                source.describe_products
                for source in self.sources.values()
                if source.is_product_specific
            }
        )

        parts = []
        if destinations:
            parts.append("exports to " + ", ".join(destinations))
        if products:
            parts.append("product rules for " + ", ".join(products))
        return "; ".join(parts)

    def evidence_for(
        self, requirement: SourceRequirement, relevance: float = 0.0
    ) -> list[RegulatoryEvidence]:
        """The evidence behind one requirement, in citation order."""
        out = []
        for chunk_id in requirement.evidence_chunks:
            chunk = self.chunk(chunk_id)
            if chunk is not None:
                out.append(chunk.as_evidence(relevance))
        return out


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class CorpusError(ValueError):
    """A source file is malformed. Raised at load time, never swallowed."""


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data or data[key] in (None, "", []):
        raise CorpusError(f"{where}: missing required field {key!r}")
    return data[key]


def _document_type(value: str, where: str) -> DocumentType:
    try:
        return DocumentType(value)
    except ValueError as exc:
        raise CorpusError(f"{where}: unknown document type {value!r}") from exc


def _parse_check(raw: dict[str, Any], where: str) -> Check:
    kind = _require(raw, "kind", where)
    if kind not in VALID_CHECK_KINDS:
        raise CorpusError(
            f"{where}: unknown check kind {kind!r}; expected one of "
            f"{sorted(VALID_CHECK_KINDS)}"
        )

    document_type = raw.get("document_type")
    return Check(
        kind=kind,
        description=_require(raw, "description", where),
        document_type=_document_type(document_type, where) if document_type else None,
        document_types=tuple(
            _document_type(value, where) for value in raw.get("document_types", [])
        ),
        fields=tuple(raw.get("fields", []))
        or ((raw["field"],) if "field" in raw else ()),
        compare=raw.get("compare", "text"),
    )


def _parse_source(path: Path) -> Source:
    where = path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{where}: not valid JSON — {exc}") from exc

    source_id = _require(data, "source_id", where)
    source_name = _require(data, "source_name", where)
    source_url = _require(data, "source_url", where)
    if not str(source_url).startswith("https://"):
        raise CorpusError(f"{where}: source_url must be an https URL")

    applies_to = data.get("applies_to", {})
    source = Source(
        source_id=source_id,
        source_name=source_name,
        source_url=source_url,
        publisher=data.get("publisher", ""),
        retrieved_at=data.get("retrieved_at", ""),
        products=tuple(applies_to.get("products", [])),
        # A source that says nothing about origin is not origin-dependent.
        origins=tuple(applies_to.get("origins", [ANY_ORIGIN])),
        destinations=tuple(applies_to.get("destinations", [])),
        scope_label=applies_to.get("scope_label", ""),
    )

    for raw in _require(data, "chunks", where):
        chunk_id = _require(raw, "chunk_id", f"{where} chunk")
        source.chunks[chunk_id] = Chunk(
            chunk_id=chunk_id,
            locator=raw.get("locator", ""),
            text=_require(raw, "text", f"{where} chunk {chunk_id}"),
            source_id=source_id,
            source_name=source_name,
            # A chunk may cite a more specific page than its parent source.
            source_url=raw.get("chunk_url") or source_url,
        )

    requirements = []
    for raw in data.get("requirements", []):
        requirement_id = _require(raw, "requirement_id", f"{where} requirement")
        spot = f"{where} requirement {requirement_id}"

        evidence_chunks = tuple(_require(raw, "evidence_chunks", spot))
        for chunk_id in evidence_chunks:
            if chunk_id not in source.chunks:
                raise CorpusError(f"{spot}: evidence_chunks points at unknown {chunk_id!r}")

        requirements.append(
            SourceRequirement(
                requirement_id=requirement_id,
                title=_require(raw, "title", spot),
                what_is_required=_require(raw, "what_is_required", spot),
                why_required=_require(raw, "why_required", spot),
                when_it_applies=_require(raw, "when_it_applies", spot),
                satisfying_evidence=tuple(raw.get("satisfying_evidence", [])),
                needed_document_or_info=tuple(raw.get("needed_document_or_info", [])),
                expected_document_types=tuple(
                    _document_type(value, spot)
                    for value in raw.get("expected_document_types", [])
                ),
                evidence_chunks=evidence_chunks,
                keywords=tuple(raw.get("keywords", [])),
                checks=tuple(_parse_check(c, spot) for c in raw.get("checks", [])),
                verification_note=raw.get("verification_note", ""),
                source_id=source_id,
            )
        )

    source.requirements = tuple(requirements)
    return source


def load_corpus(directory: Path | None = None) -> Corpus:
    """Read every source file. Raises rather than serving a broken library."""
    directory = directory or CORPUS_DIR
    corpus = Corpus()

    for path in sorted(directory.glob("*.json")):
        source = _parse_source(path)
        if source.source_id in corpus.sources:
            raise CorpusError(f"duplicate source_id {source.source_id!r} in {path.name}")
        corpus.sources[source.source_id] = source

    if not corpus.sources:
        raise CorpusEmptyError(f"no source files found in {directory}")

    seen: set[str] = set()
    for requirement in corpus.requirements:
        if requirement.requirement_id in seen:
            raise CorpusError(f"duplicate requirement_id {requirement.requirement_id!r}")
        seen.add(requirement.requirement_id)

    log.info(
        "Corpus loaded: %d sources, %d chunks, %d requirements",
        len(corpus.sources),
        len(corpus.chunks),
        len(corpus.requirements),
    )
    return corpus


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    """Cached corpus for the running app. Call load_corpus() in tests."""
    return load_corpus()
