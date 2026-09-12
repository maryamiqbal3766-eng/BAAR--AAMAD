"""
BAAR-AAMAD — PIPELINE ORCHESTRATOR
==================================

Runs the case through its eight stages, in order, recording what each one did:

    PROFILE -> REQUIREMENTS -> DOCUMENTS -> VALIDATION
            -> FINDINGS -> REASONING -> ACTIONS -> PASSPORT

THREE PROPERTIES THIS MODULE EXISTS TO GUARANTEE

1. Idempotence. Every stage rebuilds its own output from the case rather than
   appending to it, so running twice produces the same case. That is what
   makes RECHECK a plain re-run rather than a diffing engine — the
   specification explicitly allows this for the MVP.

2. Failure never destroys a case. A stage that fails is recorded as FAILED
   with a message the exporter can read, and the pipeline stops there with
   everything earlier intact. The case is always re-runnable.

3. No stage invents. The rules in core.rules and the evidence rule in
   core.corpus hold whatever happens here; the orchestrator only sequences.

Streamlit re-executes the whole script on every interaction, so the pipeline
must never run as a side effect of rendering. It runs when asked, and the
stage records tell the UI what has already happened.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from core.errors import BaarAamadError
from core.rules import case_status_for
from core.schemas import (
    CaseStatus,
    Coverage,
    ExportCase,
    StageName,
    StageRecord,
    StageStatus,
    utcnow,
)

log = logging.getLogger(__name__)

#: Execution order. The UI reads this to draw progress.
STAGE_ORDER: list[StageName] = [
    StageName.PROFILE,
    StageName.REQUIREMENTS,
    StageName.DOCUMENTS,
    StageName.VALIDATION,
    StageName.FINDINGS,
    StageName.REASONING,
    StageName.ACTIONS,
    StageName.PASSPORT,
]

STAGE_LABELS: dict[StageName, str] = {
    StageName.PROFILE: "Understanding your product",
    StageName.REQUIREMENTS: "Finding the applicable requirements",
    StageName.DOCUMENTS: "Reading your documents",
    StageName.VALIDATION: "Checking evidence against requirements",
    StageName.FINDINGS: "Recording findings",
    StageName.REASONING: "Explaining each finding",
    StageName.ACTIONS: "Building your action plan",
    StageName.PASSPORT: "Preparing the Compliance Passport",
}


@dataclass
class StageOutcome:
    """What one stage did, for the progress display."""

    stage: StageName
    status: StageStatus
    message: str = ""


def _session_files(document_id: str) -> bytes | None:
    """Default byte source: the Streamlit session store, when there is one."""
    try:
        from core import state

        return state.file_bytes(document_id)
    except Exception:  # no Streamlit session — Colab, a unit test, a script
        return None


def _session_text_sink(document_id: str, text: str) -> None:
    try:
        from core import state

        state.set_document_text(document_id, text)
    except Exception:
        pass


@dataclass
class RunContext:
    """Everything a stage needs that is not the case itself.

    The byte source is injected rather than imported so the pipeline runs
    unchanged in Streamlit, in a plain script and in Colab. `core` must not
    require a browser session to do its work.
    """

    use_ai: bool = True
    file_provider: Callable[[str], bytes | None] = _session_files
    text_sink: Callable[[str, str], None] = _session_text_sink


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def _stage_profile(case: ExportCase, ctx: RunContext) -> str:
    from modules.profile import build_profile

    if case.profile is None:
        raise BaarAamadError(
            "no profile on case",
            user_message="This case has no product details yet.",
        )

    result = build_profile(case.profile, use_ai=ctx.use_ai)
    if not result.ok:
        # Not fatal: the case is simply outside what we can advise on, and the
        # requirements stage will say so rather than guessing.
        return result.reason
    return f"Recognised as {case.profile.product_normalized} for {case.profile.destination}."


def _stage_requirements(case: ExportCase, ctx: RunContext) -> str:
    from modules.requirements import build_requirements

    result = build_requirements(case.profile, use_ai=ctx.use_ai)
    case.requirements = result.payload.get("requirements", [])
    case.coverage = result.payload.get("coverage")

    if not result.ok:
        raise BaarAamadError("no requirements", user_message=result.reason)

    sources = result.payload.get("sources", [])
    message = (
        f"{len(case.requirements)} requirement(s) from "
        f"{len(sources)} authoritative source(s)."
    )
    # Partial coverage is a completed stage, not a failure — but it must be
    # said out loud, here and on every surface downstream.
    if case.coverage and case.coverage.level is not Coverage.COVERED:
        message += f" Coverage: {case.coverage.level.value}."
    return message


def _stage_documents(case: ExportCase, ctx: RunContext) -> str:
    """Re-read every attached document from its stored bytes.

    Re-reading rather than trusting what is already on the evidence is what
    makes RECHECK correct after a document is replaced.

    If the bytes are no longer available we KEEP whatever was read earlier
    rather than discarding it. Losing the file should not silently turn a
    document that was read into a missing one — that would manufacture a
    finding out of an infrastructure problem.
    """
    from modules.documents import read_document

    if not case.documents:
        return "No documents have been uploaded to this case."

    unreadable = 0
    reused = 0

    for document in case.documents:
        data = ctx.file_provider(document.document_id)

        if data is None:
            if document.extracted and document.readable:
                reused += 1
                continue
            document.readable = False
            document.unreadable_reason = (
                "This document is no longer available in the session. Please "
                "upload it again."
            )
            unreadable += 1
            continue

        result = read_document(document, data, use_ai=ctx.use_ai)
        ctx.text_sink(document.document_id, result.payload.get("text", ""))
        if not result.ok:
            unreadable += 1

    readable = len(case.documents) - unreadable
    message = f"{readable} of {len(case.documents)} document(s) read."
    if reused:
        message += f" {reused} used the reading from earlier in this session."
    if unreadable:
        message += f" {unreadable} could not be read."
    return message


def _stage_validation(case: ExportCase, ctx: RunContext) -> str:
    """Run both engines over the evidence and record every check.

    Assessment produces checks and findings together — a finding is the
    consolidation of its checks — so this stage writes both onto the case and
    the FINDINGS stage consolidates them. Nothing is passed between stages
    except the case itself, which is what keeps every stage re-runnable.
    """
    from modules.findings import all_checks, build_findings

    findings = build_findings(case, use_ai=ctx.use_ai)
    case.findings = findings
    case.checks = all_checks(findings)

    decided = sum(1 for check in case.checks if check.passed is not None)
    return f"{len(case.checks)} check(s) run, {decided} decided exactly."


def _stage_findings(case: ExportCase, ctx: RunContext) -> str:
    """Consolidate into the ordered findings list the rest of the app reads.

    Ordering is by priority band, so the exporter is never handed ten problems
    in arbitrary order. This is the single source of truth from here on.
    """
    from core.rules import priority_rank

    case.findings.sort(key=lambda f: (priority_rank(f.priority), f.requirement_id))
    status = case_status_for(case.findings)
    return f"{len(case.findings)} finding(s). Case status: {status.value}."


def _stage_reasoning(case: ExportCase, ctx: RunContext) -> str:
    from modules.reasoning import build_traces

    case.reasoning = build_traces(case, use_ai=ctx.use_ai)
    return f"{len(case.reasoning)} explanation(s) prepared."


def _stage_actions(case: ExportCase, ctx: RunContext) -> str:
    from modules.actions import build_action_plan, build_checklists, build_drafts

    case.action_plan = build_action_plan(case)
    case.checklists = build_checklists(case)
    case.drafts = build_drafts(case)

    parts = [f"{len(case.action_plan)} action(s)"]
    if case.checklists:
        parts.append(f"{len(case.checklists)} checklist(s)")
    if case.drafts:
        parts.append(f"{len(case.drafts)} draft(s)")
    return ", ".join(parts) + "."


def _stage_passport(case: ExportCase, ctx: RunContext) -> str:
    from modules.passport import build_passport

    case.passport = build_passport(case)
    return f"Passport ready. Status: {case.passport.case_status.value}."


STAGE_RUNNERS: dict[StageName, Callable[[ExportCase, RunContext], str]] = {
    StageName.PROFILE: _stage_profile,
    StageName.REQUIREMENTS: _stage_requirements,
    StageName.DOCUMENTS: _stage_documents,
    StageName.VALIDATION: _stage_validation,
    StageName.FINDINGS: _stage_findings,
    StageName.REASONING: _stage_reasoning,
    StageName.ACTIONS: _stage_actions,
    StageName.PASSPORT: _stage_passport,
}


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def reset_stages(case: ExportCase) -> None:
    """Mark every stage pending. Called at the start of a run and a recheck."""
    case.stages = {name: StageRecord(name=name) for name in STAGE_ORDER}


def run(
    case: ExportCase, use_ai: bool = True, ctx: RunContext | None = None
) -> Iterator[StageOutcome]:
    """Run the pipeline, yielding after each stage so the UI can show progress.

    Stops at the first failure, leaving everything already computed in place.
    The caller decides what to do next; the case is never discarded.
    """
    ctx = ctx or RunContext(use_ai=use_ai)
    reset_stages(case)
    case.run_number += 1

    for name in STAGE_ORDER:
        record = case.stage(name)
        record.status = StageStatus.RUNNING
        record.started_at = utcnow()

        try:
            message = STAGE_RUNNERS[name](case, ctx)
            record.status = StageStatus.COMPLETE
            record.message = message
        except BaarAamadError as exc:
            record.status = StageStatus.FAILED
            record.error = exc.user_message
            record.finished_at = utcnow()
            log.warning("stage %s failed: %s", name.value, exc.detail or exc)
            yield StageOutcome(name, StageStatus.FAILED, exc.user_message)
            return
        except Exception as exc:  # unexpected: still must not lose the case
            record.status = StageStatus.FAILED
            record.error = (
                "Something went wrong at this step. Your export case has been "
                "kept and you can run the check again."
            )
            record.finished_at = utcnow()
            log.exception("stage %s raised: %s", name.value, exc)
            yield StageOutcome(name, StageStatus.FAILED, record.error)
            return

        record.finished_at = utcnow()
        yield StageOutcome(name, StageStatus.COMPLETE, message)


def run_to_completion(
    case: ExportCase, use_ai: bool = True, ctx: RunContext | None = None
) -> list[StageOutcome]:
    """Run every stage and collect the outcomes. Used by tests and Recheck."""
    return list(run(case, use_ai=use_ai, ctx=ctx))


def recheck(
    case: ExportCase, use_ai: bool = True, ctx: RunContext | None = None
) -> list[StageOutcome]:
    """Re-run the case after the exporter has fixed something.

    Deliberately the same pipeline. Because every stage rebuilds its output,
    corrected documents flow through re-extraction, re-matching, re-validation
    and an updated Passport without any special-case code.
    """
    return run_to_completion(case, use_ai=use_ai, ctx=ctx)


def has_run(case: ExportCase) -> bool:
    return case.run_number > 0 and bool(case.findings)


def failed_stage(case: ExportCase) -> StageRecord | None:
    return next(
        (r for r in case.stages.values() if r.status is StageStatus.FAILED), None
    )


def progress(case: ExportCase) -> tuple[int, int]:
    """(completed stages, total stages) for a progress bar."""
    done = sum(
        1 for r in case.stages.values() if r.status is StageStatus.COMPLETE
    )
    return done, len(STAGE_ORDER)


def status_of(case: ExportCase) -> CaseStatus:
    return case_status_for(case.findings)
