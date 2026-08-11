"""Real Sarvam streaming TTS WebSocket client (`bulbul:v3`) — the streaming
counterpart to `sarvam_tts.py`'s batch REST client. See
docs/SARVAM_STREAMING_TTS_CONTRACT.md for the full verified wire contract
(live-probed against the real API, not guessed from docs alone — the docs
themselves turned out to be stale on codec support).

Hand-rolled against raw `websockets`, matching every other Sarvam
integration in this codebase (no SDK) — mirrors `sarvam_streaming_stt.py`'s
shape directly: one instance = one connection for the call's lifetime,
`connect()`/`events()`/`close()`.

Uses `output_audio_codec="mulaw"` + `speech_sample_rate="8000"` — verified
live to return raw, headerless mu-law bytes at exactly Twilio's wire format,
needing nothing beyond a base64 decode (see contract doc's format table).

Cancellation is local-only (spec §79): Sarvam's protocol has no
cancel/abort message. `cancel(response_id)` marks that response's audio as
discardable; `events()` still drains (and discards) whatever the provider
keeps sending for it, so the connection itself is never disrupted by a
cancel — only what gets forwarded to the caller changes.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSCapabilities,
    TTSFailureClass,
    TTSFirstAudio,
    TTSGenerationCompleted,
    TTSStreamCancelled,
    TTSStreamEvent,
    TTSStreamFailed,
)

SARVAM_TTS_WS_URL = "wss://api.sarvam.ai/text-to-speech/ws"

CAPABILITIES = TTSCapabilities(
    supports_streaming_input=True,
    supports_streaming_audio=True,
    supports_flush=True,
    supports_completion_event=True,
    supports_live_reconfiguration=False,  # not verified this pass — see contract doc §19; restart between turns instead
    supports_pronunciation_dictionary=True,  # dict_id is a real config field; not wired into StreamingTTSConfig this pass (§65)
    supports_direct_mulaw_8k=True,  # verified live — see contract doc's format table
    supports_cancel=True,  # local-only, not protocol-level — see module docstring
)

_ERROR_CODE_PREFIX = re.compile(r"^(\d{3}):\s*")


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_TTS_API_KEY/SARVAM_API_KEY is absent — see sarvam_tts.NotConfiguredError."""


class SarvamStreamingTTSError(RuntimeError):
    """Raised for a send/receive attempted before connect(), or after close()."""


def _classify_error(message: str, *, status_code: int | None) -> TTSFailureClass:
    if status_code is None:
        match = _ERROR_CODE_PREFIX.match(message)
        status_code = int(match.group(1)) if match else None
    if status_code in (401, 403):
        return TTSFailureClass.AUTH_ERROR
    if status_code == 429:
        return TTSFailureClass.RATE_LIMIT
    if status_code is not None and status_code >= 500:
        return TTSFailureClass.PROVIDER_INTERNAL
    if status_code is not None and status_code >= 400:
        return TTSFailureClass.INVALID_REQUEST
    return TTSFailureClass.UNKNOWN


