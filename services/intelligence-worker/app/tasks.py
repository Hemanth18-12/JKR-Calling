"""Dramatiq actor entrypoint. Run the worker with:
    uv run --package jkr-intelligence-worker dramatiq app.tasks -p 1 -t 1
from services/intelligence-worker/ (see Makefile's dev-native target).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import dramatiq
from jkr_db.session import workspace_scoped_session

from app.config import get_settings
from app.pipeline import run_post_call_pipeline

settings = get_settings()
os.environ["DATABASE_URL"] = settings.database_url
os.environ.setdefault("REDIS_URL", settings.redis_url)

# Importing jkr_messaging.broker configures + registers the shared Redis
# broker (dramatiq.set_broker) before any @dramatiq.actor below is declared —
# required so this actor is reachable at the same broker+queue voice-worker's
# jkr_messaging.enqueue("run_post_call_pipeline", ..., queue_name="intelligence")
# call targets. The dedicated "intelligence" queue name (not dramatiq's
# "default") matters: campaign-worker also consumes from the same Redis
# broker, and two worker processes both listening on "default" would each
# receive a share of the OTHER's jobs and dead-letter them — see
# docs/IMPLEMENTATION_CHECKLIST.md Phase 5 for the incident this fixed.
from jkr_messaging.broker import get_broker  # noqa: E402

get_broker()


@dramatiq.actor(actor_name="run_post_call_pipeline", queue_name="intelligence", max_retries=3, min_backoff=1000)
def run_post_call_pipeline_actor(call_id: str, workspace_id: str) -> None:
    asyncio.run(_run(call_id, workspace_id))


async def _run(call_id: str, workspace_id: str) -> None:
    async with workspace_scoped_session(uuid.UUID(workspace_id)) as db:
        await run_post_call_pipeline(
            db, workspace_id=uuid.UUID(workspace_id), call_id=uuid.UUID(call_id),
            encryption_key=settings.credentials_encryption_key,
        )
