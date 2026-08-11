"""The FastAPI WebSocket endpoint Twilio's `<Connect><Stream>` connects to,
plus TwiML generation for TWILIO_VOICE_TRANSPORT=media_stream and the task
orchestration around one call's RealtimeMediaSession.

Task architecture per session (spec §17) — the receive loop never does AI
work inline (spec §16: it only decodes audio and enqueues it), all
STT/engine/TTS work happens in the processing loop, and outbound audio is
written to the socket by a single serialized send loop (spec §24, so
nothing interleaves/duplicates on the wire). All three, plus a watchdog,
are registered on the session so `session.close()` is the one place that
cancels everything regardless of which path triggered the close (spec
§34/§35/§37).

Ending the call: there is no TwiML round-trip once `<Connect><Stream>` is
active, so unlike <Record> mode there is no `<Hangup/>` to return. Closing
the WebSocket from our side is what ends the call — the TwiML response
that started the stream has nothing after `<Connect>`, so once that verb's
connection ends, Twilio's own TwiML execution naturally falls off the end
of the `<Response>` and hangs up. This is standard `<Connect><Stream>`
behavior, not a JKR-specific mechanism.
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jkr_db.models.calls import CallSession
from jkr_db.session import workspace_scoped_session
from jkr_messaging import get_redis
from sqlalchemy import select

from app.config import Settings, get_settings
from app.modules.live_call.transport.audio_codec import (
    TWILIO_SAMPLE_RATE,
    decode_twilio_media_payload,
    encode_twilio_media_payload,
)
from app.modules.live_call.transport.base import (
    AudioFrame,
    MediaSessionStatus,
    OutboundAudioChunk,
    PlaybackState,
)
from app.modules.live_call.transport.coordinator import begin_response_feed
from app.modules.live_call.transport.events import log_event
from app.modules.live_call.transport.identity import ResponseIdentity
from app.modules.live_call.transport.media_tokens import (
    InvalidMediaTokenError,
    verify_media_session_token,
)
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.schemas import (
    TwilioMarkEvent,
    TwilioMediaEvent,
    TwilioStartEvent,
    TwilioStopEvent,
    build_outbound_clear_message,
    build_outbound_mark_message,
    build_outbound_media_message,
    parse_twilio_event,
)
from app.modules.live_call.transport.session import RealtimeMediaSession, registry
from app.modules.live_call.transport.transitional_bridge import (
    TurnBuffer,
    process_transitional_turn,
    speak_turn_reply,
)

router = APIRouter()

# 4000-4999 is the range RFC 6455 reserves for application use — distinct
# from any code Twilio itself would ever send us.
WS_CLOSE_INVALID_TOKEN = 4401
WS_CLOSE_CALL_NOT_FOUND = 4404
WS_CLOSE_CALL_ALREADY_ENDED = 4409

_TERMINAL_CALL_STATUSES = {"completed", "failed", "no_answer", "busy", "abandoned"}

FRAME_WAIT_TIMEOUT_SECONDS = 1.0  # how often the processing loop wakes up to re-check grace/watchdog state even with no new audio
GRACE_SECONDS = 4.0  # mirrors service.py's closing-grace window for <Record> mode
GRACE_SAFETY_MARGIN_SECONDS = 1.5  # never finalize if media arrived more recently than this — see the grace loop's own comment
MARK_ACK_TIMEOUT_SECONDS = 10.0  # generous upper bound on how long a closing statement's audio could take to actually finish playing


def build_media_stream_twiml(ws_url: str) -> str:
    from app.modules.live_call.service import (
        _escape_xml,  # reuse the exact same XML-escaping <Record> mode's TwiML already uses
    )

    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="{_escape_xml(ws_url)}"/></Connect></Response>'


async def _load_redis_state(redis: Any, redis_state_token: str) -> dict | None:
    import json

    from app.modules.live_call.service import _redis_key

    raw = await redis.get(_redis_key(redis_state_token))
    return json.loads(raw) if raw is not None else None


async def _save_redis_state(redis: Any, redis_state_token: str, state: dict) -> None:
    import json

    from app.modules.live_call.service import REDIS_TTL_SECONDS, _redis_key

    await redis.set(_redis_key(redis_state_token), json.dumps(state), ex=REDIS_TTL_SECONDS)


async def _send_pcm_reply(
    session: RealtimeMediaSession, *, pcm16_bytes: bytes, sample_rate: int,
    identity: ResponseIdentity | None = None, playback_epoch: int = 0,
) -> str:
    """Splits one synthesized reply into a single OutboundAudioChunk (batch
    TTS doesn't chunk mid-sentence — see tts_bridge.py for the streaming-TTS
    equivalent) and enqueues it with a known mark_name, so the send loop
    can report when Twilio has actually finished playing it (spec §26 —
    never assume "enqueued" means "the customer heard it"). Returns the
    mark_name so a caller can await session.wait_for_mark_ack(...) instead
    of starting a fixed closing-grace timer immediately.

    P9 — `identity`/`playback_epoch` are None/0 by default (the legacy-path
    exception, spec §161: a pure TTS_MODE=batch call with no coordinator has
    nothing to attach) but ARE passed by callers that DO have a coordinator
    response to attach (the coordinator-routed greeting, and speak_turn_
    reply()'s own batch-fallback branch) — see docs/REPLAY_PROTECTION_
    ARCHITECTURE.md."""
    response_sequence_id = session.start_new_response_sequence()
    mark_name = session.next_mark_name()
    chunk = OutboundAudioChunk(
        response_sequence_id=response_sequence_id, chunk_index=session.next_chunk_index(),
        data=pcm16_bytes, sample_rate=sample_rate, mark_name=mark_name,
        identity=identity, playback_epoch=playback_epoch,
    )
    await session.enqueue_outbound_audio(chunk)
    return mark_name


async def _receive_loop(websocket: WebSocket, session: RealtimeMediaSession, streaming_started: asyncio.Event, settings: Settings) -> None:
    """Never does STT/LLM/TTS work — only decodes and hands off (spec §16).
    Raises WebSocketDisconnect on client disconnect, which the caller
    treats as an unexpected-close signal."""
    while True:
        raw = await websocket.receive_json()
        session.touch_twilio_event()
        parsed = parse_twilio_event(raw)

        if isinstance(parsed, TwilioStartEvent):
            session.handle_twilio_start(
                stream_sid=parsed.start.streamSid,
                media_format={
                    "encoding": parsed.start.mediaFormat.encoding,
                    "sample_rate": parsed.start.mediaFormat.sampleRate,
                    "channels": parsed.start.mediaFormat.channels,
                },
            )
            streaming_started.set()
        elif isinstance(parsed, TwilioMediaEvent):
            pcm16 = decode_twilio_media_payload(parsed.media.payload)
            frame = AudioFrame(
                data=pcm16, codec="pcm16", sample_rate=TWILIO_SAMPLE_RATE,  # fixed by Twilio's own contract — see audio_codec.py
                channels=1, timestamp_ms=int(parsed.media.timestamp) if parsed.media.timestamp.isdigit() else None,
                sequence_number=int(parsed.sequenceNumber) if parsed.sequenceNumber.isdigit() else None,
            )
            session.enqueue_inbound_audio(frame)
            if settings.voice_media_debug:
                log_event(
                    "media_frame_received", call_session_id=session.call_session_id, debug_only=True,
                    chunk=parsed.media.chunk, timestamp=parsed.media.timestamp,
                )
        elif isinstance(parsed, TwilioMarkEvent):
            session.record_mark_acknowledged(parsed.mark.name)
        elif isinstance(parsed, TwilioStopEvent):
            log_event("media_stream_stopping", call_session_id=session.call_session_id, reason="twilio_stop_event")
            return
        # `connected` and `dtmf` events: nothing to do in P2 beyond the
        # touch_twilio_event() already recorded above; dtmf handling is a
        # documented future extension, not needed for the current flow.


async def _connect_streaming_tts(
    session: RealtimeMediaSession, *, language_code: str, tts_speaker: str | None, tts_pace: float, settings: Settings,
) -> None:
    """P6 spec §15 — connect/prewarm as early as safely practical (right
    after Media Streams itself starts, before the greeting is even
    synthesized) so the first REAL turn's SpeakableChunk never pays
    WebSocket handshake latency. Any failure here just leaves
    session.tts_streaming_session as None — the call falls back to batch
    TTS for its entire duration rather than failing call setup over a
    provider hiccup, same posture as every other optional-enhancement
    connect failure in this codebase (e.g. mid-call VAD).

    P7 — also creates the call's RealtimePipelineCoordinator, always
    alongside TTSStreamingSession, never on its own (spec §92-94: every
    streaming response goes through the coordinator, so a call without a
    live TTS connection has nothing for the coordinator to orchestrate)."""
    from app.live_providers.sarvam_streaming_tts import SarvamStreamingTTS
    from app.live_providers.streaming_tts import StreamingTTSConfig, TTSCallContext
    from app.modules.live_call.transport.coordinator import RealtimePipelineCoordinator
    from app.modules.live_call.transport.tts_bridge import TTSStreamingSession

    api_key = settings.sarvam_tts_api_key or settings.sarvam_api_key
    provider = SarvamStreamingTTS(api_key=api_key)
    tts_session = TTSStreamingSession(
        provider=provider, media_session=session,
        provider_factory=lambda: SarvamStreamingTTS(api_key=api_key),  # P7 §82 — fresh instance per reconnect attempt
    )
    t0 = time.perf_counter()
    try:
        await tts_session.start(
            config=StreamingTTSConfig(target_language_code=language_code, voice_id=tts_speaker, pace=tts_pace),
            context=TTSCallContext(call_session_id=str(session.call_session_id), workspace_id=str(session.workspace_id)),
        )
    except Exception as exc:  # noqa: BLE001 — see docstring; never raised past this boundary
        log_event("tts_stream_connect_failed", call_session_id=session.call_session_id, error=str(exc))
        return
    log_event(
        "tts_stream_connected", call_session_id=session.call_session_id,
        connect_ms=int((time.perf_counter() - t0) * 1000),
    )
    session.tts_streaming_session = tts_session
    coordinator = RealtimePipelineCoordinator(call_session_id=session.call_session_id, media_session=session)
    coordinator.attach_tts_session(tts_session)
    session.pipeline_coordinator = coordinator


async def _processing_loop(
    session: RealtimeMediaSession, streaming_started: asyncio.Event, *, workspace_id: uuid.UUID,
    call_session_id: uuid.UUID, agent_id: uuid.UUID | None, redis_state: dict, settings: Settings, redis: Any, redis_state_token: str,
) -> None:
    """The only loop allowed to do STT/engine/TTS work. Sends the greeting
    once streaming starts, then hands off to either the batch turn-buffer
    loop (process_transitional_turn) or, when settings.effective_stt_mode
    == "streaming", the persistent Sarvam streaming STT loop
    (streaming_bridge.run_streaming_turn_loop) — see transitional_bridge.py
    and streaming_bridge.py's own docstrings for why each exists."""
    from app.modules.live_call.service import (
        FALLBACK_LANGUAGE,
        _persist_turn,
    )

    await streaming_started.wait()

    language_code = redis_state.get("language_code", FALLBACK_LANGUAGE)
    tts_speaker = redis_state.get("tts_speaker")
    tts_pace = redis_state.get("tts_pace", 1.0)

    if settings.effective_tts_mode == "streaming":
        await _connect_streaming_tts(
            session, language_code=language_code, tts_speaker=tts_speaker, tts_pace=tts_pace, settings=settings,
        )

    async with workspace_scoped_session(workspace_id) as db:
        result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
        call_session = result.scalar_one_or_none()
        if call_session is not None:
            call_session.status = "in_progress"
            call_session.answered_at = datetime.now(UTC)

        greeting = redis_state["recent_turns"][-1]["text"] if redis_state.get("recent_turns") else ""
        if greeting:
            # P9 §70-72/§154-155 — the greeting now goes through the SAME
            # RealtimePipelineCoordinator ownership/identity/PlaybackUnit
            # model as every other response, closing the one bypass P8's
            # own results doc flagged ("greeting playback is not currently
            # routed through the coordinator"). Reuses speak_turn_reply()
            # unchanged — it already handles a known (not LLM-streamed)
            # reply text via chunk_text_for_tts()+send_chunk(), the exact
            # shape a greeting is, and already falls back to the batch PCM
            # path unchanged when no coordinator exists (TTS_MODE=batch),
            # so this does not regress cached-greeting latency for that
            # configuration. This closes the REPLAY-PROTECTION gap (late/
            # duplicate greeting audio is now caught by the same output
            # gate as everything else) — it does NOT by itself make the
            # greeting concurrently interruptible in real time (no signal-
            # processing loop runs during _processing_loop's own greeting
            # await), which remains explicit future work, not a P9 claim.
            feed = await begin_response_feed(session.pipeline_coordinator, turn_id="greeting")
            spoken = await speak_turn_reply(
                reply_text=greeting, session=session, language_code=language_code, settings=settings,
                speaker=tts_speaker, response_handle=feed.handle, callback_fired=feed.callback_fired(),
            )
            if spoken.fatal_failure:
                log_event("media_stream_failed", call_session_id=call_session_id, reason="greeting_tts_failed")
                session.close(failed=True)
                return
            await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=redis_state, speaker="agent", text=greeting)
    await _save_redis_state(redis, redis_state_token, redis_state)

    if settings.effective_stt_mode == "streaming":
        from app.modules.live_call.transport.streaming_bridge import run_streaming_turn_loop

        fell_back_to_batch = await run_streaming_turn_loop(
            session, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
            redis_state=redis_state, settings=settings, redis=redis, redis_state_token=redis_state_token,
            language_code=language_code, tts_speaker=tts_speaker,
        )
        if not fell_back_to_batch:
            return
        # settings.stt_stream_failure_policy == "batch_next_turn" and the
        # streaming connection exhausted its reconnect attempts — the
        # session is still open (not closed/failed), so continue the call
        # on the proven batch path rather than dropping the customer.
        log_event("media_stream_stt_fallback_to_batch", call_session_id=call_session_id)

    await _run_batch_turn_loop(
        session, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
        redis_state=redis_state, settings=settings, redis=redis, redis_state_token=redis_state_token,
        language_code=language_code, tts_speaker=tts_speaker,
    )


