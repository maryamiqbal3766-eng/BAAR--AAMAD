"""
BAAR-AAMAD — GROQ GATEWAY
=========================

Every LLM call in this application goes through this module. No team module
imports `groq` directly. That gives us one place for model resolution, JSON
validation, retries, and failure typing.

MODEL RESOLUTION
----------------
`openai/gpt-oss-120b` is THE model for this application, named as such in the
PRD, and it serves BOTH tiers. One identifiable model means an observer can
tell exactly what produced every AI output, with no ambiguity about which
model did what.

We still do not hard-code it as the only possibility. `resolve_model()` asks
the live API which models exist and takes the first entry of an ordered
preference list, so a Groq catalogue change — the Llama chat models were
deprecated on 2026-06-17 and stopped being callable on 2026-08-16 — degrades
to a working fallback instead of a dead application. The ledger below records
which model actually served each call, so a fallback is visible rather than
silent.

Note: `openai/gpt-oss-*` are OPEN-WEIGHT models hosted on Groq. Using them
does not involve the OpenAI API and requires no OpenAI account.

THE CALL LEDGER
---------------
Every call through this module is recorded: call site, tier, the model that
actually served it, latency, token usage and outcome. That record is what the
AI Activity view reads. It holds no prompt bodies, no completions and no
reasoning content — see `reasoning_format` below.

USAGE
-----
    from pydantic import BaseModel
    from core.llm import Tier, complete_json

    class Out(BaseModel):
        product_normalized: str

    result = complete_json(
        system="You normalize product descriptions.",
        user="handmade leather satchels",
        schema=Out,
        tier=Tier.FAST,
        call_site="profile.describe_product",
    )
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import (
    LLMResponseInvalidError,
    LLMUnavailableError,
    ModelNotResolvedError,
)

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class Tier(str, Enum):
    """Which class of model a call needs.

    REASONING — requirement interpretation, semantic comparison, explanation.
    FAST      — classification, field extraction, short structured outputs.
    """

    REASONING = "REASONING"
    FAST = "FAST"


#: The model this application is built on, for every tier.
PRIMARY_MODEL = "openai/gpt-oss-120b"

#: Ordered preference per tier. The first one the API actually offers wins.
#: Checked against Groq's catalogue on 2026-09-12. The deprecated Llama chat
#: models are intentionally absent.
#:
#: BOTH TIERS LEAD WITH THE SAME MODEL, deliberately. The tiers still exist
#: because they express what a call needs, and the entries after the first are
#: availability insurance only — never a routine second model. If a fallback
#: ever serves a call, the ledger says so.
MODEL_PREFERENCES: dict[Tier, list[str]] = {
    Tier.REASONING: [PRIMARY_MODEL, "openai/gpt-oss-20b"],
    Tier.FAST: [PRIMARY_MODEL, "openai/gpt-oss-20b"],
}

#: Model families that emit separate reasoning content. For these we set
#: `reasoning_format="hidden"` so chain-of-thought never reaches `content`,
#: never reaches the ledger and never reaches a user. TS-2 is enforced at the
#: gateway rather than asked for in a prompt.
_REASONING_MODEL_PREFIXES = ("openai/gpt-oss",)

#: Env overrides, for when someone wants to pin a model deliberately.
_ENV_OVERRIDE = {
    Tier.REASONING: "BAAR_MODEL_REASONING",
    Tier.FAST: "BAAR_MODEL_FAST",
}

DEFAULT_TIMEOUT_S = 60
MAX_ATTEMPTS = 3

_available_cache: set[str] | None = None
_resolved_cache: dict[Tier, str] = {}
_dotenv_loaded = False


# ---------------------------------------------------------------------------
# The call ledger
# ---------------------------------------------------------------------------
#
# What this records and what it deliberately does not:
#
#   RECORDED   which call site fired, which tier it asked for, which model
#              actually answered, how long it took, tokens in and out, and how
#              it ended (ok / repaired / failed / not configured).
#
#   NOT RECORDED
#              prompts, completions, reasoning content, and the API key. The
#              ledger is rendered in the UI, so anything in it is public to
#              whoever is looking at the screen.


class Outcome(str, Enum):
    OK = "OK"  # validated first time
    REPAIRED = "REPAIRED"  # needed the one repair round-trip
    FAILED = "FAILED"  # gave up; the caller fell back to deterministic
    NOT_CONFIGURED = "NOT CONFIGURED"  # no key; the call never left the process


@dataclass
class LLMCall:
    """One recorded call through this gateway."""

    call_site: str
    tier: str
    model: str = ""
    outcome: Outcome = Outcome.OK
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1
    detail: str = ""
    sequence: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


#: Bounded so a long session cannot grow without limit.
LEDGER_LIMIT = 500

_ledger: list[LLMCall] = []
_ledger_lock = threading.Lock()
_sequence = 0


def record(call: LLMCall) -> LLMCall:
    """Append one call to the ledger. Never raises — telemetry is not a feature
    the pipeline may fail on."""
    global _sequence
    with _ledger_lock:
        _sequence += 1
        call.sequence = _sequence
        _ledger.append(call)
        if len(_ledger) > LEDGER_LIMIT:
            del _ledger[: len(_ledger) - LEDGER_LIMIT]
    return call


def ledger() -> list[LLMCall]:
    """Every call recorded in this process, oldest first."""
    with _ledger_lock:
        return list(_ledger)


def ledger_marker() -> int:
    """A point in the ledger, so a caller can ask what happened after it."""
    with _ledger_lock:
        return _sequence


def calls_since(marker: int) -> list[LLMCall]:
    """Calls recorded after `marker`. Used to attribute calls to one run."""
    return [call for call in ledger() if call.sequence > marker]


def clear_ledger() -> None:
    global _sequence
    with _ledger_lock:
        _ledger.clear()
        _sequence = 0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _load_dotenv_once() -> None:
    """Pull a local .env into the environment, exactly once per process.

    Local development uses .env; Streamlit Community Cloud uses secrets. We
    never override a variable that is already set, so an explicitly exported
    key always wins over the file.
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:  # python-dotenv is optional
        pass


