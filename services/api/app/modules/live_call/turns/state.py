"""P4 — the explicit turn state machine (spec §5). Deliberately not
enforced via a hard transition-validation table the way
transport/base.py's `MediaSessionStatus` is: that table exists because
Twilio's wire protocol genuinely only allows a fixed sequence, and
violating it is a real protocol bug. Turn detection is inherently more
fluid — multiple simultaneous signals (a new final arriving mid-timer, a
resume during POSSIBLE_END) legitimately move between non-adjacent states
depending on evidence, not a fixed sequence. `TurnManager` (manager.py) is
what actually enforces correctness (never committing without evidence,
never waiting past max_endpoint_delay_ms); this module only names the
states and documents the intended shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TurnState(StrEnum):
    IDLE = "idle"
    USER_SPEECH_STARTING = "user_speech_starting"
    USER_SPEAKING = "user_speaking"
    USER_PAUSED = "user_paused"
    POSSIBLE_END = "possible_end"
    WAITING_FOR_CONTINUATION = "waiting_for_continuation"
    TURN_READY = "turn_ready"
    TURN_COMMITTED = "turn_committed"


class TurnDecision(StrEnum):
    WAIT = "wait"
    USER_STARTED = "user_started"
    USER_CONTINUING = "user_continuing"
    MAYBE_END = "maybe_end"
    COMMIT_TURN = "commit_turn"
    CANCEL_PENDING_COMMIT = "cancel_pending_commit"


@dataclass(frozen=True)
class TranscriptSegment:
    """One STT final belonging to (possibly) a larger logical turn — see
    manager.py's coalescing logic (spec §25-27)."""

    text: str
    utterance_idx: int | None
    received_at: float


@dataclass(frozen=True)
class UserTurnCommitted:
    """Spec §35 — the one payload TurnManager ever hands to the caller for
    routing into ConversationEngine. `final_segments` is the full,
    uncoalesced evidence trail; `text` is the single coalesced string
    process_known_transcript_turn() actually receives."""

    call_session_id: object
    turn_id: str
    text: str
    language_code: str
    speech_started_at: float | None
    speech_ended_at: float | None
    committed_at: float
    final_segments: list[TranscriptSegment]
    endpoint_reason: str
    endpoint_confidence: float


# Endpoint reasons (spec §36) — used for observability, never branches logic.
ENDPOINT_REASON_PROVIDER_ONLY = "provider_only"
ENDPOINT_REASON_SEMANTIC_COMPLETE = "semantic_complete"
ENDPOINT_REASON_VAD_SILENCE_COMPLETE = "vad_silence_complete"
ENDPOINT_REASON_MAX_TIMEOUT = "max_endpoint_timeout"
ENDPOINT_REASON_CALL_ENDING = "call_ending"


@dataclass
class TurnTraceEntry:
    offset_ms: int
    event: str
    detail: str = ""


@dataclass
class TurnDebugTrace:
    """Spec §51 — an in-memory, per-turn trace, never persisted to Postgres
    (spec §52: high-volume signals stay in logs/metrics, not the DB).
    Reset after every commit so it never grows unbounded across a long call."""

    entries: list[TurnTraceEntry] = field(default_factory=list)
    _start: float | None = field(default=None, repr=False)

    def record(self, event: str, *, now: float, detail: str = "") -> None:
        if self._start is None:
            self._start = now
        self.entries.append(TurnTraceEntry(offset_ms=int((now - self._start) * 1000), event=event, detail=detail))

    def reset(self) -> None:
        self.entries = []
        self._start = None

    def render(self) -> str:
        return "\n".join(f"{e.offset_ms:>5d}ms {e.event}{(' ' + e.detail) if e.detail else ''}" for e in self.entries)
