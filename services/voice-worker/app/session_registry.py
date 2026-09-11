"""In-memory registry of active call runtimes, keyed by call_id.

Business-relevant conversation state (`known_fields`, `objective_status`,
etc.) is persisted to `call_sessions.state` (JSONB) after every turn, so it
survives a worker restart. What's *only* here — the `TurnManager`'s precise
interruption-timing window — does not; a restart mid-call would lose the
ability to correctly classify the very next interruption and would resume
conversation-engine decisions from the persisted state rather than mid-turn.
Acceptable for a single-process local/demo deployment; called out here
rather than silently assumed away. A production deployment would move this
into Redis, keyed the same way.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field

from jkr_conversation.schemas import ConversationPolicySnapshot

from app.turn_manager import TurnManager

logger = logging.getLogger(__name__)


@dataclass
class CallRuntime:
    turn_manager: TurnManager
    language: str
    human_transfer_enabled: bool = True
    policy: ConversationPolicySnapshot = field(default_factory=ConversationPolicySnapshot)
    business_identity: str = ""


_REGISTRY: dict[uuid.UUID, CallRuntime] = {}


async def _save_to_redis(call_id: uuid.UUID, data: dict) -> None:
    try:
        from jkr_messaging.redis_client import get_redis
        client = get_redis()
        await client.set(f"jkr:call_runtime:{call_id}", json.dumps(data), ex=3600)
    except Exception as exc:
        logger.debug("Could not cache call runtime in Redis: %s", exc)


async def _delete_from_redis(call_id: uuid.UUID) -> None:
    try:
        from jkr_messaging.redis_client import get_redis
        client = get_redis()
        await client.delete(f"jkr:call_runtime:{call_id}")
    except Exception as exc:
        logger.debug("Could not remove call runtime from Redis: %s", exc)


def put(call_id: uuid.UUID, runtime: CallRuntime) -> None:
    _REGISTRY[call_id] = runtime
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            data = {
                "call_id": str(call_id),
                "language": runtime.language,
                "human_transfer_enabled": runtime.human_transfer_enabled,
                "business_identity": runtime.business_identity,
            }
            loop.create_task(_save_to_redis(call_id, data))
    except Exception:
        pass


def get(call_id: uuid.UUID) -> CallRuntime | None:
    return _REGISTRY.get(call_id)


def discard(call_id: uuid.UUID) -> None:
    _REGISTRY.pop(call_id, None)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_delete_from_redis(call_id))
    except Exception:
        pass
