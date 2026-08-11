"""Transport-independent streaming TTS contract — the seam that keeps
`app.modules.live_call.transport.tts_bridge` (and any future non-Sarvam
provider) decoupled from Sarvam's specific WebSocket wire schema. Lives in
`live_providers/`, not `transport/`, mirroring `streaming_stt.py`'s exact
reasoning: this is an AI-provider concern, parallel to `sarvam_tts.py`
(batch) / `sarvam_streaming_stt.py`.

`response_id` is OUR OWN identifier (P5's `SpeakableChunk.response_id`,
reused end-to-end rather than inventing a second parallel id), not
anything Sarvam gives us — a real, empirically-confirmed gap this exists
to cover: Sarvam's own `request_id` is scoped to the WHOLE WebSocket
connection, not to an individual text/flush cycle (see
docs/SARVAM_STREAMING_TTS_CONTRACT.md's "CRITICAL empirical finding").
Every event below carries `response_id` so a caller reusing one
connection across many agent turns can always tell which turn a given
audio chunk belongs to.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class StreamingTTSConfig(BaseModel):
    """What a caller asks a streaming TTS session to do. Field names mirror
    Sarvam's streaming config message directly (see contract doc) since
    it's the only provider today — same precedent StreamingSTTConfig set."""

    model: str = "bulbul:v3"
    voice_id: str | None = None  # None -> provider's own default speaker, same policy as SarvamTTS
    target_language_code: str
    pace: float = 1.0
    temperature: float | None = None
    pronunciation_dictionary_id: str | None = None  # verified real, not wired into any provider this pass — see §65
    output_sample_rate: int = 8000  # Twilio's own fixed rate — see audio_codec.py


class TTSCallContext(BaseModel):
    """Per-call identity, kept separate from StreamingTTSConfig (which is
    pure synthesis configuration) — used for logging/usage accounting."""

    call_session_id: str
    workspace_id: str


@dataclass(frozen=True)
class TTSCapabilities:
    """What a given provider/config combination actually supports — checked
    explicitly by callers, so a lower-capability provider degrades visibly
    instead of silently. Same reasoning as STTCapabilities."""

    supports_streaming_input: bool
    supports_streaming_audio: bool
    supports_flush: bool
    supports_completion_event: bool
    supports_live_reconfiguration: bool
    supports_pronunciation_dictionary: bool
    supports_direct_mulaw_8k: bool
    supports_cancel: bool


class TTSFailureClass(StrEnum):
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    PROVIDER_INTERNAL = "provider_internal"
    INVALID_REQUEST = "invalid_request"
    STREAM_INTERRUPTED = "stream_interrupted"
    UNKNOWN = "unknown"


# --- event model ---------------------------------------------------------
# Deliberately plain frozen dataclasses, not a tagged union library — same
# pattern streaming_stt.py/streaming_llm.py (packages/conversation) already use.


@dataclass(frozen=True)
class TTSSessionStarted:
    raw: dict


@dataclass(frozen=True)
class TTSTextAccepted:
    response_id: str
    chunk_index: int


@dataclass(frozen=True)
class TTSFirstAudio:
    response_id: str


@dataclass(frozen=True)
class TTSAudioChunk:
    response_id: str
    audio_chunk_index: int
    data: bytes  # exactly what the provider sent, undecoded beyond base64 — see capabilities for format
    content_type: str | None
    codec: str | None
    sample_rate: int | None
    is_final: bool = False


@dataclass(frozen=True)
class TTSGenerationCompleted:
    response_id: str


@dataclass(frozen=True)
class TTSStreamFailed:
    response_id: str | None
    failure_class: TTSFailureClass
    message: str


@dataclass(frozen=True)
class TTSStreamCancelled:
    response_id: str


@dataclass(frozen=True)
class TTSSessionClosed:
    raw: dict | None = None


TTSStreamEvent = (
    TTSSessionStarted
    | TTSTextAccepted
    | TTSFirstAudio
    | TTSAudioChunk
    | TTSGenerationCompleted
    | TTSStreamFailed
    | TTSStreamCancelled
    | TTSSessionClosed
)


class StreamingTTSProvider(Protocol):
    """One instance = one persistent session for the lifetime of one call
    (spec §14/§48: connect once, reuse across many agent turns, close at
    call end) — never reconnected per response or per chunk."""

    @property
    def capabilities(self) -> TTSCapabilities: ...

    async def connect(self, *, config: StreamingTTSConfig, context: TTSCallContext) -> None: ...

    async def send_text(self, *, text: str, response_id: str, chunk_index: int) -> None: ...

    async def flush(self, *, response_id: str) -> None: ...

    def events(self) -> AsyncIterator[TTSStreamEvent]: ...

    async def cancel(self, response_id: str) -> None: ...

    async def close(self) -> None: ...
