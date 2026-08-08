"""One Redis-backed Dramatiq broker, shared by every service that either
produces or consumes background jobs. A *producer* (e.g. services/api,
enqueueing a post-call pipeline run) never needs to import a *consumer's*
implementation package — `enqueue()` below builds a raw `dramatiq.Message`
by actor name, which only requires the two sides to agree on that name and
both point at the same Redis broker, not share Python code.
"""

from __future__ import annotations

import os
from functools import lru_cache

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.message import Message


@lru_cache
def get_broker() -> RedisBroker:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:16379/0")
    broker = RedisBroker(url=redis_url)
    dramatiq.set_broker(broker)
    return broker


def enqueue(
    actor_name: str, *, args: tuple = (), kwargs: dict | None = None, queue_name: str = "default", delay_seconds: int | None = None
) -> None:
    """`delay_seconds` (e.g. campaign-worker's dialer self-rescheduling to
    process a due retry_job) maps to Dramatiq's own `delay` option, in
    milliseconds — RedisBroker holds delayed messages in a separate internal
    queue and moves them to the real one once due, no extra infra needed."""
    broker = get_broker()
    message = Message(
        queue_name=queue_name,
        actor_name=actor_name,
        args=args,
        kwargs=kwargs or {},
        options={},
    )
    broker.enqueue(message, delay=delay_seconds * 1000 if delay_seconds is not None else None)