class SarvamStreamingTTS:
    def __init__(self, *, api_key: str, ws_url: str = SARVAM_TTS_WS_URL):
        if not api_key:
            raise NotConfiguredError("SARVAM_TTS_API_KEY/SARVAM_API_KEY is not set")
        self._api_key = api_key
        self._ws_url = ws_url
        self._ws: ClientConnection | None = None
        self._closed = False
        # The one thing Sarvam's own protocol gives us no way to know:
        # which text/flush cycle a given audio/event message belongs to
        # (request_id is scoped to the whole connection — see contract
        # doc). Tracked locally instead: whichever response_id most
        # recently had send_text()/flush() called for it is "active" until
        # its own TTSGenerationCompleted/TTSStreamFailed is observed.
        #
        # This assumes the caller never starts response N+1 (calls
        # send_text for a new response_id) before response N's own
        # TTSGenerationCompleted/TTSStreamFailed has already been consumed
        # from events() — true by construction in tts_bridge.py (a
        # TTSResponseHandle.finish() call always awaits completion before
        # a turn loop begins the next response) and empirically true of
        # Sarvam's own per-connection processing (see contract doc's
        # connection-reuse probe). Not defensively enforced here (no
        # assertion) — a caller that violated this would see audio
        # mistagged with the wrong response_id, not a crash.
        self._active_response_id: str | None = None
        self._audio_chunk_index_by_response: dict[str, int] = {}
        self._first_audio_seen: set[str] = set()
        self._cancelled_response_ids: set[str] = set()

    @property
    def capabilities(self) -> TTSCapabilities:
        return CAPABILITIES

    async def connect(self, *, config: StreamingTTSConfig, context: TTSCallContext) -> None:
        url = f"{self._ws_url}?model={config.model}&send_completion_event=true"
        self._ws = await websockets.connect(
            url, additional_headers={"Api-Subscription-Key": self._api_key}, open_timeout=10.0
        )
        config_data: dict[str, object] = {
            "language_code": config.target_language_code,
            "pace": config.pace,
            "output_audio_codec": "mulaw",
            "speech_sample_rate": str(config.output_sample_rate),
        }
        if config.voice_id:
            config_data["speaker"] = config.voice_id
        if config.temperature is not None:
            config_data["temperature"] = config.temperature
        if config.pronunciation_dictionary_id:
            config_data["dict_id"] = config.pronunciation_dictionary_id
        await self._ws.send(json.dumps({"type": "config", "data": config_data}))

    async def send_text(self, *, text: str, response_id: str, chunk_index: int) -> None:
        if self._ws is None:
            raise SarvamStreamingTTSError("send_text() called before connect()")
        self._active_response_id = response_id
        self._audio_chunk_index_by_response.setdefault(response_id, 0)
        await self._ws.send(json.dumps({"type": "text", "data": {"text": text}}))

    async def flush(self, *, response_id: str) -> None:
        if self._ws is None:
            raise SarvamStreamingTTSError("flush() called before connect()")
        self._active_response_id = response_id
        await self._ws.send(json.dumps({"type": "flush"}))

    async def cancel(self, response_id: str) -> None:
        """Local-only — see module docstring. Never touches the socket:
        the provider keeps generating audio for a synthesis already in
        flight regardless (no protocol-level abort), but events() will
        silently drop everything for a cancelled response_id from here on."""
        self._cancelled_response_ids.add(response_id)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._ws is None:
            return
        try:
            await self._ws.close()
        except Exception:  # noqa: BLE001 — socket may already be dead; close() must never raise
            pass

    async def events(self) -> AsyncIterator[TTSStreamEvent]:
        if self._ws is None:
            raise SarvamStreamingTTSError("events() called before connect()")
        async for raw_message in self._ws:
            try:
                msg = json.loads(raw_message)
            except (TypeError, ValueError):
                continue
            for event in self._parse_event(msg):
                yield event

    def _parse_event(self, msg: dict) -> list[TTSStreamEvent]:
        mtype = msg.get("type")
        data = msg.get("data") or {}
        response_id = self._active_response_id

        if mtype == "audio":
            if response_id is None:
                return []  # audio with no response context — nothing sane to attribute it to
            if response_id in self._cancelled_response_ids:
                return []  # spec §79/§102 — discard, never forward stale/cancelled audio
            b64 = data.get("audio") or ""
            decoded = base64.b64decode(b64) if b64 else b""
            index = self._audio_chunk_index_by_response.get(response_id, 0)
            self._audio_chunk_index_by_response[response_id] = index + 1
            events: list[TTSStreamEvent] = []
            if response_id not in self._first_audio_seen:
                self._first_audio_seen.add(response_id)
                events.append(TTSFirstAudio(response_id=response_id))
            events.append(
                TTSAudioChunk(
                    response_id=response_id, audio_chunk_index=index, data=decoded,
                    content_type=data.get("content_type"), codec="mulaw", sample_rate=8000,
                )
            )
            return events

        if mtype == "event" and (data.get("event_type") == "final"):
            if response_id is None:
                return []
            if response_id in self._cancelled_response_ids:
                return [TTSStreamCancelled(response_id=response_id)]
            return [TTSGenerationCompleted(response_id=response_id)]

        if mtype == "error":
            message = data.get("message") or "unknown TTS provider error"
            return [
                TTSStreamFailed(
                    response_id=response_id, failure_class=_classify_error(message, status_code=data.get("code")),
                    message=message,
                )
            ]

        return []
