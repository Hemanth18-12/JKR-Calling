"""BATCH STT bridge — bridges continuous Media Stream audio onto the
batch STT / ConversationEngine / TTS pipeline: the exact same
SarvamSTT.transcribe(), jkr_conversation.engine.process_turn(), and
SarvamTTS.synthesize() calls the <Record> path already uses, reused
directly here rather than reimplemented — per spec §2/§3, conversation
intelligence must not be duplicated between transports, only triggered
differently.

This buffers inbound PCM16 audio in memory and uses simple trailing-
silence energy detection to decide when a turn has ended — deliberately
NOT real VAD (spec §31: "Do NOT make aggressive VAD changes yet... P4 will
implement proper VAD endpointing"). TRAILING_SILENCE_SECONDS mirrors
service.py's RECORD_SILENCE_TIMEOUT_SECONDS for consistency.

_SILENCE_RMS_THRESHOLD is a first-pass heuristic (PCM16 amplitude scale,
max 32767) that has NOT been tuned against real phone-line audio — flagged
explicitly in docs/TWILIO_MEDIA_STREAMS.md as needing real-call
calibration, not presented as a measured constant.

P3 (docs/SARVAM_STREAMING_STT_CONTRACT.md,
app/modules/live_call/transport/streaming_bridge.py) adds real streaming
STT (partial + final transcripts, no turn buffering) as the default when
`STT_MODE=streaming`. This module is kept, not deleted, as the explicit
`STT_STREAM_FAILURE_POLICY=batch_next_turn` fallback and as the permanent
implementation for `STT_MODE=batch`. `process_known_transcript_turn()`
below — everything after a transcript exists (persist, engine, tools,
reply) — is shared with the streaming path so that logic is never
duplicated between the two STT modes.
"""

from __future__ import annotations

import audioop  # noqa: DEP001 — see audio_codec.py's module docstring; project pinned to Python 3.12
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from jkr_conversation.engine import process_turn
from jkr_conversation.schemas import ConversationPolicySnapshot
from jkr_conversation.streaming_response import CancellationToken, SpeakableChunk
from jkr_db.models.calls import CallSession
from jkr_db.tools_engine import ToolNotDefinedError, ToolNotEnabledError, execute_tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.live_providers.sarvam_stt import SarvamSTT
from app.live_providers.sarvam_tts import SarvamTTS
from app.modules.live_call.transport.audio_codec import pcm16_to_wav_bytes, wav_bytes_to_pcm16
from app.modules.live_call.transport.base import AudioFrame
from app.modules.live_call.transport.coordinator import CoordinatedResponseHandle
from app.modules.live_call.transport.events import log_event
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import chunk_text_for_tts

TRAILING_SILENCE_SECONDS = 4.0  # mirrors service.py's RECORD_SILENCE_TIMEOUT_SECONDS
MAX_TURN_SECONDS = 20.0  # mirrors <Record>'s maxLength="20"
MIN_SPEECH_MS_TO_COUNT = 300  # a turn with less non-silent audio than this isn't treated as a real reply
SILENCE_RMS_THRESHOLD = 300  # heuristic — see module docstring; needs real-call tuning


@dataclass
class TurnBuffer:
    """One customer turn's worth of accumulated inbound audio. Not
    thread/task-safe by design — exactly one processing task per session
    owns this (spec §17's "processing loop" task), matching how the
    inbound queue itself is only ever drained by that same task."""

    sample_rate: int = 8000
    _pcm16_chunks: list[bytes] = field(default_factory=list)
    trailing_silence_ms: float = 0.0
    speech_ms: float = 0.0
    total_ms: float = 0.0

    def add_frame(self, frame: AudioFrame) -> None:
        self.sample_rate = frame.sample_rate
        self._pcm16_chunks.append(frame.data)
        frame_ms = (len(frame.data) / 2) / frame.sample_rate * 1000 if frame.sample_rate else 0.0
        self.total_ms += frame_ms
        rms = audioop.rms(frame.data, 2) if frame.data else 0
        if rms < SILENCE_RMS_THRESHOLD:
            self.trailing_silence_ms += frame_ms
        else:
            self.trailing_silence_ms = 0.0
            self.speech_ms += frame_ms

    def is_turn_complete(self) -> bool:
        if self.total_ms >= MAX_TURN_SECONDS * 1000:
            return self.has_speech()  # a maxed-out buffer of pure silence isn't a "turn," just nothing said yet
        return self.has_speech() and self.trailing_silence_ms >= TRAILING_SILENCE_SECONDS * 1000

    def has_speech(self) -> bool:
        return self.speech_ms >= MIN_SPEECH_MS_TO_COUNT

    def is_over_max_duration(self) -> bool:
        return self.total_ms >= MAX_TURN_SECONDS * 1000

    def build_wav(self) -> bytes:
        return pcm16_to_wav_bytes(b"".join(self._pcm16_chunks), sample_rate=self.sample_rate)

    def reset(self) -> None:
        self._pcm16_chunks.clear()
        self.trailing_silence_ms = 0.0
        self.speech_ms = 0.0
        self.total_ms = 0.0


