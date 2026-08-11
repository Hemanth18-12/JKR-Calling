"""Transport-layer abstractions for the live-call audio path — the seam
that keeps jkr_conversation.engine.process_turn() (and everything upstream
of it: extraction, RAG, domain correction, closing) completely unaware of
whether audio arrives via Twilio's <Record> (batch, one HTTP webhook per
turn) or Media Streams (continuous bidirectional WebSocket). See
docs/TWILIO_MEDIA_STREAMS.md.

`VoiceTransport` is documented here primarily as the contract
`TwilioMediaStreamTransport` implements, not as a literal base class the
existing `<Record>` flow is retrofitted into. The `<Record>` handlers
(handle_voice_webhook / handle_recording_webhook / handle_closing_grace_webhook
in ../service.py) are a fundamentally different shape — one stateless HTTP
request-response per turn, not a long-lived object with a receive loop —
and forcing them into this Protocol would mean rewriting already-correct,
already-tested code purely to satisfy an interface, which is exactly what
the P2 scope rule says not to do. They stay untouched; this module only
describes what a *streaming* transport looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.modules.live_call.transport.identity import ResponseIdentity


class MediaSessionStatus(StrEnum):
    CREATED = "created"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    CLOSING = "closing"
    STOPPED = "stopped"
    FAILED = "failed"


# Explicit transition table — deliberately not a handful of scattered
# booleans (is_connected/is_started/stopped/done) that can drift out of
# sync with each other. Anything not listed here is rejected by
# RealtimeMediaSession.transition_to().
VALID_STATUS_TRANSITIONS: dict[MediaSessionStatus, frozenset[MediaSessionStatus]] = {
    MediaSessionStatus.CREATED: frozenset({MediaSessionStatus.CONNECTING, MediaSessionStatus.FAILED}),
    MediaSessionStatus.CONNECTING: frozenset({MediaSessionStatus.CONNECTED, MediaSessionStatus.FAILED}),
    MediaSessionStatus.CONNECTED: frozenset({MediaSessionStatus.STREAMING, MediaSessionStatus.CLOSING, MediaSessionStatus.FAILED}),
    MediaSessionStatus.STREAMING: frozenset({MediaSessionStatus.CLOSING, MediaSessionStatus.FAILED}),
    MediaSessionStatus.CLOSING: frozenset({MediaSessionStatus.STOPPED, MediaSessionStatus.FAILED}),
    MediaSessionStatus.STOPPED: frozenset(),  # terminal
    MediaSessionStatus.FAILED: frozenset(),  # terminal
}


class PlaybackState(StrEnum):
    IDLE = "idle"
    PLAYING = "playing"
    CLEARING = "clearing"


@dataclass(frozen=True)
class AudioFrame:
    """Normalized inbound audio — decoded from whatever the transport's
    wire format was (Twilio: base64 mu-law, see audio_codec.py) before
    anything downstream (the transitional STT bridge today; a future real
    streaming STT provider in P3) ever sees it. A future non-Twilio
    transport only needs to produce this shape, never touch Twilio's JSON."""

    data: bytes  # PCM16 mono, unless codec says otherwise
    codec: str  # "pcm16"
    sample_rate: int
    channels: int
    timestamp_ms: int | None = None
    sequence_number: int | None = None


@dataclass(frozen=True)
class OutboundAudioChunk:
    """One piece of a logical agent response. response_sequence_id +
    chunk_index are the foundation P9's full replay/duplicate protection
    builds on — established now (even though P2 only ever sends one chunk
    per response) so nothing downstream needs retrofitting later.

    mark_name is assigned by the ENQUEUER (session.next_mark_name(), called
    before enqueue_outbound_audio) rather than by the send loop itself —
    P6 needs this: a caller that just enqueued what it knows is a
    response's FINAL chunk must be able to ask "has THIS specific mark
    been acknowledged yet" (session.wait_for_mark_ack), which requires
    knowing the mark name in advance. Since exactly one consumer ever
    drains outbound_queue in FIFO order, assigning the name at enqueue time
    is equivalent to assigning it at send time — no reordering is possible.
    mark_name also doubles as this chunk's playback_unit_id (P9) — already
    unique per call, already assigned before enqueue, no second ID needed.

    audio_is_mulaw_8k=True means `data` is already raw mu-law @ 8kHz (e.g.
    Sarvam's direct streaming-TTS output — see docs/
    SARVAM_STREAMING_TTS_CONTRACT.md) and must be base64-encoded as-is,
    never re-decoded/resampled/re-encoded through audio_codec.py's PCM16
    path — encode_twilio_media_payload() assumes PCM16 input, calling it
    on already-mulaw bytes would corrupt the audio.

    P9 — `identity`/`playback_epoch`: attached by the producer (tts_bridge.py
    for the streaming path, twilio_media_stream.py for the batch/legacy
    path) and validated again by RealtimePipelineCoordinator.can_send_media()
    — the final output gate — immediately before this chunk crosses the
    Twilio WebSocket (see docs/REALTIME_OUTPUT_INVARIANTS.md).
    `identity=None` is the deliberate, documented legacy-path exception
    (spec §161): a call with no coordinator at all (pure `TTS_MODE=batch`,
    no streaming pipeline) has no ownership model to check against, and the
    gate treats a None identity as always-sendable — never a way to bypass
    the gate for a call that DOES have a coordinator."""

    response_sequence_id: str
    chunk_index: int
    data: bytes  # PCM16 mono, unless audio_is_mulaw_8k is True
    sample_rate: int
    mark_name: str = ""  # "" only for legacy/test construction; always set by real enqueue call sites
    audio_is_mulaw_8k: bool = False
    identity: ResponseIdentity | None = None
    playback_epoch: int = 0


class VoiceTransport(Protocol):
    """The contract any streaming (non-<Record>) telephony transport must
    satisfy. `TwilioMediaStreamTransport` (twilio_media_stream.py) is the
    one real implementation today."""

    async def start_call_session(self) -> None: ...
    async def receive_customer_audio(self) -> AudioFrame | None: ...
    async def send_agent_audio(self, chunk: OutboundAudioChunk) -> None: ...
    async def clear_agent_audio(self) -> None: ...
    async def end_call(self) -> None: ...
