"""
BAAR-AAMAD — GROQ GATEWAY
=========================

Every LLM call in this application goes through this module. No team module
imports `groq` directly. That gives us one place for model resolution, JSON
validation, retries, and failure typing.

MODEL RESOLUTION
----------------
We do NOT hard-code a model ID. Groq's lineup changes: the Llama chat models
(llama-3.1-8b-instant, llama-3.3-70b-versatile) were deprecated on
2026-06-17 and stopped being callable on 2026-08-16, so any code that pinned
them is now broken.

Instead, `resolve_model()` asks the live API which models exist and picks the
first entry from an ordered preference list. If Groq's catalogue shifts again
mid-hackathon, the app keeps working.

Note: `openai/gpt-oss-*` are OPEN-WEIGHT models hosted on Groq. Using them
does not involve the OpenAI API and requires no OpenAI account.

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
    )
"""

from __future__ import annotations

import json
import logging
import os
import time
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


#: Ordered preference per tier. The first one the API actually offers wins.
#: Checked against Groq's catalogue on 2026-09-12. The deprecated Llama chat
#: models are intentionally absent. Add new IDs to the FRONT of a list.
MODEL_PREFERENCES: dict[Tier, list[str]] = {
    Tier.REASONING: [
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-20b",
    ],
    Tier.FAST: [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "qwen/qwen3.6-27b",
    ],
}

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
    report: dict[str, Any] = {"configured": is_configured()}
    if not report["configured"]:
        report["error"] = "GROQ_API_KEY not set"
        return report
    try:
        report["available"] = sorted(available_models())
        report["reasoning"] = resolve_model(Tier.REASONING)
        report["fast"] = resolve_model(Tier.FAST)
    except Exception as exc:
        report["error"] = str(exc)
    return report


def reset_cache() -> None:
    """Clear resolution caches. Used by tests and by the UI refresh button."""
    global _available_cache
    _available_cache = None
    _resolved_cache.clear()


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def complete(
    system: str,
    user: str,
    tier: Tier = Tier.FAST,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> str:
    """Raw text completion with bounded retry on transient failures."""
    model = resolve_model(tier)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _client().chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except LLMUnavailableError:
            raise
        except Exception as exc:
            last = exc
            log.warning(
                "Groq call failed (attempt %s/%s): %s", attempt, MAX_ATTEMPTS, exc
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(0.8 * attempt)  # linear backoff; keeps the demo snappy
    raise LLMUnavailableError(f"after {MAX_ATTEMPTS} attempts: {last}")


def complete_json(
    system: str,
    user: str,
    schema: type[T],
    tier: Tier = Tier.FAST,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> T:
    """Completion validated against a pydantic model.

    One repair attempt is made if the first response does not validate. If it
    still fails we raise LLMResponseInvalidError, and the caller must degrade
    to REQUIRES VERIFICATION. We never return partial data dressed up as a
    confident answer.
    """
    contract = json.dumps(schema.model_json_schema(), indent=2)
    system_with_schema = (
        f"{system}\n\n"
        "Respond with a single JSON object and nothing else. It must validate "
        f"against this JSON Schema:\n{contract}\n"
        "If you cannot determine a value from the information given, use null "
        "or an empty list. Never invent facts, regulations, sources or URLs."
    )

    raw = complete(
        system=system_with_schema,
        user=user,
        tier=tier,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )

    try:
        return schema.model_validate_json(_strip_fences(raw))
    except (ValidationError, ValueError) as first_error:
        log.warning("JSON validation failed; attempting one repair: %s", first_error)
        error_text = str(first_error)

    repair_prompt = (
        f"Your previous response did not validate.\n\n"
        f"Response:\n{raw}\n\n"
        f"Validation error:\n{error_text}\n\n"
        "Return the corrected JSON object only."
    )
    try:
        repaired = complete(
            system=system_with_schema,
            user=repair_prompt,
            tier=tier,
            temperature=0.0,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return schema.model_validate_json(_strip_fences(repaired))
    except (ValidationError, ValueError) as second_error:
        raise LLMResponseInvalidError(
            f"schema={schema.__name__} error={second_error}"
        ) from second_error


def _strip_fences(text: str) -> str:
    """Tolerate ```json fenced output even though we asked for bare JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()
