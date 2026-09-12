"""
BAAR-AAMAD — TYPED FAILURES
===========================

Implements the Anti-Failure Architecture table from the specification.

Design rule: a failure NEVER destroys the case and NEVER becomes a confident
regulatory claim. It degrades into an honest user-facing message, and where
the specification says so, into REQUIRES VERIFICATION.

    Failure                     Response
    -------------------------   ---------------------------------------------
    LLM uncertain               REQUIRES VERIFICATION + explanation
    RAG evidence insufficient   REQUIRES VERIFICATION
    Document unreadable         Ask for re-upload
    OCR fails                   Mark document unreadable
    Required document absent    Explain what is needed and why
    Information absent          Explain exactly what to provide
    Documents contradict        Show both pieces of evidence + how to correct
    Semantic comparison fails   Fall back to deterministic checks
    API temporarily fails       Recoverable; preserve case state
    Unknown document            UNSUPPORTED DOCUMENT
    Unsupported product/market  Controlled MVP message
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    pass


class BaarAamadError(Exception):
    """Base class. Carries a message safe to show a non-technical exporter."""

    #: Shown to the user. Keep it plain, specific and actionable.
    user_message: str = "Something went wrong while processing this case."

    #: True if the case can simply be re-run without data loss.
    recoverable: bool = True

    def __init__(self, detail: str = "", user_message: str | None = None) -> None:
        self.detail = detail
        if user_message:
            self.user_message = user_message
        super().__init__(detail or self.user_message)


# --- LLM / API --------------------------------------------------------------


class LLMUnavailableError(BaarAamadError):
    """Groq unreachable, rate-limited, or no suitable model resolvable."""

    user_message = (
        "The AI service is temporarily unavailable. Your export case has been "
        "preserved — please try again in a moment."
    )


class LLMResponseInvalidError(BaarAamadError):
    """Model returned output that would not validate against the contract."""

    user_message = (
        "The AI response could not be read reliably, so this item has been "
        "marked for human verification rather than guessed."
    )


class ModelNotResolvedError(LLMUnavailableError):
    """No model from the preference list is currently offered by Groq."""

    user_message = (
        "No supported AI model is currently available from the provider. "
        "Please check the model configuration."
    )


# --- Retrieval --------------------------------------------------------------


class InsufficientEvidenceError(BaarAamadError):
    """The curated corpus does not support a confident regulatory claim.

    This is not a bug. It is the system behaving correctly, and the caller
    must degrade the requirement to REQUIRES_VERIFICATION.
    """

    user_message = (
        "We could not find sufficient authoritative source material to state "
        "this requirement confidently. It has been marked for verification."
    )


class CorpusEmptyError(BaarAamadError):
    """No curated sources are loaded at all."""

    user_message = (
        "The authoritative source library is not loaded, so no requirements "
        "can be stated. Please contact the administrator."
    )


# --- Documents --------------------------------------------------------------


class DocumentUnreadableError(BaarAamadError):
    """No usable text could be recovered, by native extraction or by OCR."""

    user_message = (
        "We could not read this document. Please upload a clearer copy — a "
        "digital PDF works best."
    )


class UnsupportedDocumentError(BaarAamadError):
    """Document does not match any supported type."""

    user_message = (
        "UNSUPPORTED DOCUMENT — this file does not match any document type "
        "BAAR-AAMAD currently checks."
    )


class OCRUnavailableError(BaarAamadError):
    """OCR fallback requested but the OCR toolchain is not installed."""

    user_message = (
        "This document has no readable text layer and image reading is not "
        "available in this deployment. Please upload a digital PDF."
    )


# --- Scope ------------------------------------------------------------------


class UnsupportedScopeError(BaarAamadError):
    """No curated source covers this product, origin or destination.

    The message is built from the case and from what the corpus actually
    holds. Nothing about a particular product or market is written into this
    class: the golden demo's leather-to-Germany scenario is demo data, not a
    property of the application.
    """

    recoverable = False
    user_message = (
        "BAAR-AAMAD has no authoritative sources covering this shipment, so "
        "it cannot state the requirements that apply to it."
    )

    @classmethod
    def for_route(
        cls,
        product: str = "",
        origin: str = "",
        destination: str = "",
        covers: str = "",
    ) -> UnsupportedScopeError:
        """Say what was asked for, and what the library actually holds."""
        route = describe_route(product, origin, destination)
        message = (
            f"BAAR-AAMAD has no authoritative sources covering {route}, so it "
            "cannot state the requirements for this shipment."
        )
        if covers:
            message += f" The curated source library currently covers {covers}."
        message += (
            " Adding a product or market means curating real sources for it "
            "first — BAAR-AAMAD will not assemble requirements without them."
        )
        return cls(f"product={product!r} origin={origin!r} destination={destination!r}",
                   user_message=message)


def describe_route(product: str = "", origin: str = "", destination: str = "") -> str:
    """A readable 'X from Y to Z', skipping whatever is not known."""
    parts = []
    if product.strip():
        parts.append(product.strip())
    if origin.strip():
        parts.append(f"from {origin.strip()}")
    if destination.strip():
        parts.append(f"to {destination.strip()}")
    return " ".join(parts) or "this shipment"


# --- Pipeline ---------------------------------------------------------------


class StageFailedError(BaarAamadError):
    """A pipeline stage failed. The case is preserved and re-runnable."""

    user_message = (
        "One processing step did not complete. Your export case has been kept "
        "and you can run the check again."
    )
