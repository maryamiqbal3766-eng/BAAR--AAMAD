"""
BAAR-AAMAD — RETRIEVAL
======================

    CASE PROFILE -> RAG -> CURATED SOURCES -> RELEVANT SOURCE EVIDENCE

Finds which curated sources bear on a given export case.

WHY LEXICAL AND NOT EMBEDDINGS: the corpus is a handful of precisely-worded
legal passages, and the query is a product and a destination. Term overlap
answers that well, in microseconds, with no model, no index to build, no
extra dependency and nothing to go wrong on deployment day. Embeddings would
add a heavy download and a cold-start delay to solve a problem this corpus
does not have. If the corpus grows into the thousands of passages, revisit.

Scoring is BM25-style: rarer terms count for more, and a long passage does
not win just by being long.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from core.errors import describe_route
from core.schemas import CaseProfile, Coverage, CoverageAssessment
from modules.corpus import ANY_ORIGIN, ANY_PRODUCT, Corpus, SourceRequirement
from modules.profile import product_terms

#: Standard BM25 knobs. k1 controls how fast term frequency saturates, b how
#: strongly passage length is penalised.
BM25_K1 = 1.4
BM25_B = 0.75

#: Words carrying no discriminating signal in a corpus that is entirely about
#: export requirements.
STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have in is it its of on or shall that
    the their this to was were will with which any not
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def profile_query(profile: CaseProfile) -> str:
    """Turn a case into the words we look for in the corpus."""
    parts = [
        profile.product_raw,
        profile.product_normalized,
        profile.destination,
        *profile.product_characteristics,
    ]
    return " ".join(part for part in parts if part)


@dataclass
class Hit:
    requirement: SourceRequirement
    score: float
    applicable: bool
    reason: str = ""


def _requirement_terms(requirement: SourceRequirement, corpus: Corpus) -> list[str]:
    """Everything about a requirement that a query could legitimately match."""
    text = " ".join(
        [
            requirement.title,
            requirement.what_is_required,
            requirement.why_required,
            requirement.when_it_applies,
            " ".join(requirement.keywords),
            " ".join(
                corpus.chunks[cid].text
                for cid in requirement.evidence_chunks
                if cid in corpus.chunks
            ),
        ]
    )
    return tokenize(text)


#: Trading blocs a country belongs to, so a source scoped to the bloc is
#: correctly understood to cover its members. This is a fact about the law —
#: the Union Customs Code really does apply in all 27 member states — and it
#: is routing data, not an allow-list: membership here does not make a country
#: supported, it only lets a bloc-scoped source match one of its members.
BLOCS: dict[str, tuple[str, ...]] = {
    "european union": (
        "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia",
        "Denmark", "Estonia", "Finland", "France", "Germany", "Greece",
        "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg",
        "Malta", "Netherlands", "Poland", "Portugal", "Romania", "Slovakia",
        "Slovenia", "Spain", "Sweden",
    ),
}

#: Aliases a bloc answers to in corpus metadata.
BLOC_ALIASES: dict[str, tuple[str, ...]] = {"european union": ("european union", "eu")}


def destination_terms(destination: str) -> set[str]:
    """Every scope term a destination legitimately answers to."""
    name = destination.strip().lower()
    if not name:
        return set()

    terms = {name}
    for bloc, members in BLOCS.items():
        if name in {member.lower() for member in members}:
            terms.update(BLOC_ALIASES.get(bloc, (bloc,)))
    return terms


def origin_terms(origin: str) -> set[str]:
    """Every scope term an origin legitimately answers to.

    `any origin` is always included: a source that does not narrow by origin
    applies whatever the goods' origin is, including when we do not know it.
    """
    terms = {ANY_ORIGIN}
    name = origin.strip().lower()
    if not name:
        return terms

    terms.add(name)
    for bloc, members in BLOCS.items():
        if name in {member.lower() for member in members}:
            terms.update(BLOC_ALIASES.get(bloc, (bloc,)))
    return terms


def _applies_to_case(
    requirement: SourceRequirement, corpus: Corpus, profile: CaseProfile
) -> tuple[bool, str]:
    """Scope gate: does this source cover the case's product and destination?

    A source that declares itself for other products or markets is excluded
    outright, whatever its term overlap — relevance is not the same thing as
    applicability.
    """
    source = corpus.sources.get(requirement.source_id)
    if source is None:
        return False, "source not loaded"

    product_scope = product_terms(profile)
    origin_scope = origin_terms(profile.origin_country)
    destination_scope = destination_terms(profile.destination)

    product_ok = not source.products or any(
        term.lower() == ANY_PRODUCT or any(term.lower() in p for p in product_scope)
        for term in source.products
    )
    origin_ok = not source.origins or any(
        term.lower() in origin_scope for term in source.origins
    )
    destination_ok = not source.destinations or any(
        term.lower() in destination_scope for term in source.destinations
    )

    if not product_ok:
        return False, f"source covers {', '.join(source.products)}"
    if not origin_ok:
        return False, f"source covers origins: {', '.join(source.origins)}"
    if not destination_ok:
        return False, f"source covers {', '.join(source.destinations)}"
    return True, ""


def search(
    profile: CaseProfile, corpus: Corpus, min_score: float = 0.0
) -> list[Hit]:
    """Rank the corpus requirements against one export case.

    Returns only requirements whose source applies to this product and
    destination. Anything out of scope is dropped, not down-ranked.
    """
    query = tokenize(profile_query(profile))
    candidates = corpus.requirements
    if not candidates:
        return []

    documents = {r.requirement_id: _requirement_terms(r, corpus) for r in candidates}
    lengths = {rid: len(terms) for rid, terms in documents.items()}
    average_length = sum(lengths.values()) / len(lengths) if lengths else 0.0
    total = len(documents)

    frequencies = {rid: Counter(terms) for rid, terms in documents.items()}
    containing = Counter()
    for terms in documents.values():
        containing.update(set(terms))

    hits: list[Hit] = []
    for requirement in candidates:
        applicable, reason = _applies_to_case(requirement, corpus, profile)
        if not applicable:
            continue

        rid = requirement.requirement_id
        score = 0.0
        for term in query:
            occurrences = frequencies[rid].get(term, 0)
            if not occurrences:
                continue
            document_frequency = containing[term]
            idf = math.log(
                1 + (total - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            norm = 1 - BM25_B + BM25_B * (lengths[rid] / average_length or 1)
            score += idf * (occurrences * (BM25_K1 + 1)) / (occurrences + BM25_K1 * norm)

        hits.append(Hit(requirement=requirement, score=round(score, 4), applicable=True))

    hits.sort(key=lambda hit: (-hit.score, hit.requirement.requirement_id))
    return [hit for hit in hits if hit.score >= min_score]


def assess_coverage(profile: CaseProfile, corpus: Corpus) -> CoverageAssessment:
    """Grade how much of this case the curated corpus can actually speak to.

    Three outcomes, and the middle one is the important one:

      COVERED            sources apply to the route AND to this kind of goods
      PARTIALLY COVERED  sources apply to the route, but none to these goods
      NOT COVERED        nothing applies; no requirement may be stated at all

    Partial coverage is not a failure. Customs formalities apply to any goods
    entering a market, so an exporter of something we hold no product rules
    for still gets real, cited requirements — together with an explicit
    statement of what went unassessed. Refusing the case outright would tell
    them less and would not be any more honest.
    """
    route = describe_route(
        profile.product_normalized or profile.product_raw,
        profile.origin_country,
        profile.destination,
    )

    hits = search(profile, corpus)
    if not hits:
        return CoverageAssessment(
            level=Coverage.NOT_COVERED,
            route=route,
            message=(
                f"No curated authoritative source covers {route}. BAAR-AAMAD "
                "cannot state the requirements for this shipment, and will "
                "not guess at them."
            ),
            unassessed=["Every requirement for this shipment."],
        )

    matched_ids: list[str] = []
    product_specific: list[str] = []
    general: list[str] = []

    for hit in hits:
        source = corpus.sources.get(hit.requirement.source_id)
        if source is None or source.source_id in matched_ids:
            continue
        matched_ids.append(source.source_id)
        (product_specific if source.is_product_specific else general).append(
            source.source_id
        )

    if product_specific:
        return CoverageAssessment(
            level=Coverage.COVERED,
            route=route,
            matched_source_ids=matched_ids,
            product_specific_source_ids=product_specific,
            general_source_ids=general,
            message=(
                f"BAAR-AAMAD holds sources covering {route}, including rules "
                "specific to this kind of goods."
            ),
        )

    product = profile.product_normalized or profile.product_raw or "these goods"
    return CoverageAssessment(
        level=Coverage.PARTIALLY_COVERED,
        route=route,
        matched_source_ids=matched_ids,
        general_source_ids=general,
        message=(
            f"BAAR-AAMAD holds sources covering the customs and origin "
            f"requirements for {route}, but none written specifically for "
            f"{product}. What follows is real and cited, but it is not the "
            "whole picture."
        ),
        unassessed=[
            f"Product-specific rules for {product} — for example material, "
            "chemical, safety, labelling or certification requirements. No "
            "curated source covers them, so none have been checked.",
        ],
    )
