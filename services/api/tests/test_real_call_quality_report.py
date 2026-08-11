"""P10 — tests/tools/real_call_quality_report.py: the render half (pure,
no database) and the build half (real Postgres, same seed/cleanup pattern
test_turn_detection_integration.py already established). See
docs/P10_REAL_CALL_BENCHMARK.md.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")
os.environ.setdefault("REDIS_URL", "redis://localhost:16379/0")


def _load_tool():
    import importlib.util
    import sys

    here = os.path.abspath(__file__)
    repo_root = here
    for _ in range(4):  # tests -> api -> services -> repo root
        repo_root = os.path.dirname(repo_root)
    path = os.path.join(repo_root, "tests", "tools", "real_call_quality_report.py")
    spec = importlib.util.spec_from_file_location("real_call_quality_report", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_tool = _load_tool()
CallReport = _tool.CallReport
build_report = _tool.build_report
render_report = _tool.render_report


# --- render_report(): pure, no database --------------------------------


def _sample_report(**overrides) -> CallReport:
    base = dict(
        call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), status="completed", end_reason="completed",
        language="te-en-IN", started_at=None, answered_at=None, ended_at=None, duration_seconds=42, is_mock=False,
        turns=[], latency_rows=[], events=[],
    )
    base.update(overrides)
    return CallReport(**base)


def test_render_report_handles_a_call_with_no_data_gracefully():
    report = _sample_report()
    text = render_report(report)
    assert "no CallTurn rows found" in text
    assert "no CallLatencyMetric rows found" in text
    assert "no CallEvent rows found" in text


def test_render_report_shows_transcript_in_order_and_flags_interruptions():
    report = _sample_report(
        turns=[
            {"sequence_index": 0, "speaker": "agent", "text": "Hello there.", "is_interrupted": False, "started_at": None},
            {"sequence_index": 1, "speaker": "customer", "text": "One minute, cost entha?", "is_interrupted": False, "started_at": None},
            {"sequence_index": 2, "speaker": "agent", "text": "Root canal cost case", "is_interrupted": True, "started_at": None},
        ]
    )
    text = render_report(report)
    idx_hello = text.index("Hello there.")
    idx_customer = text.index("One minute, cost entha?")
    idx_agent2 = text.index("Root canal cost case")
    assert idx_hello < idx_customer < idx_agent2
    assert "[INTERRUPTED]" in text.splitlines()[text.splitlines().index([line for line in text.splitlines() if "Root canal cost case" in line][0])]


def test_render_report_groups_latency_by_stage_in_waterfall_order():
    report = _sample_report(
        latency_rows=[
            {"stage": "engine_generation", "duration_ms": 300, "provider": None, "recorded_at": None},
            {"stage": "stt_stream_finalize", "duration_ms": 120, "provider": "sarvam", "recorded_at": None},
            {"stage": "tts_stream_first_audio", "duration_ms": 210, "provider": "sarvam", "recorded_at": None},
        ]
    )
    text = render_report(report)
    idx_stt = text.index("stt_stream_finalize")
    idx_engine = text.index("engine_generation")
    idx_tts = text.index("tts_stream_first_audio")
    assert idx_stt < idx_engine < idx_tts  # STAGE_ORDER, not insertion order


def test_render_report_surfaces_unrecognized_stages_rather_than_dropping_them():
    report = _sample_report(latency_rows=[{"stage": "some_future_stage", "duration_ms": 99, "provider": None, "recorded_at": None}])
    text = render_report(report)
    assert "some_future_stage" in text
    assert "unrecognized stage" in text


def test_render_report_always_reminds_about_the_log_only_barge_in_trace():
    report = _sample_report()
    text = render_report(report)
    assert "NOT in this database" in text
    assert str(report.call_session_id) in text


# --- build_report(): real Postgres, seed + cleanup ---------------------


def _reset_db_engine() -> None:
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None


async def _seed_call_with_data() -> tuple[uuid.UUID, uuid.UUID]:
    from jkr_db.models.agents import Agent, AgentVersion
    from jkr_db.models.calls import CallEvent, CallLatencyMetric, CallSession, CallTurn
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="P10 Report Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="P10 Report Test WS", slug=f"p10-report-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(workspace_id=workspace_id, name="P10 Report Test Agent", business_identity="Aaha Dental Care", primary_language="te-en-IN", status="active")
        db.add(agent)
        await db.flush()
        agent_version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="qualify_and_route", ai_disclosure_text="I'm an AI assistant.",
            greeting_text="Hello, can we talk?", closing_text="Thank you.",
            supported_languages=["te-en-IN"], published_at=datetime.now(UTC),
        )
        db.add(agent_version)
        await db.flush()
        agent.published_version_id = agent_version.id

        call_session = CallSession(
            workspace_id=workspace_id, direction="outbound", status="completed", end_reason="completed",
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"p10-report-test-{uuid.uuid4()}",
            language="te-en-IN", state={}, started_at=datetime.now(UTC), answered_at=datetime.now(UTC),
            ended_at=datetime.now(UTC), duration_seconds=37, is_mock=False, disclosure_confirmed=True,
        )
        db.add(call_session)
        await db.flush()
        call_session_id = call_session.id

        db.add(CallTurn(workspace_id=workspace_id, call_session_id=call_session_id, turn_ref="t0", sequence_index=0, speaker="agent", text="Hello, can we talk?", language="te-en-IN", started_at=datetime.now(UTC)))
        db.add(CallTurn(workspace_id=workspace_id, call_session_id=call_session_id, turn_ref="t1", sequence_index=1, speaker="customer", text="Root canal cost entha?", language="te-en-IN", started_at=datetime.now(UTC)))
        db.add(CallLatencyMetric(workspace_id=workspace_id, call_session_id=call_session_id, stage="stt_stream_finalize", duration_ms=110, provider="sarvam", is_simulated=False, recorded_at=datetime.now(UTC)))
        db.add(CallLatencyMetric(workspace_id=workspace_id, call_session_id=call_session_id, stage="tts_stream_first_audio", duration_ms=230, provider="sarvam", is_simulated=False, recorded_at=datetime.now(UTC)))
        db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type="call_started", payload={}))
        db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type="call_ended", payload={"reason": "completed"}))

    return workspace_id, call_session_id


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in ("call_latency_metrics", "call_events", "call_turns", "call_sessions", "agent_versions"):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


def test_build_report_reconstructs_a_real_seeded_call():
    _reset_db_engine()
    workspace_id, call_session_id = asyncio.run(_seed_call_with_data())
    try:
        _reset_db_engine()
        report = asyncio.run(build_report(call_session_id))

        assert report.call_session_id == call_session_id
        assert report.workspace_id == workspace_id
        assert report.duration_seconds == 37
        assert len(report.turns) == 2
        assert report.turns[0]["text"] == "Hello, can we talk?"
        assert report.turns[1]["text"] == "Root canal cost entha?"
        stages = {row["stage"] for row in report.latency_rows}
        assert stages == {"stt_stream_finalize", "tts_stream_first_audio"}
        event_types = {e["event_type"] for e in report.events}
        assert event_types == {"call_started", "call_ended"}

        text_report = render_report(report)
        assert "Root canal cost entha?" in text_report
    finally:
        _reset_db_engine()
        asyncio.run(_cleanup(workspace_id))


def test_build_report_raises_a_clear_error_for_an_unknown_call_id():
    _reset_db_engine()
    try:
        try:
            asyncio.run(build_report(uuid.uuid4()))
        except ValueError as exc:
            assert "No call_sessions row found" in str(exc)
        else:
            raise AssertionError("expected a ValueError for an unknown call_session_id")
    finally:
        _reset_db_engine()
