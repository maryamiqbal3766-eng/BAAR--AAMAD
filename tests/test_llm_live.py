"""
LIVE inference against Groq. Skipped unless GROQ_API_KEY is in the environment.

    .venv\\Scripts\\python.exe -m pytest tests/test_llm_live.py -v

These are the only tests in the suite that touch the network. They exist so
that "live inference works" is a thing that was measured, not a thing that was
claimed. Nothing here prints or asserts on the key itself.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from core import llm

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not llm.is_configured(),
        reason="GROQ_API_KEY not set — live inference not exercised",
    ),
]


class DocumentNames(BaseModel):
    document_types: list[str] = Field(default_factory=list)


class Interpretation(BaseModel):
    what_is_required: str = ""
    grounded: bool = False


def test_the_primary_model_is_offered():
    assert llm.PRIMARY_MODEL in llm.available_models()


def test_both_tiers_resolve_live_to_the_primary_model():
    assert llm.resolve_model(llm.Tier.REASONING) == llm.PRIMARY_MODEL
    assert llm.resolve_model(llm.Tier.FAST) == llm.PRIMARY_MODEL


def test_a_live_call_returns_validated_structured_output():
    result = llm.complete_json(
        system=(
            "You identify trade document names mentioned in a message. Report "
            "only names that actually appear in it."
        ),
        user="The file holds a Commercial Invoice and a Packing List.",
        schema=DocumentNames,
        tier=llm.Tier.REASONING,
        max_tokens=300,
        call_site="live_test.document_names",
    )
    joined = " ".join(result.document_types).lower()
    assert "invoice" in joined


def test_the_live_call_is_recorded_with_the_model_that_served_it():
    marker = llm.ledger_marker()
    llm.complete_json(
        system="You echo structure.",
        user="Reply with what_is_required set to 'a commercial invoice'.",
        schema=Interpretation,
        tier=llm.Tier.REASONING,
        max_tokens=300,
        call_site="live_test.ledger",
    )
    calls = llm.calls_since(marker)
    assert len(calls) == 1
    assert calls[0].model == llm.PRIMARY_MODEL
    assert calls[0].outcome in (llm.Outcome.OK, llm.Outcome.REPAIRED)
    assert calls[0].latency_ms > 0
    assert calls[0].total_tokens > 0


def test_live_output_carries_no_reasoning_content():
    """`reasoning_format=hidden` must keep chain-of-thought out of `content`."""
    raw = llm.complete(
        system="You answer in one short sentence.",
        user="Name one document used in exporting goods.",
        tier=llm.Tier.REASONING,
        max_tokens=200,
        call_site="live_test.no_cot",
    )
    lowered = raw.lower()
    for marker in ("<think>", "<reasoning>", "we need to", "let me think"):
        assert marker not in lowered