async def _run_batch_turn_loop(
    session: RealtimeMediaSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, agent_id: uuid.UUID | None,
    redis_state: dict, settings: Settings, redis: Any, redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> None:
    """The trailing-silence turn-buffer loop against transitional_bridge.py
    — extracted verbatim from _processing_loop (pure code motion, no
    behavior change) so both the STT_MODE=batch path and the
    STT_MODE=streaming "batch_next_turn" fallback path can reach it."""
    from app.modules.live_call.service import _finalize_call, _reopen_conversation_state

    turn_buffer = TurnBuffer()
    in_grace_period = False
    grace_deadline = 0.0

    while not session.is_closed:
        try:
            frame = await asyncio.wait_for(session.dequeue_inbound_audio(), timeout=FRAME_WAIT_TIMEOUT_SECONDS)
        except TimeoutError:
            frame = None
        if frame is not None:
            turn_buffer.add_frame(frame)

        if in_grace_period:
            if turn_buffer.is_turn_complete():
                feed = await begin_response_feed(session.pipeline_coordinator, turn_id=f"turn_{uuid.uuid4().hex[:8]}")
                async with workspace_scoped_session(workspace_id) as db:
                    session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
                    call_session = session_result.scalar_one_or_none()
                    if call_session is not None and call_session.state:
                        call_session.state = _reopen_conversation_state(dict(call_session.state))
                    turn_result = await process_transitional_turn(
                        db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
                        wav_bytes=turn_buffer.build_wav(), redis_state=redis_state, settings=settings, language_code=language_code,
                        on_speakable_chunk=feed.on_chunk, cancellation_token=feed.cancellation_token,
                    )
                await _save_redis_state(redis, redis_state_token, redis_state)
                turn_buffer.reset()
                spoken = await speak_turn_reply(
                    reply_text=turn_result.reply_text, session=session, language_code=language_code, settings=settings,
                    speaker=tts_speaker, response_handle=feed.handle, callback_fired=feed.callback_fired(),
                )
                mark_name = spoken.mark_name
                if turn_result.force_close:
                    # customer engaged again, but this turn also closed — recurse into grace again, once THIS reply's audio actually finished
                    grace_deadline = await _grace_deadline_after_playback(session, mark_name)
                else:
                    in_grace_period = False  # genuine resume — back to normal conversation
            elif time.monotonic() >= grace_deadline:
                recent = session.seconds_since_last_media()
                if recent is not None and recent < GRACE_SAFETY_MARGIN_SECONDS:
                    # Media arrived very recently — never hang up while the
                    # customer might still be mid-speech (spec §93/§72).
                    grace_deadline = time.monotonic() + GRACE_SAFETY_MARGIN_SECONDS
                else:
                    async with workspace_scoped_session(workspace_id) as db:
                        await _finalize_call(
                            db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
                            end_reason=redis_state.get("pending_end_reason", "completed"), had_exchange=True, language_code=language_code,
                        )
                    session.close()
                    return
        else:
            if turn_buffer.is_turn_complete():
                feed = await begin_response_feed(session.pipeline_coordinator, turn_id=f"turn_{uuid.uuid4().hex[:8]}")
                async with workspace_scoped_session(workspace_id) as db:
                    turn_result = await process_transitional_turn(
                        db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
                        wav_bytes=turn_buffer.build_wav(), redis_state=redis_state, settings=settings, language_code=language_code,
                        on_speakable_chunk=feed.on_chunk, cancellation_token=feed.cancellation_token,
                    )
                await _save_redis_state(redis, redis_state_token, redis_state)
                turn_buffer.reset()
                spoken = None
                if turn_result.reply_text:
                    spoken = await speak_turn_reply(
                        reply_text=turn_result.reply_text, session=session, language_code=language_code, settings=settings,
                        speaker=tts_speaker, response_handle=feed.handle, callback_fired=feed.callback_fired(),
                    )
                    if spoken.fatal_failure:
                        log_event("media_stream_failed", call_session_id=call_session_id, reason="reply_tts_failed")
                        session.close(failed=True)
                        return
                if turn_result.force_close:
                    in_grace_period = True
                    grace_deadline = await _grace_deadline_after_playback(session, spoken.mark_name if spoken else None)
            elif turn_buffer.is_over_max_duration():
                turn_buffer.reset()  # maxed-out pure silence — discard and keep listening, never call STT on nothing


async def _grace_deadline_after_playback(session: RealtimeMediaSession, mark_name: str | None) -> float:
    """spec §59-61 — the real fix for closing grace starting before
    playback actually finished: wait for the specific mark tied to the
    closing audio's last chunk before starting the grace clock, rather
    than starting it the instant the audio was merely enqueued. A timeout
    (lost mark message — rare) falls back to starting the grace timer
    immediately rather than hanging the call; mark_name is None when there
    was nothing to wait for (e.g. TTS failed on a non-fatal reaffirm)."""
    if mark_name is not None:
        await session.wait_for_mark_ack(mark_name, timeout_seconds=MARK_ACK_TIMEOUT_SECONDS)
    return time.monotonic() + GRACE_SECONDS


async def clear_agent_audio(websocket: WebSocket, session: RealtimeMediaSession) -> None:
    """spec §27 — the primitive barge-in (P8) will call once real
    interruption detection exists; not yet wired to any automatic trigger
    in P2 (no VAD/interruption detection exists yet — spec §65-67), but
    must exist and work correctly on its own today. Sends Twilio's `clear`
    message (flushes whatever Twilio has already buffered for playback)
    and drops anything still sitting in our own outbound queue, so no
    stale audio can play after this call returns."""
    session.request_clear_playback()
    if session.twilio_stream_sid:
        await websocket.send_json(build_outbound_clear_message(stream_sid=session.twilio_stream_sid))
    while not session.outbound_queue.empty():
        try:
            session.outbound_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    session.playback_state = PlaybackState.IDLE


_GATE_REASON_TO_METRIC = {
    "unknown_response": "unknown_response_artifact_dropped_total",
    "call_mismatch": "unknown_response_artifact_dropped_total",
    "stale_response": "stale_twilio_media_dropped_total",
    "playback_epoch_stale": "stale_twilio_media_dropped_total",
    "duplicate_media": "duplicate_twilio_media_dropped_total",
    "no_coordinator_for_identity": "stale_twilio_media_dropped_total",
}


def _record_gate_block(*, call_session_id: object, reason: str, chunk: OutboundAudioChunk) -> None:
    metric_field = _GATE_REASON_TO_METRIC.get(reason, "stale_twilio_media_dropped_total")
    replay_metrics.record_blocked(metric_field)
    log_event(
        "stale_audio_blocked", call_session_id=call_session_id, boundary="twilio_output_gate", reason=reason,
        response_id=chunk.identity.response_id if chunk.identity is not None else None,
        audio_chunk_index=chunk.chunk_index,
    )


async def _send_loop(websocket: WebSocket, session: RealtimeMediaSession, settings: Settings) -> None:
    """Single serialized sender (spec §24) — nothing else in this module
    ever calls websocket.send_json() directly, so outbound messages can
    never interleave or duplicate on the wire.

    P9 §34-36/§75-78 — the CustomerFacingOutputGate: every chunk is
    validated again HERE, immediately before send, via
    RealtimePipelineCoordinator.can_send_media() — the single final
    boundary, called from exactly this one place. This is deliberately IN
    ADDITION TO (never a replacement for) the `PlaybackState.CLEARING`
    check below and every upstream ownership check — defense in depth
    (spec §78), closing the TOCTOU race between clear_agent_audio()'s
    queue-drain and this loop already having dequeued an item (see
    docs/P9_REPLAY_PROTECTION_AUDIT.md's own analysis of that race)."""
    while True:
        chunk = await session.dequeue_outbound_audio()
        if session.playback_state == PlaybackState.CLEARING:
            continue  # a clear was requested while this chunk was queued — drop it rather than play stale audio
        if chunk.identity is not None:
            coordinator = session.pipeline_coordinator
            if coordinator is None:
                _record_gate_block(call_session_id=session.call_session_id, reason="no_coordinator_for_identity", chunk=chunk)
                continue
            decision = coordinator.can_send_media(chunk)
            if not decision.allowed:
                _record_gate_block(call_session_id=session.call_session_id, reason=decision.reason, chunk=chunk)
                continue
        if chunk.audio_is_mulaw_8k:
            # Sarvam's direct streaming-TTS output (docs/SARVAM_STREAMING_TTS_CONTRACT.md)
            # — already Twilio's exact wire format, base64 directly rather
            # than routing through encode_twilio_media_payload()'s PCM16
            # resample/encode path, which would corrupt already-mulaw bytes.
            payload_b64 = base64.b64encode(chunk.data).decode("ascii")
        else:
            payload_b64 = encode_twilio_media_payload(chunk.data, sample_rate=chunk.sample_rate)
        await websocket.send_json(build_outbound_media_message(stream_sid=session.twilio_stream_sid or "", payload_b64=payload_b64))
        session.metrics.outbound_frames += 1
        session.metrics.outbound_bytes += len(chunk.data)
        if settings.voice_media_debug:
            log_event("media_frame_sent", call_session_id=session.call_session_id, debug_only=True, response_sequence_id=chunk.response_sequence_id, chunk_index=chunk.chunk_index)

        mark_name = chunk.mark_name or session.next_mark_name()
        await websocket.send_json(build_outbound_mark_message(stream_sid=session.twilio_stream_sid or "", name=mark_name))
        session.record_mark_sent(mark_name)


async def _watchdog(session: RealtimeMediaSession, *, idle_timeout_seconds: float) -> None:
    """spec §32 — detects a stream that connected but then went silent
    (no inbound media at all) for too long, distinct from normal
    trailing-silence-between-turns handled by the processing loop's own
    grace/turn-buffer logic."""
    while not session.is_closed:
        await asyncio.sleep(idle_timeout_seconds / 3)
        if session.status == MediaSessionStatus.STREAMING and session.is_media_idle(timeout_seconds=idle_timeout_seconds):
            log_event("media_stream_failed", call_session_id=session.call_session_id, reason="media_idle_timeout")
            session.close(failed=True)
            return


@router.websocket("/live-call/ws/twilio/media/{session_token}")
async def twilio_media_stream_websocket(websocket: WebSocket, session_token: str) -> None:
    settings = get_settings()
    await websocket.accept()

    try:
        token_payload = verify_media_session_token(session_token, secret=settings.session_secret)
    except InvalidMediaTokenError:
        await websocket.close(code=WS_CLOSE_INVALID_TOKEN)
        return

    workspace_id = token_payload.workspace_id
    call_session_id = token_payload.call_session_id

    async with workspace_scoped_session(workspace_id) as db:
        result = await db.execute(select(CallSession).where(CallSession.id == call_session_id, CallSession.workspace_id == workspace_id))
        call_session = result.scalar_one_or_none()

    if call_session is None:
        await websocket.close(code=WS_CLOSE_CALL_NOT_FOUND)
        return
    if call_session.status in _TERMINAL_CALL_STATUSES:
        await websocket.close(code=WS_CLOSE_CALL_ALREADY_ENDED)
        return

    redis = get_redis()
    redis_state = await _load_redis_state(redis, token_payload.redis_state_token)
    if redis_state is None:
        await websocket.close(code=WS_CLOSE_CALL_NOT_FOUND)
        return

    session = RealtimeMediaSession(
        call_session_id=call_session_id, workspace_id=workspace_id,
        twilio_call_sid=token_payload.twilio_call_sid, agent_id=call_session.agent_id,
    )
    # P8 — the only place a WebSocket reference is in scope: wire the
    # decoupled callback (docs/P8_BARGE_IN_AUDIT.md §6) so
    # RealtimePipelineCoordinator.interrupt_active_response() can trigger a
    # real Twilio clear without needing this handler's `websocket` itself.
    session.send_twilio_clear = lambda: clear_agent_audio(websocket, session)
    await registry.add(session)
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    log_event("media_stream_connected", call_session_id=call_session_id)

    streaming_started = asyncio.Event()
    failed = False
    try:
        receive_task = asyncio.create_task(_receive_loop(websocket, session, streaming_started, settings))
        processing_task = asyncio.create_task(
            _processing_loop(
                session, streaming_started, workspace_id=workspace_id, call_session_id=call_session_id,
                agent_id=call_session.agent_id, redis_state=redis_state, settings=settings, redis=redis,
                redis_state_token=token_payload.redis_state_token,
            )
        )
        send_task = asyncio.create_task(_send_loop(websocket, session, settings))
        watchdog_task = asyncio.create_task(_watchdog(session, idle_timeout_seconds=30.0))
        for task in (receive_task, processing_task, send_task, watchdog_task):
            session.register_task(task)

        # The receive loop returning (stop event) or raising
        # (WebSocketDisconnect) is what ends a normal call; the processing
        # loop returning on its own means it already finalized the call
        # (grace expired, or a TTS failure) — either way, one of these
        # finishing is the signal to tear everything else down.
        done, _pending = await asyncio.wait(
            {receive_task, processing_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            exc = task.exception() if task.done() and not task.cancelled() else None
            if isinstance(exc, WebSocketDisconnect):
                failed = True
    except WebSocketDisconnect:
        failed = True
    finally:
        was_first_close = session.close(failed=failed)
        if session.tts_streaming_session is not None:
            await session.tts_streaming_session.close()
        await registry.remove(call_session_id)
        if was_first_close and failed:
            async with workspace_scoped_session(workspace_id) as db:
                from app.modules.live_call.service import _finalize_call

                await _finalize_call(
                    db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="failed",
                    end_reason="error", had_exchange=session.metrics.inbound_frames > 0, language_code=redis_state.get("language_code", "en-IN"),
                )
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001 — socket may already be closed by the client; closing an already-closed socket must never crash cleanup
            pass
