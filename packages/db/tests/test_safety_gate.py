import uuid
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from jkr_db.safety_gate import (
    OBJECTIVE_TO_CONSENT_PURPOSE,
    dispatch_lock_key,
    rate_limit_key,
    within_calling_hours,
)

_IST = ZoneInfo("Asia/Kolkata")


def test_within_calling_hours_true_inside_window():
    monday_noon = datetime(2026, 8, 3, 12, 0, tzinfo=_IST)
    assert within_calling_hours(
        window_start=time(9, 0), window_end=time(20, 0), days_of_week=[0, 1, 2, 3, 4, 5], tz_name="Asia/Kolkata", now=monday_noon
    )


def test_within_calling_hours_false_outside_window():
    monday_midnight = datetime(2026, 8, 3, 23, 30, tzinfo=_IST)
    assert not within_calling_hours(
        window_start=time(9, 0), window_end=time(20, 0), days_of_week=[0, 1, 2, 3, 4, 5], tz_name="Asia/Kolkata", now=monday_midnight
    )


def test_within_calling_hours_false_on_excluded_day():
    # 2026-08-02 is a Sunday (weekday() == 6).
    sunday_noon = datetime(2026, 8, 2, 12, 0, tzinfo=_IST)
    assert not within_calling_hours(
        window_start=time(9, 0), window_end=time(20, 0), days_of_week=[0, 1, 2, 3, 4, 5], tz_name="Asia/Kolkata", now=sunday_noon
    )


def test_dispatch_lock_key_is_stable_and_scoped_per_pair():
    campaign_id = uuid.uuid4()
    contact_a, contact_b = uuid.uuid4(), uuid.uuid4()
    assert dispatch_lock_key(campaign_id, contact_a) == dispatch_lock_key(campaign_id, contact_a)
    assert dispatch_lock_key(campaign_id, contact_a) != dispatch_lock_key(campaign_id, contact_b)


def test_rate_limit_key_buckets_by_minute_window():
    workspace_id = uuid.uuid4()
    t1 = datetime(2026, 8, 3, 12, 0, 5, tzinfo=UTC)
    t2 = datetime(2026, 8, 3, 12, 0, 50, tzinfo=UTC)
    t3 = datetime(2026, 8, 3, 12, 1, 5, tzinfo=UTC)
    assert rate_limit_key(workspace_id, now=t1) == rate_limit_key(workspace_id, now=t2)
    assert rate_limit_key(workspace_id, now=t1) != rate_limit_key(workspace_id, now=t3)


def test_every_campaign_objective_has_a_consent_purpose_mapping():
    for objective in ("book_appointment", "qualify_lead", "collect_feedback", "renewal_reminder", "custom"):
        assert objective in OBJECTIVE_TO_CONSENT_PURPOSE
        assert OBJECTIVE_TO_CONSENT_PURPOSE[objective] in {"marketing", "transactional", "service", "appointment_reminder"}