def api_key() -> str | None:
    """Read the key from .env / environment, then Streamlit secrets.

    Never hard-coded, never logged, never written into the case.
    """
    _load_dotenv_once()

    key = os.environ.get("GROQ_API_KEY")
    if key and key.strip():
        return key.strip()

    try:  # Streamlit is absent in Colab experiments and in unit tests
        import streamlit as st

        secret = str(st.secrets["GROQ_API_KEY"]).strip()
        return secret or None
    except Exception:
        return None


def is_configured() -> bool:
    return bool(api_key())


def _client():
    key = api_key()
    if not key:
        raise LLMUnavailableError(
            "GROQ_API_KEY is not set",
            user_message=(
                "The AI service is not configured yet. Add GROQ_API_KEY to "
                "your .env file or to Streamlit secrets."
            ),
        )
    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailableError(f"groq package not installed: {exc}") from exc
    return Groq(api_key=key, timeout=DEFAULT_TIMEOUT_S)


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


def available_models(refresh: bool = False) -> set[str]:
    """Ask Groq which models are currently callable. Cached per process."""
    global _available_cache
    if _available_cache is not None and not refresh:
        return _available_cache
    try:
        listing = _client().models.list()
        _available_cache = {m.id for m in listing.data}
        log.info("Groq models available: %s", sorted(_available_cache))
    except LLMUnavailableError:
        raise
    except Exception as exc:
        raise LLMUnavailableError(f"could not list models: {exc}") from exc
    return _available_cache


def resolve_model(tier: Tier, refresh: bool = False) -> str:
    """Pick the best currently-available model for a tier.

    Honours BAAR_MODEL_REASONING / BAAR_MODEL_FAST when set, without checking
    availability first — an explicit pin is treated as deliberate.
    """
    override = os.environ.get(_ENV_OVERRIDE[tier], "").strip()
    if override:
        return override

    if not refresh and tier in _resolved_cache:
        return _resolved_cache[tier]

    offered = available_models(refresh=refresh)
    for candidate in MODEL_PREFERENCES[tier]:
        if candidate in offered:
            _resolved_cache[tier] = candidate
            log.info("Resolved %s tier to %s", tier.value, candidate)
            return candidate

    raise ModelNotResolvedError(
        f"none of {MODEL_PREFERENCES[tier]} are offered; available: {sorted(offered)}"
    )