@dataclass(frozen=True)
class TurnResult:
    reply_text: str
    force_close: bool
    had_speech: bool


async def synthesize_for_stream(
    text: str, *, language_code: str, settings: Settings, speaker: str | None
) -> tuple[bytes, int] | None:
    """Returns (pcm16_mono_bytes, sample_rate), or None if Sarvam TTS
    failed. Unlike service.py's _speak(), there is no Twilio <Say>
    fallback available here — once a Media Stream call is underway there's
    no further TwiML round-trip to fall back into. A None here means the
    caller (the WebSocket handler) ends the call gracefully rather than
    leaving the customer in silence (spec §72: "Do not leave caller in
    silence indefinitely") — a documented P2 limitation, not a silent gap;
    see docs/TWILIO_MEDIA_STREAMS.md's Known Limitations section."""
    try:
        tts = SarvamTTS(api_key=settings.sarvam_tts_api_key or settings.sarvam_api_key, **({"speaker": speaker} if speaker else {}))
        wav_bytes = await tts.synthesize(text=text, language_code=language_code)
    except Exception:  # noqa: BLE001 — see docstring; caller handles None explicitly
        return None
    pcm16_bytes, sample_rate, _channels = wav_bytes_to_pcm16(wav_bytes)
    return pcm16_bytes, sample_rate


@dataclass(frozen=True)
class SpokenReplyOutcome:
    mark_name: str | None
    fatal_failure: bool  # True: nothing could be spoken at all (streaming AND batch fallback both failed) — caller's existing "reply_tts_failed" policy applies
    # P10 — surfaces TTSTurnOutcome.first_audio_ms (already computed inside
    # tts_bridge.py's _finish_response, previously discarded at this exact
    # boundary) so the real-call benchmark harness can persist
    # tts_stream_first_audio_ms as part of the turn latency waterfall (see
    # docs/P10_REAL_CALL_BENCHMARK.md). None under the batch path (no
    # equivalent measurement exists there) or when no audio was ever produced.
    first_audio_ms: int | None = None


