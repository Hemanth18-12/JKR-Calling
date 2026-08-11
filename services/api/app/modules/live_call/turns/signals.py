"""P4 — normalized turn-detection signal model. Every evidence source
(Sarvam's provider VAD events, local energy VAD, STT partial/final text,
semantic-completeness evaluation, backchannel classification, timers) is
translated into one of these before TurnManager ever sees it — the whole
point being that TurnManager (manager.py) never has provider-specific
logic embedded in it (spec §6: "Do not hardcode logic directly into the
Sarvam adapter").

`timestamp` is always caller-supplied (`time.monotonic()` in production,
an incrementing fake counter in tests) — TurnManager and everything in this
package is deliberately synchronous and never reads the clock itself, so
tests never need to sleep for real (spec §110/§111).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TurnSignalType(StrEnum):
    LOCAL_VAD_SPEECH_START = "local_vad_speech_start"
    LOCAL_VAD_SPEECH_END = "local_vad_speech_end"

    PROVIDER_SPEECH_START = "provider_speech_start"
    PROVIDER_SPEECH_END = "provider_speech_end"

    STT_PARTIAL = "stt_partial"
    STT_FINAL = "stt_final"

    SEMANTIC_COMPLETE = "semantic_complete"
    SEMANTIC_INCOMPLETE = "semantic_incomplete"

    BACKCHANNEL = "backchannel"
    CUSTOMER_RESUMED = "customer_resumed"

    SILENCE_TIMER = "silence_timer"
    MAX_ENDPOINT_WAIT = "max_endpoint_wait"


@dataclass(frozen=True)
class TurnSignal:
    type: TurnSignalType
    timestamp: float  # monotonic seconds, caller-supplied
    confidence: float | None = None
    source: str = ""  # "energy_vad" | "sarvam" | "semantic" | "backchannel" | "timer"
    text: str | None = None  # populated for STT_PARTIAL/STT_FINAL
    utterance_idx: int | None = None
