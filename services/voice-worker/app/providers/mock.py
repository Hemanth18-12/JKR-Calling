"""Mock transport adapters — the default for every workspace (spec §2 rules
19-20, docs/DECISIONS/0002-voice-runtime.md). No credentials, no network
calls, no cost. `MockSTT`/`MockTTS`/`MockTelephony`/`MockMediaRuntime` satisfy
the Protocols in `base.py` directly.

The conversation-intelligence mock that used to live here (`MockLLM`,
`MOCK_SCRIPTS`, per-objective canned closings) has moved to
`jkr_conversation.objectives`/`jkr_conversation.extractor`/`jkr_conversation.prompt_builder`
— it's shared conversation logic, not a transport concern, and is now used
identically by both this Test Lab path and the real Twilio call path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.providers.base import (
    CallHandle,
    CallStatusInfo,
    MediaSession,
    SynthesisResult,
    TranscriptResult,
    VoiceConfig,
)


@dataclass
class MockSTT:
    async def transcribe(self, *, audio_or_text: str, language: str) -> TranscriptResult:
        # Text-simulated: the "audio" already is the text. Confidence is
        # deliberately imperfect-looking (not always 1.0) so downstream
        # confidence-threshold logic has something real to react to.
        confidence = 0.97 if len(audio_or_text.strip()) > 2 else 0.6
        return TranscriptResult(text=audio_or_text.strip(), confidence=confidence, language=language, is_final=True)


@dataclass
class MockTTS:
    async def synthesize(self, *, text: str, voice: VoiceConfig) -> SynthesisResult:
        from app.turn_manager import estimate_speaking_duration_ms

        return SynthesisResult(audio_duration_ms=estimate_speaking_duration_ms(text), is_simulated=True)

    async def stop(self, *, session_id: str) -> None:
        return None


@dataclass
class MockTelephony:
    async def create_outbound_call(self, *, to: str, from_: str, context: dict) -> CallHandle:
        return CallHandle(provider_call_ref=f"mock-call-{uuid.uuid4()}", raw={"to": to, "from": from_})

    async def accept_inbound_call(self, *, call_ref: str) -> CallHandle:
        return CallHandle(provider_call_ref=call_ref)

    async def end_call(self, *, call_ref: str) -> None:
        return None

    async def transfer_call(self, *, call_ref: str, target: str) -> None:
        return None

    async def get_call_status(self, *, call_ref: str) -> CallStatusInfo:
        return CallStatusInfo(status="completed")


@dataclass
class MockMediaRuntime:
    sessions: dict[str, MediaSession] = field(default_factory=dict)

    async def create_session(self, *, call_id: str) -> MediaSession:
        session = MediaSession(session_id=f"mock-media-{call_id}")
        self.sessions[call_id] = session
        return session

    async def publish_audio(self, *, session: MediaSession, chunk: bytes) -> None:
        return None

    async def cancel_output(self, *, session: MediaSession) -> None:
        return None