async def speak_turn_reply(
    *, reply_text: str, session: RealtimeMediaSession, language_code: str, settings: Settings, speaker: str | None,
    response_handle: CoordinatedResponseHandle | None, callback_fired: bool,
) -> SpokenReplyOutcome:
    """The one place a turn's reply text actually becomes audio, shared by
    both turn loops (batch and streaming-STT) — P6 unifies what used to be
    two separate inline synthesize_for_stream()+_send_pcm_reply() blocks
    per loop into this single function so the streaming-TTS-with-batch-
    fallback policy only needs to be implemented (and tested) once.

    `response_handle` is None under TTS_MODE=batch (or when no
    TTSStreamingSession exists for this call) — falls straight to the
    original batch REST path, byte-identical to pre-P6 behavior.

    `callback_fired` tells this function whether reply_text was already
    spoken via on_speakable_chunk during process_turn() (an LLM-streamed
    response) — if so, feeding reply_text again would double-speak it, so
    only chunk-and-feed reply_text locally when the callback never fired
    (canned/fast-path/COMPLETE_OBJECTIVE/LLM_RESPONSE_MODE=complete —
    spec §62-64: these still get the "audio before full synthesis" benefit,
    just via local chunking of the already-fully-formatted text)."""
    if not reply_text:
        return SpokenReplyOutcome(mark_name=None, fatal_failure=False)

    if response_handle is not None:
        if not callback_fired:
            for chunk_text in chunk_text_for_tts(reply_text):
                await response_handle.send_chunk(chunk_text)
        outcome = await response_handle.finish()
        if not outcome.failed:
            return SpokenReplyOutcome(mark_name=outcome.final_mark_name, fatal_failure=False, first_audio_ms=outcome.first_audio_ms)
        if outcome.chunks_sent > 0:
            # spec §72 — partial audio already delivered to the customer;
            # never automatically replay what's already been heard. The
            # safest acceptable P6 behavior: stop here, let the call
            # continue on the next turn rather than attempting a recovery
            # utterance that risks repeating content.
            log_event(
                "tts_stream_failed_after_partial_audio", call_session_id=session.call_session_id,
                response_id=outcome.response_id, chunks_sent=outcome.chunks_sent, failure_message=outcome.failure_message,
            )
            return SpokenReplyOutcome(mark_name=outcome.final_mark_name, fatal_failure=False, first_audio_ms=outcome.first_audio_ms)
        log_event(
            "tts_stream_failed_before_audio_falling_back_to_batch", call_session_id=session.call_session_id,
            response_id=outcome.response_id, failure_message=outcome.failure_message,
        )
        # falls through to the batch path below — spec §71

    from app.modules.live_call.transport.twilio_media_stream import (
        _send_pcm_reply,  # local import: avoids a circular import (twilio_media_stream.py imports this module)
    )

    synthesized = await synthesize_for_stream(reply_text, language_code=language_code, settings=settings, speaker=speaker)
    if synthesized is None:
        return SpokenReplyOutcome(mark_name=None, fatal_failure=True)
    mark_name = await _send_pcm_reply(session, pcm16_bytes=synthesized[0], sample_rate=synthesized[1])
    return SpokenReplyOutcome(mark_name=mark_name, fatal_failure=False)


async def process_transitional_turn(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    call_session_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    wav_bytes: bytes,
    redis_state: dict,
    settings: Settings,
    language_code: str,
    on_speakable_chunk: Callable[[SpeakableChunk], Awaitable[None]] | None = None,
    cancellation_token: CancellationToken | None = None,
) -> TurnResult:
    """Runs the SAME STT -> process_turn -> tool-execution -> reply
    pipeline service.py:handle_recording_webhook uses, just triggered by
    the transitional turn buffer instead of a Twilio recording callback.
    Imports _record_latency/_end_reason_for/_persist_turn from service.py
    rather than reimplementing them — same functions, same CallLatencyMetric/
    CallTurn/CallEvent rows either transport produces.

    Only responsible for the STT step itself — everything after a
    transcript exists is shared with the P3 streaming path via
    process_known_transcript_turn() below, so the engine/tool/reply
    pipeline is never duplicated between batch and streaming STT."""
    from app.modules.live_call.service import (
        _record_latency,  # local import: avoids a circular import
    )

    t0 = time.perf_counter()
    stt = SarvamSTT(api_key=settings.sarvam_api_key or settings.sarvam_tts_api_key)
    transcript = await stt.transcribe(audio_bytes=wav_bytes, language_code=language_code)
    await _record_latency(
        db, workspace_id=workspace_id, call_session_id=call_session_id, stage="stt_transcribe",
        duration_ms=int((time.perf_counter() - t0) * 1000), provider="sarvam",
    )

    speech_result = transcript.text
    if not speech_result:
        return TurnResult(reply_text="", force_close=False, had_speech=False)

    stt_metadata = {
        "stt_detected_language_code": transcript.detected_language_code,
        "stt_language_probability": transcript.language_probability,
        "stt_requested_language_code": language_code,
    }
    return await process_known_transcript_turn(
        db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
        speech_result=speech_result, stt_metadata=stt_metadata, redis_state=redis_state, settings=settings,
        on_speakable_chunk=on_speakable_chunk, cancellation_token=cancellation_token,
    )


