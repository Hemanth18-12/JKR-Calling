"""In-memory registry of active call runtimes, keyed by call_id.

Business-relevant conversation state (`known_fields`, `objective_status`,
etc.) is persisted to `call_sessions.state` (JSONB) after every turn, so it
survives a worker restart. What's *only* here — the `TurnManager`'s precise
interruption-timing window and the `MockLLM` script cursor — does not; a
restart mid-call would lose the ability to correctly classify the very next
interruption and would restart script progression from the persisted
`known_fields`/`objective_status` rather than mid-question. Acceptable for a
single-process local/demo deployment; called out here rather than silently
assumed away. A production deployment would move this into Redis, keyed the
same way.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.providers.mock import MockLLM
from app.turn_manager import TurnManager


@dataclass
class CallRuntime:
    turn_manager: TurnManager
    llm: MockLLM
    language: str
    human_transfer_enabled: bool = True


_REGISTRY: dict[uuid.UUID, CallRuntime] = {}


def put(call_id: uuid.UUID, runtime: CallRuntime) -> None:
    _REGISTRY[call_id] = runtime


def get(call_id: uuid.UUID) -> CallRuntime | None:
    return _REGISTRY.get(call_id)


def discard(call_id: uuid.UUID) -> None:
    _REGISTRY.pop(call_id, None)
