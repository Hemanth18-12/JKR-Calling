"""P10 — real-call quality report tool. Given a `call_session_id`, prints
the turn transcript, the persisted latency waterfall, and coarse call
events for a call that has already happened. See
docs/P10_REAL_CALL_BENCHMARK.md for the full harness this tool is part of,
and specifically its "Turn waterfall: what's actually captured, honestly"
section for why some spec-requested stages (the detailed barge-in/replay
event trace) are deliberately NOT reconstructed here — they only exist in
the server's own structured logs, never in `CallEvent` rows, and this tool
says so explicitly rather than silently omitting them.

Usage:
    uv run --package jkr-db python tests/tools/real_call_quality_report.py <call_session_id>

Tested (against seeded/synthetic data in this environment — see
services/api/tests/test_real_call_quality_report.py) but NOT YET run
against a real call's data, because no real call has been placed in this
environment. Do not treat any example output in this docstring or in the
test suite as a real call result.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")

from jkr_db.models.calls import CallEvent, CallLatencyMetric, CallSession, CallTurn  # noqa: E402
from jkr_db.session import get_session, workspace_scoped_session  # noqa: E402
from sqlalchemy import select  # noqa: E402

# Every stage this codebase currently persists as a CallLatencyMetric row —
# see docs/P10_REAL_CALL_BENCHMARK.md's own "what's actually captured"
# section. Displayed in this order (roughly waterfall order) when present;
# anything found in the database but NOT in this list is still shown, just
# flagged, rather than silently dropped (spec's own "fail closed" instinct,
# applied to reporting rather than production output this time).
STAGE_ORDER = [
    "stt_transcribe", "stt_stream_finalize", "stt_stream_first_partial",
    "engine_fast_router", "engine_domain_vocabulary", "engine_extraction", "engine_planning",
    "engine_rag_embedding", "engine_rag_vector_search", "engine_rag",
    "engine_generation", "engine_llm_ttft", "engine_llm_first_speakable_chunk", "engine_llm_full_generation",
    "tts_synthesize", "tts_stream_first_audio", "turn_total_backend",
]


@dataclass
class CallReport:
    call_session_id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    end_reason: str | None
    language: str | None
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    is_mock: bool
    turns: list[dict] = field(default_factory=list)
    latency_rows: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


async def build_report(call_session_id: uuid.UUID) -> CallReport:
    """Two-phase lookup, same pattern this codebase's own test helpers
    already use for cross-tenant setup: an unscoped get_session() to find
    WHICH workspace this call belongs to (a call_session_id alone doesn't
    tell you that), then a workspace_scoped_session() for every tenant-
    owned row after that — never the reverse, since RLS requires the
    workspace context to already be set before querying tenant tables."""
    async with get_session() as db:
        result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
        call = result.scalar_one_or_none()
    if call is None:
        raise ValueError(f"No call_sessions row found with id={call_session_id}")

    async with workspace_scoped_session(call.workspace_id) as db:
        turns_result = await db.execute(
            select(CallTurn).where(CallTurn.call_session_id == call_session_id).order_by(CallTurn.sequence_index)
        )
        turns = list(turns_result.scalars().all())

        latency_result = await db.execute(
            select(CallLatencyMetric).where(CallLatencyMetric.call_session_id == call_session_id).order_by(CallLatencyMetric.recorded_at)
        )
        latency_rows = list(latency_result.scalars().all())

        events_result = await db.execute(
            select(CallEvent).where(CallEvent.call_session_id == call_session_id).order_by(CallEvent.created_at)
        )
        events = list(events_result.scalars().all())

    return CallReport(
        call_session_id=call.id,
        workspace_id=call.workspace_id,
        status=str(call.status),
        end_reason=str(call.end_reason) if call.end_reason else None,
        language=str(call.language) if call.language else None,
        started_at=call.started_at,
        answered_at=call.answered_at,
        ended_at=call.ended_at,
        duration_seconds=call.duration_seconds,
        is_mock=call.is_mock,
        turns=[
            {
                "sequence_index": t.sequence_index, "speaker": str(t.speaker), "text": t.text,
                "is_interrupted": t.is_interrupted, "started_at": t.started_at,
            }
            for t in turns
        ],
        latency_rows=[
            {"stage": r.stage, "duration_ms": r.duration_ms, "provider": r.provider, "recorded_at": r.recorded_at}
            for r in latency_rows
        ],
        events=[{"event_type": e.event_type, "payload": e.payload, "created_at": e.created_at} for e in events],
    )


def _group_latency_by_stage(rows: list[dict]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for row in rows:
        grouped.setdefault(row["stage"], []).append(row["duration_ms"])
    return grouped


def render_report(report: CallReport) -> str:
    """Pure — takes an already-built CallReport, produces the text report.
    Split from build_report() specifically so this half is unit-testable
    with zero database (see the test suite)."""
    lines: list[str] = []
    lines.append(f"=== Call {report.call_session_id} ===")
    lines.append(f"workspace_id: {report.workspace_id}")
    lines.append(f"status: {report.status}  end_reason: {report.end_reason}  language: {report.language}  is_mock: {report.is_mock}")
    lines.append(f"started_at: {report.started_at}  answered_at: {report.answered_at}  ended_at: {report.ended_at}  duration_s: {report.duration_seconds}")
    lines.append("")
    lines.append("--- Transcript ---")
    if not report.turns:
        lines.append("(no CallTurn rows found — call may not have progressed past connection, or is not yet persisted)")
    for t in report.turns:
        interrupted = " [INTERRUPTED]" if t["is_interrupted"] else ""
        lines.append(f"[{t['sequence_index']:>3}] {t['speaker']:>8}: {t['text']}{interrupted}")
    lines.append("")
    lines.append("--- Latency waterfall (grouped by stage, ms) ---")
    grouped = _group_latency_by_stage(report.latency_rows)
    if not grouped:
        lines.append("(no CallLatencyMetric rows found)")
    for stage in STAGE_ORDER:
        if stage in grouped:
            values = grouped.pop(stage)
            lines.append(f"{stage:<32} n={len(values):<3} values={values}")
    for stage, values in grouped.items():  # anything not in STAGE_ORDER — surfaced, never silently dropped
        lines.append(f"{stage:<32} n={len(values):<3} values={values}  (unrecognized stage — update STAGE_ORDER)")
    lines.append("")
    lines.append("--- Coarse call events (call_started / *_turn / call_ended only) ---")
    if not report.events:
        lines.append("(no CallEvent rows found)")
    for e in report.events:
        lines.append(f"{e['created_at']}  {e['event_type']}  {e['payload']}")
    lines.append("")
    lines.append("--- Reminder ---")
    lines.append(
        "The detailed barge-in/replay/dead-air event trace (barge_in_candidate, "
        "pipeline_response_interrupted, stale_audio_blocked, etc.) is NOT in this "
        "database — those are structured-log-only events (see transport/events.py's "
        "log_event()), never persisted as CallEvent rows. Cross-reference your "
        f"captured server log file for call_session_id={report.call_session_id}. "
        "See docs/P10_REAL_CALL_BENCHMARK.md."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("call_session_id", help="UUID of the call_sessions row to report on")
    args = parser.parse_args(argv)
    try:
        call_session_id = uuid.UUID(args.call_session_id)
    except ValueError:
        print(f"'{args.call_session_id}' is not a valid UUID", file=sys.stderr)
        raise SystemExit(2) from None

    try:
        report = asyncio.run(build_report(call_session_id))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    print(render_report(report))


if __name__ == "__main__":
    main()
