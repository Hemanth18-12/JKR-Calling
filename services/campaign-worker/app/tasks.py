"""Dramatiq actor entrypoint. Run the worker with:
    uv run --package jkr-campaign-worker dramatiq app.tasks -p 1 -t 1
from services/campaign-worker/ (see Makefile's dev-native target).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import dramatiq
from jkr_db.session import workspace_scoped_session

from app.config import get_settings

settings = get_settings()
os.environ["DATABASE_URL"] = settings.database_url
os.environ.setdefault("REDIS_URL", settings.redis_url)

# Registers the shared Redis broker (dramatiq.set_broker) before the actor
# below is declared — required so this actor is reachable at the same queue
# services/api's jkr_messaging.enqueue("run_campaign_dispatch_batch", ...)
# call targets, and so this actor's own self-rescheduling enqueue() calls
# reach itself.
from jkr_messaging import enqueue, get_broker, get_redis  # noqa: E402

get_broker()


@dramatiq.actor(actor_name="run_campaign_dispatch_batch", queue_name="campaigns", max_retries=3, min_backoff=1000)
def run_campaign_dispatch_batch_actor(campaign_id: str, workspace_id: str) -> None:
    asyncio.run(_run(campaign_id, workspace_id))


async def _run(campaign_id: str, workspace_id: str) -> None:
    from app.dialer import run_dispatch_batch

    redis_client = get_redis()
    async with workspace_scoped_session(uuid.UUID(workspace_id)) as db:
        result = await run_dispatch_batch(
            db, redis_client, settings, campaign_id=uuid.UUID(campaign_id), workspace_id=uuid.UUID(workspace_id)
        )

    if result["reschedule_in_seconds"] is not None:
        enqueue(
            "run_campaign_dispatch_batch", args=(campaign_id, workspace_id), queue_name="campaigns",
            delay_seconds=result["reschedule_in_seconds"],
        )
