"""
BAAR-AAMAD — PRODUCT UNDERSTANDING
==================================

    WHAT THE EXPORTER TYPED -> STRUCTURED CASE PROFILE

THIS MODULE HOLDS NO PRODUCT VOCABULARY, AND MUST NOT ACQUIRE ONE.

An earlier version recognised leather articles and returned nothing for
anything else, which quietly made the golden demo into the product's scope: an
exporter of rice or ceramic tiles had their goods silently treated as
unrecognised, and a leather category was asserted about anything the matcher
did name. Both are gone.

What replaces them:

  * Python TIDIES the exporter's own words and never replaces them with a
    category of its own invention.
  * The CORPUS decides which products it speaks to. Each source declares the
    goods it covers, and modules.retrieval matches the exporter's description
    against those declarations. Adding a source for a new kind of goods is
    therefore the only way to widen what can be assessed — and it needs no
    change here.
  * The MODEL, when available, describes physical characteristics of whatever
    was described. Descriptive only; it steers retrieval and never becomes a
    regulatory claim.
  * Where the corpus holds nothing product-specific, coverage says
    PARTIALLY COVERED and names what went unassessed. That is the honest
    answer, and it is never a guess.

SAFETY: this module never states a final tariff classification. The spec is
explicit that an uncertain classification must be marked for verification,
and classification is a legal determination we are not entitled to make. Any
HS code the exporter's own invoice carries is DOCUMENT evidence, read by the
Document Intelligence module — it is not a claim BAAR-AAMAD makes.
"""

from __future__ import annotations

import logging
import re

from core.schemas import CaseProfile, ModuleResult, VerificationStatus

log = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z0-9]+")

#: Words carrying no signal about what the goods are. Short, and deliberately
#: about GRAMMAR rather than about any particular kind of product.
_FILLER = frozenset(
    """
    a an and are as at be by for from in is it its of on or the their this to
    with our my your we us goods good item items product products
    """.split()
)


def stems(text: str) -> set[str]:
    """The comparable word-stems of a piece of text.

    Crude on purpose: lowercase, split on non-alphanumerics, drop grammar
    words, and fold a trailing plural 's'. Applied to BOTH sides of every
    comparison, so "leather bags" and "a bag of leather" reduce alike. It is
    not a linguistics engine and is not trying to be.
    """
    out: set[str] = set()
    for word in _WORD.findall(text.lower()):
        if word in _FILLER or len(word) < 2:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.add(word)
    return out


def normalize_product(raw: str) -> tuple[str, list[str]]:
    """Tidy what the exporter typed. Nothing more.

    Returns the cleaned description and an empty characteristics list. There
    is deliberately no deterministic characteristic here: any statement about
    what goods are made of, or what they touch, would be a claim about a
    product this module knows nothing about. Characteristics come from the
    model (`ai_describe_product`), which sees the actual description.

    Capitalisation is left exactly as typed. The exporter's wording is quoted
    back to them all over the application, and silently re-casing it makes
    BAAR-AAMAD look like it substituted its own idea of the product.
    """
    cleaned = " ".join(raw.split()).strip(" ,.;:-—")
    return cleaned, []


def product_terms(profile: CaseProfile) -> set[str]:
    """Every word-stem retrieval may legitimately match this product on.

    Built ONLY from what the exporter supplied and what the model observed
    about it. No category is added on the application's behalf: if the words
    "leather bags" are here, it is because they were typed or observed, never
    because code decided this case was a leather case.
    """
    text = " ".join(
        [
            profile.product_raw,
            profile.product_normalized,
            *profile.product_characteristics,
        ]
    )
    return stems(text)


def ai_describe_product(raw: str) -> list[str]:
    """Ask the model for further characteristics of an unusual description.

    Optional and additive. Characteristics are descriptive only — they steer
    retrieval, they never become regulatory claims — so a wrong one shows up
    as an irrelevant requirement, not as invented law. Any failure returns
    nothing and the deterministic result stands.
    """
    from core import llm

    if not raw.strip():
        return []
    if not llm.is_configured():
        llm.record_skipped(
            "profile.describe_product",
            llm.Tier.FAST,
            "no API key; using the exporter's own description unchanged",
        )
        return []

    from pydantic import BaseModel, Field

    class Described(BaseModel):
        characteristics: list[str] = Field(default_factory=list)

    try:
        result = llm.complete_json(
            system=(
                "You describe physical characteristics of export goods that "
                "affect which product regulations apply — materials, parts "
                "that touch the skin, whether it is a finished article. "
                "Report only what the description supports. Never name a "
                "regulation, a tariff code or a legal requirement."
            ),
            user=f"Product description from the exporter: {raw}",
            schema=Described,
            tier=llm.Tier.FAST,
            call_site="profile.describe_product",
        )
    except Exception as exc:
        log.warning("Product understanding unavailable, using patterns only: %s", exc)
        return []

    return [c.strip() for c in result.characteristics if c and c.strip()][:6]


def build_profile(profile: CaseProfile, use_ai: bool = True) -> ModuleResult:
    """Fill in the derived parts of a Case Profile, in place.

    The exporter's own entries — product_raw, destination, exporter and
    shipment details — are never overwritten.

    Any product goes through. Whether BAAR-AAMAD can then say anything about
    it is a question for the corpus, answered by
    modules.retrieval.assess_coverage, and it is answered per case rather than
    decided in advance here.
    """
    normalized, characteristics = normalize_product(profile.product_raw)

    if not normalized:
        profile.product_normalized = ""
        profile.product_characteristics = []
        profile.classification_verification_status = (
            VerificationStatus.REQUIRES_VERIFICATION
        )
        return ModuleResult(
            ok=False,
            reason=(
                "No product description was given, so there is nothing to find "
                "requirements for."
            ),
        )

    profile.product_normalized = normalized
    profile.product_characteristics = characteristics

    if use_ai:
        for extra in ai_describe_product(profile.product_raw):
            if extra not in profile.product_characteristics:
                profile.product_characteristics.append(extra)

    # A tariff classification is a legal determination. We do not make one.
    profile.classification_context = (
        "No tariff classification has been determined by BAAR-AAMAD. Any HS "
        "code shown for this case is the one stated on your own documents and "
        "must be confirmed with your customs broker."
    )
    profile.classification_verification_status = VerificationStatus.REQUIRES_VERIFICATION

    return ModuleResult(
        ok=True,
        payload={
            "product_normalized": normalized,
            "characteristics": list(profile.product_characteristics),
        },
    )
