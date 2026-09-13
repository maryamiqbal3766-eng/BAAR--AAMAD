"""
The Groq gateway, exercised against a fake client.

No network. These tests prove the things that decide whether live inference
behaves itself: which model is asked for, that chain-of-thought is suppressed
at the transport, that an unsupported parameter degrades instead of failing,
and that every call lands in the ledger exactly once.

The live counterpart is tests/test_llm_live.py, which is skipped without a key.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from core import llm
from core.errors import LLMResponseInvalidError, LLMUnavailableError


class Shape(BaseModel):
    value: str


# ---------------------------------------------------------------------------
# A fake Groq client
# ---------------------------------------------------------------------------


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Usage:
    def __init__(self, prompt: int, completion: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class _Completion:
    def __init__(self, content: str, model: str) -> None:
        self.choices = [_Choice(content)]
        self.model = model
        self.usage = _Usage(11, 7)


class FakeClient:
    """Records every request and replies from a scripted list.

    `router` lets a test script one call site while every other call site in a
    full pipeline run gets a harmless empty object. Without it, the stages that
    run before the one under test silently eat the script.
    """

    def __init__(
        self,
        replies: list[str | Exception] | None = None,
        model: str = llm.PRIMARY_MODEL,
        router=None,
        default: str = '{"value": "default"}',
    ):
        self.replies = list(replies or [])
        self.model = model
        self.router = router
        self.default = default
        self.requests: list[dict] = []
        self.chat = self  # client.chat.completions.create(...)
        self.completions = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.router is not None:
            routed = self.router(kwargs)
            if routed is not None:
                reply = routed
            else:
                reply = self.replies.pop(0) if self.replies else self.default
        else:
            reply = self.replies.pop(0) if self.replies else self.default
        if isinstance(reply, Exception):
            raise reply
        return _Completion(reply, self.model)


@pytest.fixture(autouse=True)
def _isolate_gateway(monkeypatch):
    """Every test starts with an empty ledger and a resolved primary model."""
    llm.clear_ledger()
    llm.reset_cache()
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "available_models", lambda refresh=False: {llm.PRIMARY_MODEL})
    yield
    llm.clear_ledger()
    llm.reset_cache()


def install(monkeypatch, client: FakeClient) -> FakeClient:
    monkeypatch.setattr(llm, "_client", lambda: client)
    return client


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


def test_both_tiers_resolve_to_the_primary_model():
    """One identifiable model for the whole application, by decision."""
    assert llm.resolve_model(llm.Tier.REASONING) == llm.PRIMARY_MODEL
    assert llm.resolve_model(llm.Tier.FAST) == llm.PRIMARY_MODEL
    assert llm.PRIMARY_MODEL == "openai/gpt-oss-120b"


def test_every_tier_leads_with_the_primary_model():
    for candidates in llm.MODEL_PREFERENCES.values():
        assert candidates[0] == llm.PRIMARY_MODEL


def test_resolution_report_says_whether_we_are_on_the_primary_model():
    report = llm.resolution_report()
    assert report["configured"] is True
    assert report["primary"] == llm.PRIMARY_MODEL
    assert report["on_primary"] is True


def test_an_env_override_is_honoured(monkeypatch):
    monkeypatch.setenv("BAAR_MODEL_REASONING", "some/other-model")
    assert llm.resolve_model(llm.Tier.REASONING) == "some/other-model"


# ---------------------------------------------------------------------------
# Transport settings
# ---------------------------------------------------------------------------


def test_reasoning_is_hidden_at_the_transport(monkeypatch):
    """TS-2 is a transport setting, not a prompt request."""
    client = install(monkeypatch, FakeClient(['{"value": "ok"}']))
    llm.complete_json(system="s", user="u", schema=Shape, call_site="t")
    assert client.requests[0]["reasoning_format"] == "hidden"


def test_the_current_token_parameter_is_sent(monkeypatch):
    client = install(monkeypatch, FakeClient(['{"value": "ok"}']))
    llm.complete_json(system="s", user="u", schema=Shape, max_tokens=321, call_site="t")
    assert client.requests[0]["max_completion_tokens"] == 321
    assert "max_tokens" not in client.requests[0]


def test_an_unsupported_parameter_is_dropped_and_the_call_retried(monkeypatch):
    """A model that does not know `reasoning_format` must still be usable."""
    client = install(
        monkeypatch,
        FakeClient(
            [
                Exception("400: Unsupported parameter: 'reasoning_format'"),
                '{"value": "ok"}',
            ]
        ),
    )
    result = llm.complete_json(system="s", user="u", schema=Shape, call_site="t")

    assert result.value == "ok"
    assert "reasoning_format" in client.requests[0]
    assert "reasoning_format" not in client.requests[1]


def test_an_unsupported_token_parameter_falls_back_to_the_old_name(monkeypatch):
    client = install(
        monkeypatch,
        FakeClient(
            [
                Exception("400: Unrecognized request argument: max_completion_tokens"),
                '{"value": "ok"}',
            ]
        ),
    )
    llm.complete_json(system="s", user="u", schema=Shape, max_tokens=99, call_site="t")

    assert client.requests[1]["max_tokens"] == 99
    assert "max_completion_tokens" not in client.requests[1]


def test_a_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    client = install(
        monkeypatch, FakeClient([Exception("503 service unavailable"), '{"value": "ok"}'])
    )
    assert llm.complete_json(system="s", user="u", schema=Shape, call_site="t").value == "ok"
    assert len(client.requests) == 2


def test_persistent_failure_raises_unavailable(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    install(monkeypatch, FakeClient([Exception("boom")] * llm.MAX_ATTEMPTS))
    with pytest.raises(LLMUnavailableError):
        llm.complete_json(system="s", user="u", schema=Shape, call_site="t")


# ---------------------------------------------------------------------------
# JSON handling
# ---------------------------------------------------------------------------


def test_fenced_json_is_tolerated(monkeypatch):
    install(monkeypatch, FakeClient(['```json\n{"value": "fenced"}\n```']))
    assert llm.complete_json(system="s", user="u", schema=Shape, call_site="t").value == "fenced"


def test_invalid_json_gets_one_repair_round_trip(monkeypatch):
    client = install(monkeypatch, FakeClient(["not json at all", '{"value": "fixed"}']))
    result = llm.complete_json(system="s", user="u", schema=Shape, call_site="t")

    assert result.value == "fixed"
    assert len(client.requests) == 2
    assert "did not validate" in client.requests[1]["messages"][1]["content"]


def test_json_that_never_validates_raises_rather_than_guessing(monkeypatch):
    install(monkeypatch, FakeClient(["nope", "still nope"]))
    with pytest.raises(LLMResponseInvalidError):
        llm.complete_json(system="s", user="u", schema=Shape, call_site="t")


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


def test_a_successful_call_is_recorded_once(monkeypatch):
    install(monkeypatch, FakeClient(['{"value": "ok"}']))
    llm.complete_json(system="s", user="u", schema=Shape, call_site="phase.one")

    assert len(llm.ledger()) == 1
    entry = llm.ledger()[0]
    assert entry.call_site == "phase.one"
    assert entry.model == llm.PRIMARY_MODEL
    assert entry.outcome is llm.Outcome.OK
    assert entry.total_tokens == 18


def test_a_repaired_call_is_one_row_that_says_so(monkeypatch):
    install(monkeypatch, FakeClient(["bad", '{"value": "ok"}']))
    llm.complete_json(system="s", user="u", schema=Shape, call_site="phase.two")

    assert len(llm.ledger()) == 1
    entry = llm.ledger()[0]
    assert entry.outcome is llm.Outcome.REPAIRED
    assert entry.total_tokens == 36  # both round-trips counted


def test_a_failed_call_is_recorded_as_failed(monkeypatch):
    install(monkeypatch, FakeClient(["nope", "nope"]))
    with pytest.raises(LLMResponseInvalidError):
        llm.complete_json(system="s", user="u", schema=Shape, call_site="phase.three")

    assert llm.ledger()[0].outcome is llm.Outcome.FAILED


def test_the_ledger_never_holds_prompts_or_completions(monkeypatch):
    """It is rendered on screen. Nothing sensitive may be in it."""
    install(monkeypatch, FakeClient(['{"value": "SECRET-COMPLETION"}']))
    llm.complete_json(
        system="SYSTEM-PROMPT-TEXT", user="USER-PROMPT-TEXT", schema=Shape, call_site="t"
    )

    blob = repr(llm.ledger())
    assert "SYSTEM-PROMPT-TEXT" not in blob
    assert "USER-PROMPT-TEXT" not in blob
    assert "SECRET-COMPLETION" not in blob


def test_a_skipped_call_is_visible_rather_than_silent():
    llm.record_skipped("somewhere", llm.Tier.FAST, "no API key")
    entry = llm.ledger()[0]
    assert entry.outcome is llm.Outcome.NOT_CONFIGURED
    assert entry.model == ""


def test_calls_since_attributes_calls_to_one_run(monkeypatch):
    install(monkeypatch, FakeClient(['{"value": "a"}', '{"value": "b"}']))
    llm.complete_json(system="s", user="u", schema=Shape, call_site="before")
    marker = llm.ledger_marker()
    llm.complete_json(system="s", user="u", schema=Shape, call_site="after")

    assert [c.call_site for c in llm.calls_since(marker)] == ["after"]


def test_the_ledger_is_bounded(monkeypatch):
    for index in range(llm.LEDGER_LIMIT + 25):
        llm.record(llm.LLMCall(call_site=f"c{index}", tier="FAST"))
    assert len(llm.ledger()) == llm.LEDGER_LIMIT
