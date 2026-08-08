"""Redis token-bucket-style rate limiting (docs/SECURITY_AND_COMPLIANCE.md §7:
"Rate limiting ... on auth endpoints and on the public webhook endpoints").
Fixed-window counter, not a true token bucket — simpler, and the distinction
doesn't matter at this traffic scale; a burst right at a window boundary can
momentarily allow ~2x the limit, which is an acceptable tradeoff for a local/
demo-scale product, not silently pretended away.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from jkr_messaging import get_redis


def rate_limit(key_prefix: str, *, max_requests: int, window_seconds: int):
    async def _dep(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"jkr:rate_limit:{key_prefix}:{client_ip}"
        redis_client = get_redis()
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window_seconds)
        if current > max_requests:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests — try again shortly.")

    return _dep