def resolution_report() -> dict[str, Any]:
    """Diagnostic for the UI status panel. Never raises."""
    report: dict[str, Any] = {
        "configured": is_configured(),
        "primary": PRIMARY_MODEL,
    }
    if not report["configured"]:
        report["error"] = "GROQ_API_KEY not set"
        return report
    try:
        report["available"] = sorted(available_models())
        report["reasoning"] = resolve_model(Tier.REASONING)
        report["fast"] = resolve_model(Tier.FAST)
        report["on_primary"] = (
            report["reasoning"] == PRIMARY_MODEL and report["fast"] == PRIMARY_MODEL
        )
    except Exception as exc:
        report["error"] = str(exc)
    return report


def record_skipped(call_site: str, tier: Tier, reason: str) -> None:
    """Note a call site that chose not to call, so the absence is visible.

    A stage that quietly did nothing because there was no API key looks
    identical, in a UI, to a stage that was never reached. This makes the
    deterministic fallback an observable event rather than a silence.
    """
    record(
        LLMCall(
            call_site=call_site,
            tier=tier.value,
            outcome=Outcome.NOT_CONFIGURED,
            detail=reason,
        )
    )


def reset_cache() -> None:
    """Clear resolution caches. Used by tests and by the UI refresh button."""
    global _available_cache
    _available_cache = None
    _resolved_cache.clear()


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


