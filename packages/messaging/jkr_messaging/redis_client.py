"""Shared async Redis client for the small set of non-queue uses that need
one directly: the campaign safety gate's dispatch lock + rate-limit counters
(services/api and services/campaign-worker both need the exact same keys to
mean the same thing, so this lives here rather than being duplicated per
service). Dramatiq's own broker connection (broker.py) is separate — that one
is dramatiq-internal and not meant for arbitrary GET/SET/INCR use.
"""

from __future__ import annotations

import os
from functools import lru_cache

import redis.asyncio as redis


@lru_cache
def get_redis() -> redis.Redis:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:16379/0")
    return redis.from_url(redis_url, decode_responses=True)
