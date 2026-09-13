"""
BAAR-AAMAD — LIVE INFERENCE SMOKE TEST
======================================

Answers one question honestly: does this machine actually reach
openai/gpt-oss-120b on Groq, and does it come back with usable structured
output?

    .venv\\Scripts\\python.exe scripts\\check_llm.py

SECRETS
-------
The key is read from the environment (or a local .env, which is never
committed). This script prints whether a key is PRESENT and nothing about its
value — no prefix, no suffix, no length.

Exit status is 0 only on a real round-trip. A missing key exits 2, so this can
never be mistaken in CI for a successful test.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402

from core import llm  # noqa: E402


class Probe(BaseModel):
    """A deliberately tiny contract — this tests transport, not intelligence."""

    understood: bool = Field(description="true if you received this request")
    document_types: list[str] = Field(
        default_factory=list,
        description="The trade document names present in the user message.",
    )


def main() -> int:
    print("BAAR-AAMAD — live inference check")
    print("=" * 60)

    configured = llm.is_configured()
    print(f"  GROQ_API_KEY present   : {'yes' if configured else 'NO'}")
    if not configured:
        print()
        print("  No key in the environment, so no live call was attempted.")
        print("  Set GROQ_API_KEY in your shell or in a local .env file, or")
        print("  add it to Streamlit Secrets for the deployed application.")
        print()
        print("  RESULT: NOT TESTED (this is not a pass).")
        return 2

    print(f"  Primary model          : {llm.PRIMARY_MODEL}")

    try:
        catalogue = sorted(llm.available_models())
    except Exception as exc:
        print(f"  Model catalogue        : FAILED — {exc}")
        print()
        print("  RESULT: FAILED")
        return 1

    print(f"  Models offered         : {len(catalogue)}")
    print(f"  Primary offered        : {'yes' if llm.PRIMARY_MODEL in catalogue else 'NO'}")

    try:
        reasoning = llm.resolve_model(llm.Tier.REASONING)
        fast = llm.resolve_model(llm.Tier.FAST)
    except Exception as exc:
        print(f"  Resolution             : FAILED — {exc}")
        print()
        print("  RESULT: FAILED")
        return 1

    print(f"  REASONING tier         : {reasoning}")
    print(f"  FAST tier              : {fast}")

    print()
    print("  Calling the model...")
    started = time.monotonic()
    try:
        result = llm.complete_json(
            system=(
                "You identify trade document names mentioned in a message. "
                "Report only names that actually appear."
            ),
            user=(
                "Our shipment file contains a Commercial Invoice and a "
                "Packing List."
            ),
            schema=Probe,
            tier=llm.Tier.REASONING,
            max_tokens=300,
            call_site="smoke_test.probe",
        )
    except Exception as exc:
        print(f"  Live call              : FAILED — {exc}")
        print()
        print("  RESULT: FAILED")
        return 1

    elapsed = int((time.monotonic() - started) * 1000)
    print(f"  Live call              : OK in {elapsed} ms")
    print(f"  Structured output      : understood={result.understood} "
          f"document_types={result.document_types}")

    print()
    print("  Ledger")
    for call in llm.ledger():
        print(
            f"    #{call.sequence} {call.call_site} [{call.tier}] "
            f"model={call.model or '-'} {call.outcome.value} "
            f"{call.latency_ms}ms tokens={call.total_tokens}"
        )

    served_by = next((c.model for c in llm.ledger() if c.model), "")
    print()
    if served_by == llm.PRIMARY_MODEL:
        print(f"  RESULT: PASS — live inference on {served_by}")
    else:
        print(f"  RESULT: PASS, BUT SERVED BY A FALLBACK MODEL ({served_by})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
