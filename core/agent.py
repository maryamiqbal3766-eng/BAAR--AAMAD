"""
BAAR-AAMAD — THE BOUNDED AGENT
==============================

    PLAN -> USE TOOL -> OBSERVE -> DECIDE -> ACT / VERIFY

ONE loop. Not a framework, not a crew of agents, not a planner that writes its
own tools. The model is shown the case and a fixed menu of checks, it picks
one, Python runs it, the result goes back, and the model decides whether it
needs to look at anything else.

WHY THIS IS SAFE, STRUCTURALLY
------------------------------
The agent cannot weaken a verdict, because it does not produce one.

After this loop finishes — however it finishes, whether the model stopped
early, ran out of steps, chose nothing useful, or failed outright — the
orchestrator runs the FULL deterministic validation pass over every
requirement, exactly as it did before this module existed. That pass is what
builds the findings, and it is not conditional on anything the agent did.

So the agent's influence on the outcome is bounded at zero by construction.
What it adds is investigation and an account of it: which checks were looked
at, in what order, what each showed, and what the model decided to do next.
That account is what the AI Activity view renders, and it is the difference
between an agent and a log line claiming there was one.

The alternative design — letting the agent's results BE the validation, with
Python backfilling whatever it skipped — was rejected. It makes the safety
property a thing you have to audit rather than a thing you can see.

HARD LIMITS
-----------
Every one of these is enforced in Python, not requested in a prompt:

    MAX_STEPS         turns of the loop, total, per run
    MAX_LLM_CALLS     model calls, total, per run
    TOOLS             the only callable names; anything else is refused
    argument checking every argument is validated against this case before a
                      tool runs — no inventing a document type, a field or a
                      requirement that is not there

A refused tool call is not an error. It becomes an observation, goes back to
the model, and the loop continues. That is what "bounded" means: the model may
ask for anything, and only permitted things happen.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from core.schemas import (
    AgentDecision,
    AgentStep,
    DocumentType,
    ExportCase,
    StepOrigin,
)

log = logging.getLogger(__name__)

#: Turns of the loop.
#:
#: Measured at 8: the model used every step, never chose `finish`, and the
#: loop alone cost ~9,100 tokens and ~18s of a 52s run — while the last four
#: steps established nothing the first four had not. Each turn resends the
#: whole observation history, so cost grows faster than value.
#:
#: Four is enough to show a real loop — look at the documents, compare a
#: field, run the checks, stop — and keeps the wait watchable. Raise it only
#: with a measurement in hand.
MAX_STEPS = 4

#: Model calls per run. One per step, plus headroom for a repair round-trip.
#: The loop stops on whichever limit is reached first.
MAX_LLM_CALLS = 6

#: How much of a tool's output goes back to the model, per observation.
OBSERVATION_LIMIT = 900


# ---------------------------------------------------------------------------
# The tool menu
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: tuple[str, ...] = ()
    #: True when running it produces deterministic check results. Those results
    #: are shown to the model as observations; the authoritative copy is
    #: produced by the validation pass afterwards.
    is_check: bool = False


TOOLS: dict[str, Tool] = {
    "list_documents": Tool(
        name="list_documents",
        description=(
            "List every document attached to this case: its type, whether it "
            "could be read, and how many fields were extracted from it."
        ),
    ),
    "read_document_fields": Tool(
        name="read_document_fields",
        description=(
            "Show the field values extracted from one document, so you can see "
            "what it actually states."
        ),
        arguments=("document_type",),
    ),
    "run_requirement_checks": Tool(
        name="run_requirement_checks",
        description=(
            "Run the deterministic checks curated for one requirement and see "
            "what they found. This is the main way to investigate a "
            "requirement."
        ),
        arguments=("requirement_id",),
        is_check=True,
    ),
    "compare_field_across_documents": Tool(
        name="compare_field_across_documents",
        description=(
            "Compare one field's value across the documents that state it, to "
            "look for a disagreement no curated check covers."
        ),
        arguments=("field", "document_types"),
    ),
    "finish": Tool(
        name="finish",
        description=(
            "Stop. Use this once you have looked at what matters, or when no "
            "remaining tool would tell you anything new."
        ),
        arguments=("reason",),
    ),
}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


class ToolRefused(Exception):
    """The model asked for something this case does not have."""


def _document(case: ExportCase, raw: str) -> DocumentType:
    try:
        document_type = DocumentType(raw.strip().upper())
    except ValueError:
        raise ToolRefused(
            f"{raw!r} is not a document type. Available: "
            + ", ".join(d.document_type.value for d in case.documents)
        ) from None
    if case.document(document_type) is None:
        raise ToolRefused(f"no {document_type.value} is attached to this case")
    return document_type


def _tool_list_documents(case: ExportCase, args: dict[str, str]) -> str:
    if not case.documents:
        return "No documents are attached to this case."
    lines = []
    for document in case.documents:
        state = "readable" if document.readable else "UNREADABLE"
        lines.append(
            f"- {document.document_type.value} ({document.filename}): {state}, "
            f"{len(document.fields)} field(s) extracted"
        )
    return "\n".join(lines)


def _tool_read_document_fields(case: ExportCase, args: dict[str, str]) -> str:
    document_type = _document(case, args.get("document_type", ""))
    document = case.document(document_type)
    if document is None or not document.readable:
        return f"{document_type.value} could not be read, so it states nothing."
    if not document.fields:
        return f"No fields could be extracted from the {document_type.value}."
    return "\n".join(
        f"- {name}: {field_value.value}"
        for name, field_value in sorted(document.fields.items())
    )


def _tool_run_requirement_checks(case: ExportCase, args: dict[str, str]) -> str:
    from modules.requirements import source_requirement_for
    from modules.validation import run_checks

    requirement_id = args.get("requirement_id", "").strip()
    known = [r.requirement_id for r in case.requirements]
    if requirement_id not in known:
        raise ToolRefused(
            f"{requirement_id!r} is not a requirement on this case. "
            f"Available: {', '.join(known)}"
        )

    source_requirement = source_requirement_for(requirement_id)
    if source_requirement is None:
        raise ToolRefused(f"{requirement_id} has no curated checks to run")
    if not source_requirement.checks:
        return (
            f"{requirement_id} has no check that can be settled from documents. "
            "It is handled as requiring human verification."
        )

    # use_ai=False: a semantic comparison inside a tool call would be a second,
    # unbounded model call hiding inside this one.
    results = run_checks(case, source_requirement, use_ai=False)
    lines = []
    for result in results:
        if result.passed is True:
            verdict = "PASSED"
        elif result.passed is False:
            verdict = "FAILED"
        else:
            verdict = "UNDETERMINED"
        lines.append(f"- {verdict}: {result.description} — {result.detail}")
    return "\n".join(lines)


def _tool_compare_field(case: ExportCase, args: dict[str, str]) -> str:
    field_name = args.get("field", "").strip()
    if not field_name:
        raise ToolRefused("no field was named")

    raw_types = args.get("document_types", "")
    wanted = [part for part in raw_types.replace(";", ",").split(",") if part.strip()]
    if len(wanted) < 2:
        raise ToolRefused("name at least two document types to compare")

    stated: dict[str, str] = {}
    for raw in wanted:
        document_type = _document(case, raw)
        document = case.document(document_type)
        value = document.get(field_name) if document and document.readable else None
        if value:
            stated[document_type.value] = value

    if len(stated) < 2:
        return (
            f"Fewer than two of those documents state {field_name!r}, so there "
            "is nothing to compare."
        )

    values = set(stated.values())
    listing = "; ".join(f"{key}: {value}" for key, value in sorted(stated.items()))
    if len(values) == 1:
        return f"All of them state the same {field_name} — {listing}."
    return f"These documents disagree on {field_name} — {listing}."


def _tool_finish(case: ExportCase, args: dict[str, str]) -> str:
    return args.get("reason", "").strip() or "Investigation complete."


RUNNERS: dict[str, Callable[[ExportCase, dict[str, str]], str]] = {
    "list_documents": _tool_list_documents,
    "read_document_fields": _tool_read_document_fields,
    "run_requirement_checks": _tool_run_requirement_checks,
    "compare_field_across_documents": _tool_compare_field,
    "finish": _tool_finish,
}


def execute(case: ExportCase, tool: str, arguments: dict[str, str]) -> str:
    """Run one tool. Refusals come back as text, never as an exception."""
    runner = RUNNERS.get(tool)
    if runner is None:
        return (
            f"REFUSED: {tool!r} is not an available tool. Available: "
            + ", ".join(TOOLS)
        )
    try:
        return runner(case, arguments)[:OBSERVATION_LIMIT]
    except ToolRefused as refusal:
        return f"REFUSED: {refusal}"
    except Exception as exc:  # a tool must never take the pipeline down
        log.warning("agent tool %s raised: %s", tool, exc)
        return f"REFUSED: {tool} could not be run on this case."


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


SYSTEM = """\
You are investigating one export case to decide what has been checked and what \
still needs looking at. You work one step at a time: choose a single tool, see \
what it returns, then choose the next.

