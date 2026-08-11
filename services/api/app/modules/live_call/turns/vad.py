"""P4 — local VAD (spec §7-9). `VADProvider` is a real Protocol specifically
so a neural VAD (Silero or similar) can be substituted later with zero
TurnManager changes — but no such dependency is added in this pass. Checked
before writing this: no Silero/onnxruntime/webrtcvad/LiveKit package exists
anywhere in this repo (see docs/P4_TURN_DETECTION_AUDIT.md). Adding one
properly means model bundling, an ONNX runtime dependency, and real
CPU/latency profiling to satisfy spec §87-88 ("do not block the Twilio
receive loop") — a substantial, separate piece of work, not something to
add speculatively without being able to verify it. `EnergyVAD` below is a
real, working, zero-new-dependency implementation instead: the same
`audioop.rms()` energy-thresholding approach `transitional_bridge.TurnBuffer`
already uses in production, restructured as a proper frame-by-frame VAD
emitting normalized `TurnSignal`s instead of just buffering into one turn.

Deliberately synchronous (`process_frame` is a plain function call, not a
coroutine) — RMS over a ~160-sample 20ms frame is microseconds of pure
arithmetic, so there is no blocking concern and no need for an executor/
worker (spec §88's caution about CPU-heavy VAD doesn't apply to this
implementation; it would apply to a neural one).
"""

from __future__ import annotations

import audioop  # noqa: DEP001 — see audio_codec.py's own module docstring; project pinned to Python 3.12
from dataclasses import dataclass
from typing import Protocol

from app.modules.live_call.turns.signals import TurnSignal, TurnSignalType


@dataclass(frozen=True)
class VADConfig:
    # PCM16 RMS amplitude scale (max 32767) — mirrors
    # transitional_bridge.SILENCE_RMS_THRESHOLD's own documented-as-untuned
    # starting point; real PSTN-audio calibration is still outstanding (see
    # docs/P4_TURN_DETECTION_RESULTS.md).
    activation_threshold: int = 300
    deactivation_threshold: int = 300
    min_speech_duration_ms: int = 200
    min_silence_duration_ms: int = 400
    prefix_padding_ms: int = 100


class VADProvider(Protocol):
    def process_frame(self, frame: bytes, *, sample_rate: int, now: float) -> TurnSignal | None: ...

    def reset(self) -> None: ...


class EnergyVAD:
    """Not a neural VAD — see module docstring. `process_frame` returns a
    signal only on a state TRANSITION (silence->speech or speech->silence),
    never one per frame, so callers don't need to de-duplicate."""

    def __init__(self, config: VADConfig | None = None):
        self.config = config or VADConfig()
        self._is_speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0

    def process_frame(self, frame: bytes, *, sample_rate: int, now: float) -> TurnSignal | None:
        if not frame or sample_rate <= 0:
            return None
        rms = audioop.rms(frame, 2)
        frame_ms = (len(frame) / 2) / sample_rate * 1000
        is_loud = rms >= self.config.activation_threshold

        if is_loud:
            self._speech_ms += frame_ms
            self._silence_ms = 0.0
            if not self._is_speaking and self._speech_ms >= self.config.min_speech_duration_ms:
                self._is_speaking = True
                return TurnSignal(type=TurnSignalType.LOCAL_VAD_SPEECH_START, timestamp=now, source="energy_vad")
        else:
            self._silence_ms += frame_ms
            self._speech_ms = 0.0
            if self._is_speaking and self._silence_ms >= self.config.min_silence_duration_ms:
                self._is_speaking = False
                return TurnSignal(type=TurnSignalType.LOCAL_VAD_SPEECH_END, timestamp=now, source="energy_vad")
        return None

    def reset(self) -> None:
        self._is_speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
