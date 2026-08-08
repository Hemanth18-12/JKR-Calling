"""Provider interfaces — spec §10.1. Every real adapter (Twilio, Deepgram,
OpenAI, ElevenLabs, ...) and every mock implements these Protocols, so
`voice-worker`'s conversation engine and TurnManager never know which
concrete provider they're talking to. See docs/VOICE_ARCHITECTURE.md §2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


class NotConfiguredError(RuntimeError):
    """Raised by a real (non-mock) adapter when required credentials are
    absent — see docs/VOICE_ARCHITECTURE.md §2. Callers should catch this and
    fall back per the provider router's fallback policy (spec §10.3),
    logging a `provider_fallback` call_event."""


@dataclass
class CallHandle:
    provider_call_ref: str
    raw: dict = field(default_factory=dict)


@dataclass
class CallStatusInfo:
    status: str
    raw: dict = field(default_factory=dict)


class TelephonyProvider(Protocol):
    async def create_outbound_call(self, *, to: str, from_: str, context: dict) -> CallHandle: ...
    async def accept_inbound_call(self, *, call_ref: str) -> CallHandle: ...
    async def end_call(self, *, call_ref: str) -> None: ...
    async def transfer_call(self, *, call_ref: str, target: str) -> None: ...
    async def get_call_status(self, *, call_ref: str) -> CallStatusInfo: ...


@dataclass
class TranscriptResult:
    text: str
    confidence: float
    language: str
    is_final: bool = True


class SpeechToTextProvider(Protocol):
    """Real implementations stream audio frames; MockSTT (app/providers/mock.py)
    takes typed text directly — see docs/DECISIONS/0002-voice-runtime.md."""

    async def transcribe(self, *, audio_or_text: str, language: str) -> TranscriptResult: ...


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass
class Token:
    text: str
    is_final: bool = False


class LLMProvider(Protocol):
    def stream_response(self, *, messages: list[Message], context: dict) -> AsyncIterator[Token]: ...
    async def generate_structured_output(self, *, prompt: str, schema_hint: dict) -> dict: ...


@dataclass
class VoiceConfig:
    provider: str
    voice_id: str
    language: str
    speaking_speed: float = 1.0
    stability: float = 0.6
    expressiveness: float = 0.6


@dataclass
class SynthesisResult:
    audio_duration_ms: int
    is_simulated: bool = True


class TextToSpeechProvider(Protocol):
    async def synthesize(self, *, text: str, voice: VoiceConfig) -> SynthesisResult: ...
    async def stop(self, *, session_id: str) -> None: ...


@dataclass
class MediaSession:
    session_id: str


class MediaRuntime(Protocol):
    async def create_session(self, *, call_id: str) -> MediaSession: ...
    async def publish_audio(self, *, session: MediaSession, chunk: bytes) -> None: ...
    async def cancel_output(self, *, session: MediaSession) -> None: ...