async def process_known_transcript_turn(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    call_session_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    speech_result: str,
    stt_metadata: dict,
    redis_state: dict,
    settings: Settings,
    on_speakable_chunk: Callable[[SpeakableChunk], Awaitable[None]] | None = None,
    cancellation_token: CancellationToken | None = None,
) -> TurnResult:
    """The shared second half of a turn: persist the customer's utterance,
    run it through the real ConversationEngine (extraction, domain
    correction, RAG, planning, generation — completely unaware of which
    STT path produced this text), execute any requested tools, persist and
    return the agent's reply. Called by process_transitional_turn() above
    (batch STT already has the transcript) and by streaming_bridge.py's
    FinalTranscript handler (streaming STT already has the transcript) —
    the one place this logic lives, so P3 never duplicates it.

    P6 — `on_speakable_chunk`, when given, is forwarded straight into
    process_turn() so a caller with a TTSStreamingSession can feed audio in
    real time while the LLM is still generating (see tts_bridge.py). Only
    ever actually invoked when settings.llm_response_mode == "streaming"
    AND the turn reaches free generation (see prompt_builder.generate()'s
    own structural early-returns) — a no-op parameter otherwise.

    P9 — `cancellation_token`, when given (the coordinator response's own
    token — see coordinator.ResponseFeed), is forwarded the same way so
    StreamingResponseAssembler stops consuming a stale generation's own LLM
    stream the moment this response is cancelled/superseded/interrupted,
    independent of whether the surrounding asyncio task is ever explicitly
    cancelled (see docs/REPLAY_PROTECTION_ARCHITECTURE.md)."""
    from app.modules.live_call.service import (  # local import: avoids a circular import
        _end_reason_for,
        _persist_turn,
        _record_latency,
    )

    await _persist_turn(
        db, workspace_id=workspace_id, call_session_id=call_session_id, state=redis_state, speaker="customer",
        text=speech_result, metadata=stt_metadata,
    )

    session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
    call_session = session_result.scalar_one_or_none()
    conversation_state = dict(call_session.state) if call_session is not None and call_session.state else {}
    policy_snapshot = ConversationPolicySnapshot(**redis_state.get("policy", {}))

    result = await process_turn(
        db, workspace_id=workspace_id, call_session_id=call_session_id, state=conversation_state,
        customer_utterance=speech_result, conversation_policy=policy_snapshot, agent_id=agent_id,
        business_identity=redis_state.get("business_identity", ""), recent_turns=redis_state.get("recent_turns", [])[-6:],
        engine_mode=settings.conversation_engine_mode, response_mode=settings.llm_response_mode,
        on_speakable_chunk=on_speakable_chunk, cancellation_token=cancellation_token,
        # P10 §42 — adaptive brevity: redis_state["recent_interrupt_count"]
        # is set by streaming_bridge.py's _execute_pending_interruption()
        # (P8); always 0 under batch/<Record> mode, where it's never set.
        recent_interrupt_count=redis_state.get("recent_interrupt_count", 0),
    )
    for stage, duration_ms in result.latency_ms.items():
        await _record_latency(
            db, workspace_id=workspace_id, call_session_id=call_session_id, stage=f"engine_{stage}",
            duration_ms=duration_ms, provider="jkr_conversation",
        )

    for tool_call in result.tool_calls_requested:
        try:
            execution = await execute_tool(
                db, workspace_id=workspace_id, tool_name=tool_call.tool_name, tool_input=tool_call.tool_input,
                idempotency_key=f"call-{call_session_id}-{tool_call.idempotency_suffix}",
                call_session_id=call_session_id, agent_version_id=call_session.agent_version_id if call_session else None,
            )
            if execution.status == "succeeded":
                result.state.setdefault("tool_results", {})[tool_call.tool_name] = execution.output
        except (ToolNotDefinedError, ToolNotEnabledError):
            pass  # tool not configured for this workspace — matches service.py's own handling

    if call_session is not None:
        call_session.state = result.state

    reply = result.reply_text
    redis_state["recent_turns"].append({"speaker": "customer", "text": speech_result})
    redis_state["recent_turns"].append({"speaker": "agent", "text": reply})
    redis_state["agent_turns"] = redis_state.get("agent_turns", 0) + 1
    await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=redis_state, speaker="agent", text=reply)

    force_close = result.call_should_end or result.planner_action == "HUMAN_HANDOFF"
    if force_close:
        redis_state["pending_end_reason"] = _end_reason_for(result)

    return TurnResult(reply_text=reply, force_close=force_close, had_speech=True)