@dataclass
class _Response:
    """What one round-trip produced, before the caller sees only the text."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1


def _is_unsupported_parameter(exc: Exception, parameter: str) -> bool:
    """Did Groq reject the request because of this specific parameter?

    We send `reasoning_format` and `max_completion_tokens` because they are
    correct for gpt-oss. A different model, or an older API surface, may not
    know them. Rather than pinning to whatever is true today, we notice the
    rejection and retry without the parameter.
    """
    message = str(exc).lower()
    if parameter.lower() not in message:
        return False
    return any(
        marker in message
        for marker in ("unsupported", "unrecognized", "unknown", "not supported", "invalid")
    )


def _raw_complete(
    system: str,
    user: str,
    tier: Tier,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> _Response:
    """One completion with bounded retry. Returns the text and its metadata."""
    model = resolve_model(tier)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        # The current spelling. `max_tokens` is the deprecated alias, and we
        # fall back to it below if this one is refused.
        "max_completion_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if model.startswith(_REASONING_MODEL_PREFIXES):
        # Keep the model's reasoning out of `content` entirely. Not a prompt
        # instruction — a transport setting, so nothing downstream has to
        # strip anything.
        kwargs["reasoning_format"] = "hidden"

    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _client().chat.completions.create(**kwargs)
            usage = getattr(response, "usage", None)
            return _Response(
                text=response.choices[0].message.content or "",
                model=getattr(response, "model", model) or model,
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                attempts=attempt,
            )
        except LLMUnavailableError:
            raise
        except Exception as exc:
            # An unsupported optional parameter is a configuration mismatch,
            # not a transient failure: drop it and try again straight away
            # rather than burning the backoff on a request that cannot work.
            dropped = False
            for parameter in ("reasoning_format", "max_completion_tokens"):
                if parameter in kwargs and _is_unsupported_parameter(exc, parameter):
                    log.info("Groq rejected %s; retrying without it", parameter)
                    del kwargs[parameter]
                    if parameter == "max_completion_tokens":
                        kwargs["max_tokens"] = max_tokens
                    dropped = True
            if dropped:
                continue

            last = exc
            log.warning(
                "Groq call failed (attempt %s/%s): %s", attempt, MAX_ATTEMPTS, exc
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(0.8 * attempt)  # linear backoff; keeps the demo snappy

    raise LLMUnavailableError(f"after {MAX_ATTEMPTS} attempts: {last}")


def complete(
    system: str,
    user: str,
    tier: Tier = Tier.FAST,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    json_mode: bool = False,
    call_site: str = "unattributed",
    _record: bool = True,
) -> str:
    """Raw text completion with bounded retry on transient failures.

    `_record` is False when the caller writes its own aggregate ledger row —
    `complete_json` does, so a repair round-trip shows as one call that needed
    repairing rather than as two unrelated calls.
    """
    started = time.monotonic()
    try:
        response = _raw_complete(system, user, tier, temperature, max_tokens, json_mode)
    except Exception as exc:
        if _record:
            record(
                LLMCall(
                    call_site=call_site,
                    tier=tier.value,
                    model=_resolved_cache.get(tier, ""),
                    outcome=(
                        Outcome.NOT_CONFIGURED if not is_configured() else Outcome.FAILED
                    ),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    detail=str(exc)[:200],
                )
            )
        raise

    if _record:
        record(
            LLMCall(
                call_site=call_site,
                tier=tier.value,
                model=response.model,
                outcome=Outcome.OK,
                latency_ms=int((time.monotonic() - started) * 1000),
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                attempts=response.attempts,
            )
        )
    return response.text


def complete_json(
    system: str,
    user: str,
    schema: type[T],
    tier: Tier = Tier.FAST,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    call_site: str = "unattributed",
) -> T:
    """Completion validated against a pydantic model.

    One repair attempt is made if the first response does not validate. If it
    still fails we raise LLMResponseInvalidError, and the caller must degrade
    to REQUIRES VERIFICATION. We never return partial data dressed up as a
    confident answer.

    Exactly one ledger row is written per call, whether or not a repair was
    needed — the row says which.
    """
    contract = json.dumps(schema.model_json_schema(), indent=2)
    system_with_schema = (
        f"{system}\n\n"
        "Respond with a single JSON object and nothing else. It must validate "
        f"against this JSON Schema:\n{contract}\n"
        "If you cannot determine a value from the information given, use null "
        "or an empty list. Never invent facts, regulations, sources or URLs."
    )

    started = time.monotonic()
    entry = LLMCall(call_site=call_site, tier=tier.value)

    def _elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    def _absorb(response: _Response) -> None:
        entry.model = response.model
        entry.prompt_tokens += response.prompt_tokens
        entry.completion_tokens += response.completion_tokens

    try:
        first = _raw_complete(
            system_with_schema, user, tier, temperature, max_tokens, json_mode=True
        )
    except Exception as exc:
        entry.outcome = (
            Outcome.NOT_CONFIGURED if not is_configured() else Outcome.FAILED
        )
        entry.latency_ms = _elapsed()
        entry.detail = str(exc)[:200]
        entry.model = entry.model or _resolved_cache.get(tier, "")
        record(entry)
        raise

    _absorb(first)
    entry.attempts = first.attempts

    try:
        validated = schema.model_validate_json(_strip_fences(first.text))
    except (ValidationError, ValueError) as first_error:
        log.warning("JSON validation failed; attempting one repair: %s", first_error)
        error_text = str(first_error)
    else:
        entry.outcome = Outcome.OK
        entry.latency_ms = _elapsed()
        record(entry)
        return validated

    repair_prompt = (
        f"Your previous response did not validate.\n\n"
        f"Response:\n{first.text}\n\n"
        f"Validation error:\n{error_text}\n\n"
        "Return the corrected JSON object only."
    )
    try:
        second = _raw_complete(
            system_with_schema, repair_prompt, tier, 0.0, max_tokens, json_mode=True
        )
        _absorb(second)
        entry.attempts += second.attempts
        validated = schema.model_validate_json(_strip_fences(second.text))
    except (ValidationError, ValueError) as second_error:
        entry.outcome = Outcome.FAILED
        entry.latency_ms = _elapsed()
        entry.detail = f"schema {schema.__name__} did not validate after repair"
        record(entry)
        raise LLMResponseInvalidError(
            f"schema={schema.__name__} error={second_error}"
        ) from second_error
    except Exception as exc:
        entry.outcome = Outcome.FAILED
        entry.latency_ms = _elapsed()
        entry.detail = str(exc)[:200]
        record(entry)
        raise

    entry.outcome = Outcome.REPAIRED
    entry.latency_ms = _elapsed()
    record(entry)
    return validated


def _strip_fences(text: str) -> str:
    """Tolerate ```json fenced output even though we asked for bare JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()
