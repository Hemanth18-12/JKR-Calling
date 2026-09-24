"""Real-time call state and event streaming backed by Redis.

Provides sub-millisecond event publishing and state caching for the Live
Console, so live agent/customer turns and call status flow through Redis
Pub/Sub rather than hammering PostgreSQL with polling loops.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator

from jkr_messaging.redis_client import get_redis

logger = logging.getLogger(__name__)

CALL_STATE_TTL_SECONDS = 3600  # 1 hour


def _channel_name(call_id: uuid.UUID | str) -> str:
    return f"jkr:call:{call_id}:events"


def _state_key(call_id: uuid.UUID | str) -> str:
    return f"jkr:call:{call_id}:live_state"


async def publish_call_event(call_id: uuid.UUID | str, event_type: str, data: dict[str, Any]) -> None:
    """Publish an event to the call's Redis Pub/Sub channel and update live state."""
    try:
        redis_client = get_redis()
        payload = json.dumps({"event": event_type, "data": data})
        channel = _channel_name(call_id)
        await redis_client.publish(channel, payload)

        # Append to chronological event log in Redis
        log_key = f"jkr:call:{call_id}:event_log"
        await redis_client.rpush(log_key, payload)
        await redis_client.expire(log_key, CALL_STATE_TTL_SECONDS)

        # Update live state in Redis
        state_key = _state_key(call_id)
        existing = await redis_client.get(state_key)
        state_obj = json.loads(existing) if existing else {"call_id": str(call_id), "status": "in_progress", "turns": []}

        if event_type == "turn":
            state_obj.setdefault("turns", []).append(data)
            state_obj["last_turn"] = data
        elif event_type == "call_started":
            state_obj.update(data)
            state_obj["status"] = "in_progress"
        elif event_type == "call_ended":
            state_obj["status"] = data.get("status", "completed")
            state_obj["outcome_category"] = data.get("outcome_category")
        elif event_type == "interruption":
            state_obj["last_interruption"] = data
        elif event_type == "supervisor_listen":
            state_obj["is_listened"] = True
            state_obj["supervisor_id"] = data.get("supervisor_id")
        elif event_type == "whisper":
            state_obj["last_whisper"] = data
        elif event_type == "barge":
            state_obj["is_barged_in"] = (data.get("action") == "takeover")
            state_obj["status"] = "human_takeover" if (data.get("action") == "takeover") else "in_progress"

        await redis_client.set(state_key, json.dumps(state_obj), ex=CALL_STATE_TTL_SECONDS)
    except Exception as exc:
        logger.debug("Redis publish_call_event failed for %s (%s): %s", call_id, event_type, exc)


async def get_call_events_log(call_id: uuid.UUID | str) -> list[dict[str, Any]]:
    """Fetch chronological real-time event log directly from Redis."""
    try:
        redis_client = get_redis()
        events_raw = await redis_client.lrange(f"jkr:call:{call_id}:event_log", 0, -1)
        return [json.loads(e) for e in events_raw]
    except Exception as exc:
        logger.debug("Redis get_call_events_log failed for %s: %s", call_id, exc)
        return []


async def get_call_live_state(call_id: uuid.UUID | str) -> dict[str, Any] | None:
    """Fetch active live call state directly from Redis."""
    try:
        redis_client = get_redis()
        data = await redis_client.get(_state_key(call_id))
        return json.loads(data) if data else None
    except Exception as exc:
        logger.debug("Redis get_call_live_state failed for %s: %s", call_id, exc)
        return None


async def subscribe_call_events(call_id: uuid.UUID | str) -> AsyncIterator[dict[str, Any]]:
    """Async iterator subscribing to the Redis Pub/Sub channel for a live call."""
    redis_client = get_redis()
    pubsub = redis_client.pubsub()
    channel = _channel_name(call_id)
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    yield payload
                    if payload.get("event") in ("call_ended", "call_terminated"):
                        break
                except Exception:
                    continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
