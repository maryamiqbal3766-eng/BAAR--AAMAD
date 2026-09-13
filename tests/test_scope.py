"""
BAAR-AAMAD — COVERAGE, NOT SCOPE
================================

BAAR-AAMAD is product-, origin- and destination-agnostic. Leather bags from
Pakistan to Germany is the golden DEMO scenario and nothing more.

What the application can advise on is decided at run time by the curated
corpus, graded into COVERED / PARTIALLY COVERED / NOT COVERED. This file
proves that grading is honest in both directions:

  * it never states a requirement without a source, and
  * it never refuses a case just because we hold no product-specific source,
    when real route-level sources genuinely apply.

It also guards the contract: if anyone puts a product or market allow-list
back into core/schemas.py, the first test here fails.
"""

from __future__ import annotations

import pytest

from core import schemas
from core.errors import UnsupportedScopeError, describe_route
from core.schemas import CaseProfile, Coverage
from modules.corpus import ANY_ORIGIN, ANY_PRODUCT
from modules.profile import build_profile, product_terms
from modules.requirements import build_requirements
from modules.retrieval import (
    BLOCS,
    assess_coverage,
    destination_terms,
    origin_terms,
    product_matches,
    search,
)

EU = BLOCS["european union"]


def profile_for(product: str, origin: str = "Pakistan", destination: str = "Germany"):
    profile = CaseProfile(
        product_raw=product, origin_country=origin, destination=destination
    )
    build_profile(profile, use_ai=False)
    return profile


# ---------------------------------------------------------------------------
# The contract must stay agnostic
# ---------------------------------------------------------------------------


def test_the_contract_declares_no_product_or_market_scope():
    """The golden demo must not leak back into the shared contract."""
    for banned in (
        "MVP_PRODUCT",
        "MVP_DESTINATION",
        "SUPPORTED_PRODUCTS",
        "SUPPORTED_DESTINATIONS",
        "EU_MEMBER_STATES",
    ):
        assert not hasattr(schemas, banned), f"{banned} is back in core/schemas.py"


def test_case_profile_has_no_default_destination():
    assert CaseProfile(product_raw="anything").destination == ""


def test_case_profile_carries_an_origin():
    profile = CaseProfile(product_raw="x", origin_country="Pakistan")
    assert profile.origin_country == "Pakistan"


# ---------------------------------------------------------------------------
# The corpus declares its own scope
# ---------------------------------------------------------------------------


def test_every_source_declares_an_origin_scope(corpus):
    for source in corpus.sources.values():
        assert source.origins


def test_coverage_summary_comes_from_the_corpus(corpus):
    summary = corpus.coverage_summary()
    assert "European Union" in summary["destinations"]
    assert ANY_ORIGIN in summary["origins"]
    assert ANY_PRODUCT in summary["products"]


def test_general_and_product_specific_sources_are_distinguished(corpus):
    customs = corpus.sources["eu-ucc-952-2013"]
    chemical = corpus.sources["eu-reach-301-2014"]
    assert customs.is_product_specific is False  # applies to any goods
    assert chemical.is_product_specific is True  # written for leather articles


# ---------------------------------------------------------------------------
# COVERED — the golden demo scenario
# ---------------------------------------------------------------------------


def test_the_demo_scenario_is_fully_covered(corpus):
    coverage = assess_coverage(profile_for("Leather bags"), corpus)
    assert coverage.level is Coverage.COVERED
    assert coverage.product_specific_source_ids == ["eu-reach-301-2014"]
    assert coverage.unassessed == []
    assert "Leather bags" in coverage.route
    assert "Pakistan" in coverage.route and "Germany" in coverage.route


def test_a_covered_case_still_cites_every_source(corpus):
    result = build_requirements(profile_for("Leather bags"), corpus=corpus, use_ai=False)
    assert result.ok
    for requirement in result.payload["requirements"]:
        assert requirement.evidence
        for evidence in requirement.evidence:
            assert evidence.source_url.startswith("https://")


# ---------------------------------------------------------------------------
# PARTIALLY COVERED — the case the old model got wrong
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "product",
    ["ceramic floor tiles", "basmati rice", "cotton bedsheets", "surgical instruments"],
)
def test_goods_with_no_product_sources_are_partially_covered(product, corpus):
    """Customs rules apply to any goods. Refusing the case would say less."""
    coverage = assess_coverage(profile_for(product), corpus)

    assert coverage.level is Coverage.PARTIALLY_COVERED
    assert coverage.general_source_ids
    assert coverage.product_specific_source_ids == []
    assert coverage.unassessed, "partial coverage must say what went unassessed"
    assert product in coverage.message


def test_partial_coverage_still_produces_real_cited_requirements(corpus):
    result = build_requirements(
        profile_for("ceramic floor tiles"), corpus=corpus, use_ai=False
    )
    assert result.ok
    requirements = result.payload["requirements"]
    assert requirements

    ids = {r.requirement_id for r in requirements}
    assert "REQ-COMMERCIAL-INVOICE" in ids
    assert "REQ-DOCUMENT-CONSISTENCY" in ids
    # and nothing leather was claimed about ceramic tiles
    assert "REQ-CHROMIUM-VI" not in ids

    for requirement in requirements:
        assert requirement.evidence


