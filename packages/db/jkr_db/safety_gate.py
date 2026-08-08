"""The outbound campaign safety gate (docs/SECURITY_AND_COMPLIANCE.md §2).

Lives in packages/db — not in services/api or services/campaign-worker —
specifically so both share the exact one implementation: services/api's
`/campaigns/{id}/dry-run` and campaign-worker's real dispatch loop MUST run
identical logic, or a dry-run's "would dispatch" promise could silently lie
about what actually happens at dispatch time. See docs/DECISIONS/0003.

Pure/read-only: every check here only ever peeks at Redis (dispatch lock,
rate-limit counter), never mutates it. The one-time side effects the doc
describes (acquire the lock, increment the counter, flip the contact to
`reserved`) only happen in campaign-worker's dialer, strictly after every
check below has passed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.models.calls import CallSession
from jkr_db.models.campaigns import Campaign, CampaignContact, CampaignSchedule
from jkr_db.models.contacts import ConsentEvent, Contact, SuppressionEntry
from jkr_db.models.tenancy import Workspace
from jkr_db.phone import is_valid as phone_is_valid


class RedisLike(Protocol):
    async def exists(self, key: str) -> int: ...
    async def get(self, key: str) -> str | None: ...


# A campaign's objective implies what it needs consent for — spec doesn't
# pin this mapping down explicitly, so it's fixed here as a documented,
# conservative simplification. A real workspace compliance setting (spec
# §8's "campaign purpose categories") would make this configurable.
OBJECTIVE_TO_CONSENT_PURPOSE: dict[str, str] = {
    "book_appointment": "marketing",
    "qualify_lead": "marketing",
    "collect_feedback": "service",
    "renewal_reminder": "service",
    "custom": "marketing",
}

NON_DISPATCHABLE_CONTACT_STATUSES = {"dialing", "ringing", "in_progress", "completed", "suppressed", "human_review"}

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_PER_WINDOW = 30


def dispatch_lock_key(campaign_id: uuid.UUID, contact_id: uuid.UUID) -> str:
    return f"jkr:dispatch_lock:{campaign_id}:{contact_id}"


def rate_limit_key(workspace_id: uuid.UUID, *, now: datetime | None = None) -> str:
    bucket = int((now or datetime.now(UTC)).timestamp() // RATE_LIMIT_WINDOW_SECONDS)
    return f"jkr:dispatch_rate:{workspace_id}:{bucket}"


async def _has_valid_consent(db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID, purpose: str) -> bool:
    now = datetime.now(UTC)
    result = await db.execute(
        select(ConsentEvent.id)
        .where(
            ConsentEvent.workspace_id == workspace_id,
            ConsentEvent.contact_id == contact_id,
            ConsentEvent.purpose == purpose,
            ConsentEvent.revoked_at.is_(None),
            or_(ConsentEvent.expires_at.is_(None), ConsentEvent.expires_at > now),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _is_suppressed(db: AsyncSession, *, workspace_id: uuid.UUID, phone_e164: str) -> bool:
    result = await db.execute(
        select(SuppressionEntry.id).where(SuppressionEntry.workspace_id == workspace_id, SuppressionEntry.phone_e164 == phone_e164)
    )
    return result.scalar_one_or_none() is not None


def within_calling_hours(*, window_start: time, window_end: time, days_of_week: list[int], tz_name: str, now: datetime | None = None) -> bool:
    try:
        now_local = (now or datetime.now(UTC)).astimezone(ZoneInfo(tz_name))
    except Exception:
        now_local = now or datetime.now(UTC)
    if now_local.weekday() not in days_of_week:
        return False
    return window_start <= now_local.time() <= window_end


async def _today_spend_paise(db: AsyncSession, *, campaign_id: uuid.UUID, tz_name: str) -> int:
    try:
        start_of_today_local = datetime.now(ZoneInfo(tz_name)).replace(hour=0, minute=0, second=0, microsecond=0)
    except Exception:
        start_of_today_local = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(CallSession.cost_paise), 0)).where(
            CallSession.campaign_id == campaign_id, CallSession.started_at >= start_of_today_local
        )
    )
    return int(result.scalar_one())


async def run_safety_gate(
    db: AsyncSession,
    redis_client: RedisLike,
    *,
    campaign: Campaign,
    campaign_contact: CampaignContact,
    contact: Contact,
    workspace: Workspace,
    schedule: CampaignSchedule | None,
) -> list[dict]:
    """Returns an ordered list of `{"check", "passed", "detail"}` dicts,
    short-circuiting (stopping) at the first failure — mirrors
    docs/SECURITY_AND_COMPLIANCE.md §2's "first failure short-circuits"."""
    checks: list[dict] = []

    def fail(check: str, detail: str) -> list[dict]:
        checks.append({"check": check, "passed": False, "detail": detail})
        return checks

    def ok(check: str) -> None:
        checks.append({"check": check, "passed": True, "detail": None})

    # 1. Campaign is in a dispatchable state. "draft" is included (not just
    # "active") so a dry-run is usable *before* launch; the real dialer only
    # ever calls this once campaign.status is already "active", so this is a
    # no-op guard there, not a loosening of the live-dispatch rule.
    if campaign.status not in ("draft", "active"):
        return fail("campaign_active", f"Campaign status is '{campaign.status}', not draft/active")
    ok("campaign_active")

    # 2. Contact isn't already mid-flight, done, or blocked.
    if campaign_contact.status in NON_DISPATCHABLE_CONTACT_STATUSES:
        return fail("contact_dispatchable", f"Contact status is '{campaign_contact.status}'")
    ok("contact_dispatchable")

    # 3. Consent on file for this campaign's purpose, unexpired, unrevoked.
    purpose = OBJECTIVE_TO_CONSENT_PURPOSE.get(campaign.objective, "marketing")
    if not await _has_valid_consent(db, workspace_id=workspace.id, contact_id=contact.id, purpose=purpose):
        return fail("consent", f"No unexpired consent on file for purpose '{purpose}'")
    ok("consent")

    # 4. Phone number is a valid, dispatchable E.164 number.
    if not contact.phone_e164 or not phone_is_valid(contact.phone_e164):
        return fail("phone_valid", "Phone number failed E.164 validation")
    ok("phone_valid")

    # 5. Not on the suppression list (checked fresh, not the cached flag).
    if await _is_suppressed(db, workspace_id=workspace.id, phone_e164=contact.phone_e164):
        return fail("not_suppressed", "Contact is on the suppression list")
    ok("not_suppressed")

    # 6. Within calling hours.
    if schedule is not None:
        window_start, window_end, days, tz_name = schedule.calling_window_start, schedule.calling_window_end, schedule.days_of_week, schedule.timezone
    else:
        window_start, window_end, days, tz_name = workspace.calling_window_start, workspace.calling_window_end, [0, 1, 2, 3, 4, 5], workspace.timezone
    if not within_calling_hours(window_start=window_start, window_end=window_end, days_of_week=days, tz_name=tz_name):
        return fail("calling_hours", "Outside the configured calling-hours window")
    ok("calling_hours")

    # 7. Under the per-contact attempt cap.
    if campaign_contact.attempt_count >= campaign.max_attempts:
        return fail("max_attempts", f"Already attempted {campaign_contact.attempt_count}/{campaign.max_attempts} times")
    ok("max_attempts")

    # 8. No other dispatch already in flight for this (campaign, contact) —
    # peek only; the real lock is acquired atomically at reserve time.
    if await redis_client.exists(dispatch_lock_key(campaign.id, contact.id)):
        return fail("no_concurrent_dispatch", "Another dispatch is already in flight for this contact")
    ok("no_concurrent_dispatch")

    # 9. Workspace/campaign budget. Real usage/billing tracking is a later
    # pass's job — this compares against actual (currently always-zero,
    # since mock calls cost nothing) call_sessions.cost_paise: real logic on
    # real data, just trivially satisfied until a real provider bills something.
    if campaign.daily_budget_paise is not None:
        spent = await _today_spend_paise(db, campaign_id=campaign.id, tz_name=workspace.timezone)
        if spent >= campaign.daily_budget_paise:
            return fail("budget", f"Daily budget of {campaign.daily_budget_paise} paise reached ({spent} spent)")
    ok("budget")

    # 10. Workspace dispatch rate limit (peek only, same reasoning as #8).
    current = await redis_client.get(rate_limit_key(workspace.id))
    if current is not None and int(current) >= RATE_LIMIT_MAX_PER_WINDOW:
        return fail("rate_limit", "Workspace dispatch rate limit exceeded")
    ok("rate_limit")

    return checks
