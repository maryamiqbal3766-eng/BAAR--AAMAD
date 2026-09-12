"""
BAAR-AAMAD — PRODUCT UNDERSTANDING
==================================

    WHAT THE EXPORTER TYPED -> STRUCTURED CASE PROFILE

Normalizes a free-text product description into the terms the corpus is
written in, and records the characteristics that decide which requirements
apply — for leather bags, whether the article touches the skin matters,
because that is what the chromium VI restriction turns on.

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

#: Words that mean "made of leather", however the exporter phrases it.
LEATHER_TERMS = ("leather", "hide", "suede", "nappa", "full-grain", "full grain")

#: The article words we recognise, grouped by the canonical product each maps
#: to. All of these touch the skin in normal use, which is the test the
#: chromium VI restriction turns on.
ARTICLE_TERMS: dict[str, tuple[str, ...]] = {
    "Leather bags": (
        "bag", "bags", "handbag", "handbags", "satchel", "satchels", "tote",
        "totes", "backpack", "backpacks", "rucksack", "briefcase", "briefcases",
        "holdall", "shoulder bag", "messenger bag", "duffel",
    ),
    "Leather belts": ("belt", "belts", "waistbelt", "strap", "straps"),
    "Leather wallets and purses": (
        "wallet", "wallets", "purse", "purses", "cardholder", "card holder",
        "coin pouch",
    ),
    "Leather gloves": ("glove", "gloves", "mitt", "mitts", "mitten", "mittens"),
    "Leather jackets and garments": (
        "jacket", "jackets", "coat", "coats", "garment", "garments", "vest",
        "waistcoat", "apparel",
    ),
    "Leather cases and covers": (
        "case", "cases", "cover", "covers", "sleeve", "sleeves", "pouch",
        "folio", "portfolio",
    ),
}

#: The category every recognised product belongs to. This is the term the
#: corpus is written against, so retrieval matches on it rather than on each
#: individual article name.
PRODUCT_CATEGORY = "Leather articles"

#: Products this module can recognise deterministically, derived from the
#: vocabulary above rather than declared twice.
#:
#: NOTE — THIS IS NOT THE APPLICATION'S SCOPE.
#: What BAAR-AAMAD can advise on is decided by the corpus, graded by
#: modules.retrieval.assess_coverage. This list only says which descriptions
#: the pattern matcher can name without a model. A product missing from it is
#: not rejected: it goes through as the exporter's own words, and coverage
#: decides honestly what can and cannot be assessed.
#:
#: The leather vocabulary here is the last piece of golden-demo shape left in
#: application logic, and is scheduled for replacement by generic product
#: understanding.
RECOGNISED_PRODUCTS: tuple[str, ...] = tuple(ARTICLE_TERMS)

#: Characteristics the corpus keys off. Each is written so an exporter can
#: see why it was recorded.
SKIN_CONTACT = "Comes into contact with the skin in normal use (handles, straps, trim)"
LEATHER_ARTICLE = "Made of leather or contains leather parts"
FINISHED_GOOD = "Finished consumer article, not a raw material"


def _words(text: str) -> set[str]:
    """Lowercased word set, so 'bags' does not match inside 'baggage'."""
    return set(re.findall(r"[a-z]+", text.lower()))


def looks_like_leather(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in LEATHER_TERMS)


def classify_article(text: str) -> str:
    """Which supported product this description is, or '' if none.

    Word-boundary matching on purpose: a phrase mentioning "baggage" is not a
    bag, and we would rather recognise nothing than the wrong thing.
    """
    lowered = text.lower()
    words = _words(text)
    for canonical, terms in ARTICLE_TERMS.items():
        for term in terms:
            hit = term in lowered if " " in term else term in words
            if hit:
                return canonical
    return ""


def normalize_product(raw: str) -> tuple[str, list[str]]:
    """Map free text onto a supported product and its characteristics.

    Deterministic. Returns an empty name when the text does not describe a
    leather article we have sources for, rather than forcing it into one.
    """
    if not raw.strip() or not looks_like_leather(raw):
        return "", []

    canonical = classify_article(raw)
    if not canonical:
        return "", []

    characteristics = [LEATHER_ARTICLE, SKIN_CONTACT, FINISHED_GOOD]
    return canonical, characteristics


def product_terms(profile: CaseProfile) -> set[str]:
    """Every term retrieval may legitimately match this product on.

    Includes the category, because the corpus is written against "leather
    articles" — which is what the REACH restriction actually says — not
    against each individual article name.
    """
    terms = {profile.product_raw.lower(), profile.product_normalized.lower()}

    # The category is only claimed when the product was actually recognised as
    # belonging to it. Adding it unconditionally would make goods we cannot
    # identify match a source written for a material they may not contain.
    if profile.product_normalized:
        terms |= {PRODUCT_CATEGORY.lower(), "leather"}

    return {term for term in terms if term}


def ai_describe_product(raw: str) -> list[str]:
    """Ask the model for further characteristics of an unusual description.

    Optional and additive. Characteristics are descriptive only — they steer
    retrieval, they never become regulatory claims — so a wrong one shows up
    as an irrelevant requirement, not as invented law. Any failure returns
    nothing and the deterministic result stands.
    """
    from core import llm

    if not llm.is_configured() or not raw.strip():
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
        )
    except Exception as exc:
        log.warning("Product understanding unavailable, using patterns only: %s", exc)
        return []

    return [c.strip() for c in result.characteristics if c and c.strip()][:6]


def build_profile(profile: CaseProfile, use_ai: bool = True) -> ModuleResult:
    """Fill in the AI-derived parts of a Case Profile, in place.

    The exporter's own entries — product_raw, destination, exporter and
    shipment details — are never overwritten.
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
                "The product description was not recognised as a leather bag, "
                "so no product characteristics were recorded."
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


def is_recognised_product(profile: CaseProfile) -> bool:
    """Whether the deterministic matcher could name this product.

    This says nothing about whether BAAR-AAMAD can advise on the shipment —
    that is coverage, and only the corpus can answer it. An unrecognised
    product is still a valid case; it simply carries the exporter's own
    wording forward.
    """
    return profile.product_normalized in RECOGNISED_PRODUCTS