Rules:
- Choose exactly one tool per turn, from the menu given. Nothing else exists.
- Base every choice on what you have already observed this run.
- You are investigating, not deciding. Do not state whether the exporter \
complies, and do not state any legal conclusion. Deterministic checks decide \
that afterwards, and they run whatever you do.
- If a tool is REFUSED, read why and choose differently. Do not repeat it.
- Prefer a tool that would tell you something you do not already know.
- Call finish as soon as further tools would add nothing.
- In looking_for, give ONE short line naming what you are trying to establish. \
Not your reasoning — just the question this step answers.\
"""


def _menu() -> str:
    lines = []
    for tool in TOOLS.values():
        arguments = ", ".join(tool.arguments) or "no arguments"
        lines.append(f"- {tool.name}({arguments}): {tool.description}")
    return "\n".join(lines)


def _case_briefing(case: ExportCase) -> str:
    profile = case.profile
    lines = [
        "EXPORT CASE",
        f"  Goods: {profile.product_raw if profile else 'not stated'}",
        f"  Origin: {(profile.origin_country if profile else '') or 'not stated'}",
        f"  Destination: {(profile.destination if profile else '') or 'not stated'}",
        "",
        "REQUIREMENTS FOUND FOR THIS CASE",
    ]
    for requirement in case.requirements:
        lines.append(f"  - {requirement.requirement_id}: {requirement.title}")
    lines.append("")
    lines.append("DOCUMENTS ATTACHED")
    if case.documents:
        for document in case.documents:
            lines.append(f"  - {document.document_type.value} ({document.filename})")
    else:
        lines.append("  - none")
    return "\n".join(lines)


def _history(steps: list[AgentStep]) -> str:
    if not steps:
        return "Nothing has been observed yet. This is your first step."
    lines = []
    for step in steps:
        arguments = ", ".join(f"{k}={v}" for k, v in step.arguments.items())
        lines.append(
            f"Step {step.step}: {step.tool}({arguments})\nObserved: {step.observation}"
        )
    return "\n\n".join(lines)


@dataclass
class Investigation:
    """What one run of the loop did."""

    steps: list[AgentStep] = field(default_factory=list)
    llm_calls: int = 0
    stopped_because: str = ""

    @property
    def ran(self) -> bool:
        return bool(self.steps)


def investigate(case: ExportCase) -> Investigation:
    """Run the loop over one case. Never raises.

    Returns whatever was observed before it stopped. A failure part-way
    through is a shorter investigation, not a failed pipeline — the
    deterministic pass that follows does not depend on any of this.
    """
    from core import llm

    investigation = Investigation()

    if not case.requirements:
        investigation.stopped_because = "there were no requirements to investigate"
        return investigation

    if not llm.is_configured():
        llm.record_skipped(
            "agent.plan_step",
            llm.Tier.REASONING,
            "no API key; the deterministic checks run on their own",
        )
        investigation.stopped_because = (
            "the AI service is not configured, so no agent steps were planned"
        )
        return investigation

    from pydantic import BaseModel, Field

    class Move(BaseModel):
        tool: str = ""
        arguments: dict[str, str] = Field(default_factory=dict)
        looking_for: str = ""

    briefing = _case_briefing(case)

    while len(investigation.steps) < MAX_STEPS:
        if investigation.llm_calls >= MAX_LLM_CALLS:
            investigation.stopped_because = (
                f"the model call limit ({MAX_LLM_CALLS}) was reached"
            )
            break

        user = (
            f"{briefing}\n\nAVAILABLE TOOLS\n{_menu()}\n\n"
            f"WHAT YOU HAVE OBSERVED SO FAR\n{_history(investigation.steps)}\n\n"
            f"You have {MAX_STEPS - len(investigation.steps)} step(s) left. "
            "Choose the next single tool."
        )

        try:
            investigation.llm_calls += 1
            move = llm.complete_json(
                system=SYSTEM,
                user=user,
                schema=Move,
                tier=llm.Tier.REASONING,
                max_tokens=600,
                call_site="agent.plan_step",
            )
        except Exception as exc:
            log.warning("agent step could not be planned: %s", exc)
            investigation.stopped_because = (
                "the AI service stopped responding part-way through"
            )
            break

        tool = (move.tool or "").strip()
        arguments = {str(k): str(v) for k, v in (move.arguments or {}).items()}
        observation = execute(case, tool, arguments)
        finished = tool == "finish"

        # Mark the step BEFORE this one as continued: the model saw its
        # observation and asked for another tool, which is the decision.
        if investigation.steps:
            investigation.steps[-1].decision = AgentDecision.CONTINUE

        investigation.steps.append(
            AgentStep(
                step=len(investigation.steps) + 1,
                tool=tool or "(none)",
                arguments=arguments,
                observation=observation,
                decision=AgentDecision.STOP,
                rationale=move.looking_for.strip()[:200],
                chosen_by=StepOrigin.MODEL,
            )
        )

        if finished:
            investigation.stopped_because = "the model decided it had seen enough"
            break
    else:
        investigation.stopped_because = f"the step limit ({MAX_STEPS}) was reached"

    return investigation
