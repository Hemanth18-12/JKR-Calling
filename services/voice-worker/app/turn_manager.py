"""TurnManager — spec §11.

Real-time audio would drive this off VAD frames; the text-simulated
transport (docs/DECISIONS/0002-voice-runtime.md) drives it off wall-clock
time instead: an agent turn's "speaking" window is a simulated duration
computed from the formatted text length, and a user utterance arriving
before that window elapses is a candidate interruption. The classification
logic below (phrase-list + word-count + timing) is the real thing the spec
asks for — only the audio-duration measurement is simulated, not the
decision logic itself.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

# ~2.7 words/sec is a natural, slightly deliberate speaking pace for
# Telugu/Hindi-English code-switched speech; tuned for demo believability,
# not measured against a real TTS engine (there isn't one in mock mode).
MS_PER_CHAR = 55
AGENT_TURN_BASE_LATENCY_MS = 250  # simulated "time to first audio"

# A user utterance shorter than this, whose full text is in the phrase list,
# is treated as a filler acknowledgement rather than a real interruption.
FALSE_INTERRUPTION_MAX_WORDS = 3


class InterruptionClassification(StrEnum):
    MEANINGFUL = "meaningful"
    FALSE_POSITIVE = "false_positive"
    NONE = "none"  # no agent turn was in flight; not an interruption at all


@dataclass
class ClassifiedUtterance:
    classification: InterruptionClassification
    stop_latency_ms: int | None
    cancelled_sequence_id: str | None


@dataclass
class AgentTurnRecord:
    sequence_id: str
    turn_ref: str
    text: str
    started_at: float
    expected_end_at: float
    cancelled: bool = False
    cancelled_at: float | None = None


def estimate_speaking_duration_ms(formatted_text: str) -> int:
    return AGENT_TURN_BASE_LATENCY_MS + max(len(formatted_text), 1) * MS_PER_CHAR


@dataclass
class TurnManager:
    call_id: uuid.UUID
    accidental_interruption_phrases: list[str] = field(default_factory=list)
    min_interruption_ms: int = 250

    user_speaking: bool = False
    agent_speaking: bool = False
    active_turn: AgentTurnRecord | None = None
    turn_counter: int = 0
    user_interruption_count: int = 0
    false_interruption_count: int = 0
    recovery_count: int = 0
    last_user_stop_at: float | None = None

    def next_turn_ref(self, prefix: str) -> str:
        self.turn_counter += 1
        return f"{prefix}-{self.turn_counter}"

    def start_agent_turn(self, formatted_text: str, *, now: float | None = None) -> AgentTurnRecord:
        now = now if now is not None else time.monotonic()
        duration_ms = estimate_speaking_duration_ms(formatted_text)
        record = AgentTurnRecord(
            sequence_id=str(uuid.uuid4()),
            turn_ref=self.next_turn_ref("agent"),
            text=formatted_text,
            started_at=now,
            expected_end_at=now + duration_ms / 1000,
        )
        self.active_turn = record
        self.agent_speaking = True
        return record

    def _is_false_interruption(self, text: str) -> bool:
        normalized = text.strip().lower()
        if not normalized:
            return True
        word_count = len(normalized.split())
        if word_count > FALSE_INTERRUPTION_MAX_WORDS:
            return False
        return any(normalized == phrase.strip().lower() for phrase in self.accidental_interruption_phrases)

    def handle_user_utterance(self, text: str, *, now: float | None = None) -> ClassifiedUtterance:
        """Call this for every user turn. Returns the interruption
        classification (NONE if the agent wasn't mid-turn at all)."""
        now = now if now is not None else time.monotonic()

        if not self.agent_speaking or self.active_turn is None:
            return ClassifiedUtterance(InterruptionClassification.NONE, None, None)

        turn = self.active_turn
        if now >= turn.expected_end_at:
            # The simulated speaking window already elapsed naturally —
            # the agent finished before the user spoke; not an interruption.
            self.agent_speaking = False
            return ClassifiedUtterance(InterruptionClassification.NONE, None, None)

        elapsed_ms = (now - turn.started_at) * 1000
        if self._is_false_interruption(text) or elapsed_ms < self.min_interruption_ms:
            self.false_interruption_count += 1
            return ClassifiedUtterance(InterruptionClassification.FALSE_POSITIVE, None, None)

        # Meaningful interruption: cancel the in-flight turn.
        turn.cancelled = True
        turn.cancelled_at = now
        self.agent_speaking = False
        self.user_interruption_count += 1
        stop_latency_ms = max(int((now - turn.started_at) * 1000 * 0.01), 30)  # near-instant in mock mode
        return ClassifiedUtterance(
            InterruptionClassification.MEANINGFUL, stop_latency_ms, turn.sequence_id
        )

    def mark_recovered(self) -> None:
        self.recovery_count += 1