def test_goods_never_acquire_a_category_they_were_not_described_as():
    """The bug this refactor removed: a leather category was asserted about
    anything the old matcher could name."""
    tiles = profile_for("ceramic floor tiles")
    terms = product_terms(tiles)
    assert "leather" not in terms
    assert "article" not in terms


def test_the_product_gate_reads_the_corpus_not_the_code():
    """A source's declared goods decide whether it applies, in both directions."""
    case_terms = product_terms(profile_for("handmade leather shoulder bags"))

    # Declared fully within what the exporter described -> applies.
    assert product_matches("leather bags", case_terms) is True
    assert product_matches("any goods", case_terms) is True
    # Declared terms the exporter never used -> does not apply.
    assert product_matches("ceramic tiles", case_terms) is False
    assert product_matches("leather footwear", case_terms) is False


def test_an_underspecified_product_does_not_pull_in_a_material_source():
    """'bags' must not match a source written for leather bags: we do not know
    what these bags are made of, and guessing is exactly the failure mode."""
    assert product_matches("leather bags", product_terms(profile_for("bags"))) is False


def test_a_product_with_no_sources_is_still_a_valid_case(corpus):
    """Product-agnostic means the case proceeds and coverage tells the truth."""
    rice = profile_for("basmati rice")
    assert rice.product_normalized == "basmati rice"
    assert assess_coverage(rice, corpus).level is Coverage.PARTIALLY_COVERED


# ---------------------------------------------------------------------------
# NOT COVERED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("destination", ["Japan", "United Kingdom", "Brazil", "Canada"])
def test_a_market_with_no_sources_is_not_covered(destination, corpus):
    coverage = assess_coverage(
        profile_for("Leather bags", destination=destination), corpus
    )
    assert coverage.level is Coverage.NOT_COVERED
    assert coverage.matched_source_ids == []
    assert coverage.can_state_requirements is False
    assert destination in coverage.message


def test_an_uncovered_market_states_no_requirements(corpus):
    result = build_requirements(
        profile_for("Leather bags", destination="Japan"), corpus=corpus, use_ai=False
    )
    assert result.ok is False
    assert result.payload["requirements"] == []
    assert result.payload["coverage"].level is Coverage.NOT_COVERED


def test_search_returns_nothing_for_an_uncovered_market(corpus):
    assert search(profile_for("Leather bags", destination="Japan"), corpus) == []


# ---------------------------------------------------------------------------
# Origin is a real dimension now
# ---------------------------------------------------------------------------


def test_origin_always_answers_to_any_origin():
    """Sources that do not narrow by origin apply whatever the origin is."""
    assert ANY_ORIGIN in origin_terms("Pakistan")
    assert ANY_ORIGIN in origin_terms("")  # including when we do not know it


def test_an_unknown_origin_does_not_block_a_case(corpus):
    coverage = assess_coverage(profile_for("Leather bags", origin=""), corpus)
    assert coverage.level is Coverage.COVERED


@pytest.mark.parametrize("origin", ["Pakistan", "India", "Bangladesh", "Vietnam"])
def test_any_origin_is_accepted_while_no_source_narrows_by_it(origin, corpus):
    coverage = assess_coverage(profile_for("Leather bags", origin=origin), corpus)
    assert coverage.level is Coverage.COVERED


def test_an_eu_origin_also_answers_to_the_bloc():
    assert "european union" in origin_terms("France")


# ---------------------------------------------------------------------------
# Bloc membership
# ---------------------------------------------------------------------------


def test_all_27_member_states_are_known():
    assert len(EU) == 27
    assert len(set(EU)) == 27
    for expected in ("Germany", "France", "Ireland", "Czechia", "Sweden"):
        assert expected in EU


def test_the_uk_is_not_a_member():
    assert "United Kingdom" not in EU


def test_a_member_state_answers_to_the_bloc():
    terms = destination_terms("France")
    assert "france" in terms and "european union" in terms


def test_a_non_member_does_not():
    assert "european union" not in destination_terms("Japan")


@pytest.mark.parametrize("destination", EU)
def test_every_member_state_is_covered_for_the_demo_product(destination, corpus):
    coverage = assess_coverage(
        profile_for("Leather bags", destination=destination), corpus
    )
    assert coverage.level is Coverage.COVERED


# ---------------------------------------------------------------------------
# Error wording is generic
# ---------------------------------------------------------------------------


def test_scope_error_names_the_route_not_a_hard_coded_product():
    error = UnsupportedScopeError.for_route(
        product="ceramic tiles", origin="Pakistan", destination="Japan"
    )
    message = error.user_message
    assert "ceramic tiles" in message
    assert "Japan" in message
    assert "leather" not in message.lower()
    assert "Germany" not in message


def test_the_default_scope_message_names_no_product_or_market():
    message = UnsupportedScopeError().user_message
    assert "leather" not in message.lower()
    assert "germany" not in message.lower()


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("Leather bags", "Pakistan", "Germany"), "Leather bags from Pakistan to Germany"),
        (("Rice", "", "France"), "Rice to France"),
        (("", "", ""), "this shipment"),
    ],
)
def test_route_description(args, expected):
    assert describe_route(*args) == expected
