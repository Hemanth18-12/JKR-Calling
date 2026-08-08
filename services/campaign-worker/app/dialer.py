"""The campaign dialer loop (docs/ARCHITECTURE.md §3, §1's "campaign-worker").

`run_dispatch_batch` is the only place a call is ever dispatched from a
campaign — it runs the shared `jkr_db.safety_gate.run_safety_gate` for each
candidate contact, and only after every check passes does it reserve the
contact (Redis lock + rate-limit increment + status flip) and dial.

Since this pass has no real telephony adapter wired into voice-worker at all
(services/voice-worker/app/conversation_engine.py hardcodes `is_mock=True`
and never touches `MockTelephony` — a carried-forward Phase 3 scope
boundary, not something introduced here), every dispatch this loop performs
is a mock call. What's real: the safety gate, the reserve/lock/rate-limit
mechanics, the retry scheduling and backoff, and — since a campaign call has
no human typing responses the way Test Lab's operator does — an
auto-play "mock customer" that answers the agent's questions with a small
round-robin set of generic replies so the call runs to a real completion
(real turns, real extraction, real post-call intelligence) without a human
in the loop. This is a deliberate simplification of "who plays the
customer," documented here and in docs/IMPLEMENTATION_CHECKLIST.md, not a
hidden shortcut.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from jkr_db.models.campaigns import (
    Campaign,
    CampaignAttempt,
    CampaignContact,
    CampaignSchedule,
    RetryJob,
)
from jkr_db.models.contacts import Contact
from jkr_db.models.tenancy import Workspace
from jkr_db.safety_gate import dispatch_lock_key, rate_limit_key, run_safety_gate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

BATCH_SIZE = 5
MAX_CUSTOMER_TURNS = 6
RESERVE_LOCK_TTL_SECONDS = 300
RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_BACKOFF_MINUTES = [30, 120, 480]
SELF_RESCHEDULE_MIN_DELAY_S = 5
SELF_RESCHEDULE_MAX_DELAY_S = 300
# Waiting out each agent turn's `estimated_duration_ms` (plus this margin)
# before replying isn't cosmetic pacing — TurnManager classifies any reply
# arriving before that window elapses (or under `min_interruption_ms`) as a
# false-positive filler and never advances conversation state (see
# services/voice-worker/app/turn_manager.py). A reply-immediately loop here
# would make every campaign call end up "unreachable" with empty
# extracted_summary despite the HTTP calls all succeeding — that exact bug
# was caught live before this margin was added; see
# docs/IMPLEMENTATION_CHECKLIST.md Phase 5.
REPLY_DELAY_MARGIN_MS = 150

# Deliberately generic — conversation_engine.submit_user_turn stores whatever
# text arrives as the answer to the field currently being asked about, so
# these don't need to be field-specific to genuinely advance the script (see
# module docstring above).
CANNED_CUSTOMER_REPLIES = [
    "Yes, that works for me.",
    "Sure, tell me more about that.",
    "Okay, that sounds fine.",
    "Yes please, go ahead.",
    "That's right.",
    "Sounds good to me.",
]


def pick_customer_reply(turn_index: int) -> str:
    return CANNED_CUSTOMER_REPLIES[turn_index % len(CANNED_CUSTOMER_REPLIES)]


def should_stop_conversation(conversation_state: dict) -> bool:
    return conversation_state.get("next_best_action") == "close_conversation"


def simulate_connect_outcome(contact_id: uuid.UUID, attempt_number: int) -> str:
    """Deterministic (not truly random, so reproducible in tests and demos)
    stand-in for "did the phone actually get answered" — biased heavily
    toward `answered` since this is a demo, not a churn simulator."""
    digest = hashlib.sha256(f"{contact_id}:{attempt_number}".encode()).digest()
    roll = digest[0] % 100
    if roll < 80:
        return "answered"
    if roll < 90:
        return "no_answer"
    if roll < 96:
        return "busy"
    return "provider_error"


def retry_reason_for_outcome(outcome: str) -> str:
    return {"no_answer": "no_answer", "busy": "busy", "provider_error": "provider_error"}.get(outcome, "provider_error")


def next_retry_delay_minutes(attempt_number: int, backoff_minutes: list[int]) -> int:
    if not backoff_minutes:
        backoff_minutes = DEFAULT_BACKOFF_MINUTES
    index = min(max(attempt_number - 1, 0), len(backoff_minutes) - 1)
    return backoff_minutes[index]


def clamp_seconds(seconds: float) -> int:
    return max(SELF_RESCHEDULE_MIN_DELAY_S, min(SELF_RESCHEDULE_MAX_DELAY_S, int(seconds)))


async def _run_mock_call(
    settings: Settings, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID, contact_id: uuid.UUID,
    contact_name: str, agent_id: uuid.UUID,
) -> dict | None:
    headers = {"X-Internal-Token": settings.internal_service_token}
    async with httpx.AsyncClient(base_url=settings.voice_worker_base_url, timeout=15.0) as client:
        try:
            resp = await client.post(
                "/sessions",
                json={
                    "workspace_id": str(workspace_id), "agent_id": str(agent_id), "contact_name": contact_name,
                    "campaign_id": str(campaign_id), "contact_id": str(contact_id),
                },
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None

        session = resp.json()
        call_id = session["call_id"]
        state = session["conversation_state"]
        pending_agent_duration_ms = session.get("estimated_duration_ms") or 0

        turn_index = 0
        while turn_index < MAX_CUSTOMER_TURNS and not should_stop_conversation(state):
            await asyncio.sleep((pending_agent_duration_ms + REPLY_DELAY_MARGIN_MS) / 1000)
            try:
                resp = await client.post(
                    f"/sessions/{call_id}/user-turn",
                    json={"workspace_id": str(workspace_id), "text": pick_customer_reply(turn_index)},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                break
            payload = resp.json()
            state = payload["conversation_state"]
            agent_turn = payload.get("agent_turn") or {}
            pending_agent_duration_ms = agent_turn.get("estimated_duration_ms") or 0
            turn_index += 1

        try:
            resp = await client.post(
                f"/sessions/{call_id}/end",
                json={"workspace_id": str(workspace_id), "end_reason": "agent_ended"},
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None

        payload = resp.json()
        return {"call_id": uuid.UUID(call_id), "outcome_category": payload["outcome_category"], "lead_score": payload["lead_score"]}


async def _fetch_work_items(
    db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID, now: datetime,
) -> list[tuple[CampaignContact, Contact, RetryJob | None]]:
    pending_result = await db.execute(
        select(CampaignContact, Contact)
        .join(Contact, Contact.id == CampaignContact.contact_id)
        .where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id, CampaignContact.status == "pending")
        .order_by(CampaignContact.created_at)
        .limit(BATCH_SIZE)
    )
    items: list[tuple[CampaignContact, Contact, RetryJob | None]] = [(cc, contact, None) for cc, contact in pending_result.all()]

    due_result = await db.execute(
        select(CampaignContact, Contact, RetryJob)
        .join(Contact, Contact.id == CampaignContact.contact_id)
        .join(RetryJob, RetryJob.campaign_contact_id == CampaignContact.id)
        .where(
            CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == "retry_scheduled", RetryJob.executed_at.is_(None), RetryJob.cancelled_at.is_(None),
            RetryJob.scheduled_for <= now,
        )
        .order_by(RetryJob.scheduled_for)
        .limit(BATCH_SIZE)
    )
    items.extend((cc, contact, retry_job) for cc, contact, retry_job in due_result.all())
    return items[:BATCH_SIZE]


async def _process_item(
    db: AsyncSession, redis_client, settings: Settings, *, campaign: Campaign, workspace: Workspace,
    schedule: CampaignSchedule | None, campaign_contact: CampaignContact, contact: Contact, retry_job: RetryJob | None,
) -> None:
    now = datetime.now(UTC)
    checks = await run_safety_gate(
        db, redis_client, campaign=campaign, campaign_contact=campaign_contact, contact=contact, workspace=workspace, schedule=schedule,
    )
    passed = all(c["passed"] for c in checks)
    attempt_number = campaign_contact.attempt_count + 1

    if retry_job is not None:
        retry_job.executed_at = now

    if not passed:
        failed_check = next(c["check"] for c in checks if not c["passed"])
        db.add(
            CampaignAttempt(
                workspace_id=workspace.id, campaign_contact_id=campaign_contact.id, attempt_number=attempt_number,
                gate_result={"checks": checks}, dispatched=False, outcome=None, failure_reason=f"gate:{failed_check}",
            )
        )
        # Leave campaign_contact.status untouched (still pending/retry_scheduled)
        # — it's retried on the next batch this loop runs, or the next manual
        # campaign action. See module docstring's note on calling-hours blocks.
        await db.flush()
        return

    lock_key = dispatch_lock_key(campaign.id, contact.id)
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=RESERVE_LOCK_TTL_SECONDS)
    if not acquired:
        return  # lost the race this cycle — try again next batch

    try:
        await redis_client.incr(rate_limit_key(workspace.id, now=now))
        await redis_client.expire(rate_limit_key(workspace.id, now=now), RATE_LIMIT_WINDOW_SECONDS)

        campaign_contact.status = "dialing"
        campaign_contact.attempt_count = attempt_number
        campaign_contact.last_attempt_at = now
        await db.flush()

        connect_outcome = simulate_connect_outcome(contact.id, attempt_number)
        backoff = campaign.retry_policy.get("backoff_minutes", DEFAULT_BACKOFF_MINUTES) if campaign.retry_policy else DEFAULT_BACKOFF_MINUTES

        if connect_outcome != "answered":
            db.add(
                CampaignAttempt(
                    workspace_id=workspace.id, campaign_contact_id=campaign_contact.id, attempt_number=attempt_number,
                    gate_result={"checks": checks}, dispatched=True, outcome=connect_outcome,
                    failure_reason=f"simulated connect result: {connect_outcome}",
                )
            )
            _schedule_retry_or_fail(db, campaign=campaign, campaign_contact=campaign_contact, attempt_number=attempt_number, reason=retry_reason_for_outcome(connect_outcome), backoff=backoff, now=now)
            await db.flush()
            return

        contact.last_call_at = now
        campaign_contact.status = "in_progress"
        await db.flush()

        call_result = await _run_mock_call(
            settings, workspace_id=workspace.id, campaign_id=campaign.id, contact_id=contact.id,
            contact_name=contact.full_name, agent_id=campaign.agent_id,
        )

        if call_result is None:
            db.add(
                CampaignAttempt(
                    workspace_id=workspace.id, campaign_contact_id=campaign_contact.id, attempt_number=attempt_number,
                    gate_result={"checks": checks}, dispatched=True, outcome="provider_error",
                    failure_reason="voice-worker call failed or was unreachable",
                )
            )
            _schedule_retry_or_fail(db, campaign=campaign, campaign_contact=campaign_contact, attempt_number=attempt_number, reason="provider_error", backoff=backoff, now=now)
        else:
            db.add(
                CampaignAttempt(
                    workspace_id=workspace.id, campaign_contact_id=campaign_contact.id, attempt_number=attempt_number,
                    call_session_id=call_result["call_id"], gate_result={"checks": checks}, dispatched=True,
                    outcome=call_result["outcome_category"],
                )
            )
            campaign_contact.status = "completed"
            campaign_contact.extracted_summary = {"outcome_category": call_result["outcome_category"], "lead_score": call_result["lead_score"]}
        await db.flush()
    finally:
        await redis_client.delete(lock_key)


def _schedule_retry_or_fail(
    db: AsyncSession, *, campaign: Campaign, campaign_contact: CampaignContact, attempt_number: int, reason: str, backoff: list[int], now: datetime,
) -> None:
    if attempt_number >= campaign.max_attempts:
        campaign_contact.status = "failed"
        campaign_contact.next_attempt_at = None
        return
    delay_minutes = next_retry_delay_minutes(attempt_number, backoff)
    scheduled_for = now + timedelta(minutes=delay_minutes)
    db.add(RetryJob(workspace_id=campaign.workspace_id, campaign_contact_id=campaign_contact.id, reason=reason, scheduled_for=scheduled_for))
    campaign_contact.status = "retry_scheduled"
    campaign_contact.next_attempt_at = scheduled_for


async def run_dispatch_batch(db: AsyncSession, redis_client, settings: Settings, *, campaign_id: uuid.UUID, workspace_id: uuid.UUID) -> dict:
    """One batch iteration. Returns `{"reschedule_in_seconds": int | None, "completed": bool}`
    so the actor entrypoint (app/tasks.py) knows whether to self-enqueue again."""
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.status != "active":
        return {"reschedule_in_seconds": None, "completed": False}

    workspace = await db.get(Workspace, workspace_id)
    schedule_result = await db.execute(
        select(CampaignSchedule).where(CampaignSchedule.workspace_id == workspace_id, CampaignSchedule.campaign_id == campaign_id)
    )
    schedule = schedule_result.scalar_one_or_none()

    now = datetime.now(UTC)
    work_items = await _fetch_work_items(db, workspace_id=workspace_id, campaign_id=campaign_id, now=now)

    for campaign_contact, contact, retry_job in work_items:
        await _process_item(
            db, redis_client, settings, campaign=campaign, workspace=workspace, schedule=schedule,
            campaign_contact=campaign_contact, contact=contact, retry_job=retry_job,
        )

    # Is there more work right now (batch cap was hit)?
    more_now = await _fetch_work_items(db, workspace_id=workspace_id, campaign_id=campaign_id, now=now)
    if more_now:
        return {"reschedule_in_seconds": SELF_RESCHEDULE_MIN_DELAY_S, "completed": False}

    # Any future retry to wake up for?
    next_retry_result = await db.execute(
        select(func.min(RetryJob.scheduled_for))
        .join(CampaignContact, CampaignContact.id == RetryJob.campaign_contact_id)
        .where(
            CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id,
            RetryJob.executed_at.is_(None), RetryJob.cancelled_at.is_(None), RetryJob.scheduled_for > now,
        )
    )
    next_retry_at = next_retry_result.scalar_one_or_none()
    if next_retry_at is not None:
        delay = clamp_seconds((next_retry_at - now).total_seconds())
        return {"reschedule_in_seconds": delay, "completed": False}

    # Nothing left to do right now. If every contact has reached a terminal
    # state, the campaign is done; otherwise it just goes idle (e.g. blocked
    # on calling-hours with no scheduled wake-up — see module docstring) and
    # waits for a manual campaign action to resume it.
    unresolved_result = await db.execute(
        select(func.count(CampaignContact.id)).where(
            CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id,
            CampaignContact.status.not_in(["completed", "failed", "suppressed"]),
        )
    )
    if unresolved_result.scalar_one() == 0:
        campaign.status = "completed"
        await db.flush()
        return {"reschedule_in_seconds": None, "completed": True}

    return {"reschedule_in_seconds": None, "completed": False}
