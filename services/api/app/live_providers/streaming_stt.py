"""Transport-independent streaming STT contract — the seam that keeps
`app.modules.live_call.transport.streaming_bridge` (and, in future, any
non-Sarvam provider) decoupled from Sarvam's specific WebSocket wire
schema. Lives in `live_providers/`, not `transport/`, because it's an
AI-provider concern (parallel to `sarvam_stt.py`/`sarvam_tts.py`), not a
Twilio/Media-Streams concern — a `StreamingSTTProvider` never sees
Twilio's JSON, only normalized PCM16 bytes in and typed events out.

Event fields that a provider does not supply are always `None`, never
manufactured — e.g. Sarvam's Realtime API never emits a transcription
confidence score at all (see docs/SARVAM_STREAMING_STT_CONTRACT.md), so
`FinalTranscript.provider_confidence` is always `None` for that provider,
not a fabricated placeholder value.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel


class StreamingSTTConfig(BaseModel):
    """What a caller asks a streaming STT session to do. Field names/values
    mirror Sarvam's Realtime API query params directly (see contract doc)
    since it's the only provider today, but nothing here is Sarvam-specific
    naming — a future provider adapter would translate this shape into its
    own wire format, same as `StreamingSTTConfig` -> Sarvam query string
    translation happens entirely inside `sarvam_streaming_stt.py`."""

    language_code: str  # pinned, e.g. "te-IN" — never "auto" (see sarvam_stt.py's own "never unknown" policy)
    mode: Literal["transcribe", "translate", "verbatim", "translit", "codemix"] = "codemix"
    stream_type: Literal["fast", "balanced", "simulated"] = "fast"
    encoding: Literal["linear16", "linear32", "mulaw", "alaw"] = "linear16"
    sample_rate: Literal[8000, 16000] = 8000
    endpointing: Literal["vad", "manual"] = "vad"
    return_timestamps: bool = False
    prompt: str | None = None
    threshold: float = 0.3
    prefix_padding_ms: int = 300
    silence_duration_ms: int = 500
    min_speech_duration_ms: int = 250


@dataclass(frozen=True)
class STTCapabilities:
    """What a given provider/config combination actually supports —
    checked explicitly by callers rather than assumed, so a future
    lower-capability provider degrades visibly instead of silently."""

    supports_partial_transcripts: bool
    supports_vad_events: bool
    supports_live_reconfiguration: bool
    supports_flush: bool
    supports_provider_confidence: bool
    supports_code_mix: bool
    supports_pronunciation_dictionary: bool


# --- event model -------------------------------------------------------
# Deliberately plain frozen dataclasses, not a tagged union library — the
# caller pattern-matches on type, matching how TwilioXxxEvent is consumed
# in transport/schemas.py. `raw` always carries the untouched provider
# payload for debugging, never parsed a second time downstream.


@dataclass(frozen=True)
class STTSessionStarted:
    request_id: str | None
    raw: dict


@dataclass(frozen=True)
class STTSessionEnded:
    request_id: str | None
    total_duration_s: float | None
    total_utterances: int | None
    audio_duration_s: float | None
    raw: dict


@dataclass(frozen=True)
class SpeechStarted:
    utterance_idx: int | None
    provider_confidence: float | None
    raw: dict


@dataclass(frozen=True)
class SpeechEnded:
    utterance_idx: int | None
    provider_confidence: float | None
    raw: dict


@dataclass(frozen=True)
class PartialTranscript:
    utterance_idx: int | None
    text: str
    detected_language_code: str | None
    raw: dict


@dataclass(frozen=True)
class FinalTranscript:
    utterance_idx: int | None
    text: str
    detected_language_code: str | None
    language_probability: float | None
    start_s: float | None
    end_s: float | None
    provider_confidence: float | None  # always None for Sarvam — see module docstring
    raw: dict


@dataclass(frozen=True)
class STTReconfigured:
    raw: dict


@dataclass(frozen=True)
class STTError:
    code: str | None
    message: str
    is_fatal: bool
    status_code: int | None
    raw: dict


STTEvent = (
    STTSessionStarted
    | STTSessionEnded
    | SpeechStarted
    | SpeechEnded
    | PartialTranscript
    | FinalTranscript
    | STTReconfigured
    | STTError
)


class StreamingSTTProvider(Protocol):
    """One instance = one persistent session for one call. Never owns
    ConversationEngine/RAG/domain correction/business state/planner —
    `streaming_bridge.py` is the only caller, and it's the only place a
    `FinalTranscript` event ever gets handed to
    `jkr_conversation.engine.process_turn()`."""

    @property
    def capabilities(self) -> STTCapabilities: ...

    async def connect(self) -> None: ...

    async def send_audio(self, pcm16_bytes: bytes) -> None: ...

    def events(self) -> AsyncIterator[STTEvent]: ...

    async def flush(self) -> None: ...

    async def reconfigure(self, **kwargs: object) -> None: ...

    async def close(self) -> None: ...
