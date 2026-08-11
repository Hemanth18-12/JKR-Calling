"""Real Sarvam Realtime STT WebSocket client (`saaras:v3-realtime`) — the
streaming counterpart to `sarvam_stt.py`'s batch REST client. See
docs/SARVAM_STREAMING_STT_CONTRACT.md for the full verified wire contract
this module implements; every field name/URL/message shape here traces
back to that document, not to assumption.

Hand-rolled against the raw `websockets` library rather than the official
`sarvamai` SDK, matching this codebase's existing pattern for every other
Sarvam integration (`sarvam_stt.py`/`sarvam_tts.py` are both raw `httpx`,
no SDK) — keeps full control over reconnect behavior and lets server
events map directly onto this project's own typed `STTEvent` model instead
of the SDK's.

Sends every inbound audio frame continuously, silence included — Sarvam's
server-side VAD (`endpointing=vad`) needs a continuous stream to detect
speech boundaries itself; there is no local turn-buffering here at all
(contrast `transitional_bridge.TurnBuffer`, which this module's caller,
`streaming_bridge.py`, does not use).
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from app.live_providers.streaming_stt import (
    FinalTranscript,
    PartialTranscript,
    SpeechEnded,
    SpeechStarted,
    StreamingSTTConfig,
    STTCapabilities,
    STTError,
    STTEvent,
    STTReconfigured,
    STTSessionEnded,
    STTSessionStarted,
)

REALTIME_STT_WS_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
REALTIME_STT_MODEL = "saaras:v3-realtime"

# Sarvam's docs say the inactivity timeout threshold isn't published — this
# is a conservative, documented-available mitigation (send periodic pings),
# not a value derived from any specific published number.
PING_INTERVAL_SECONDS = 15.0

CAPABILITIES = STTCapabilities(
    supports_partial_transcripts=True,
    supports_vad_events=True,
    supports_live_reconfiguration=True,
    supports_flush=True,
    supports_provider_confidence=False,  # Sarvam's Realtime API never emits a transcription confidence score
    supports_code_mix=True,
    supports_pronunciation_dictionary=False,  # not found anywhere in the documented config surface
)


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_API_KEY is absent — see sarvam_stt.NotConfiguredError."""


class SarvamStreamingSTTError(RuntimeError):
    """Raised for a send/receive attempted before connect(), or after close()."""


def _build_connect_url(config: StreamingSTTConfig, *, ws_url: str) -> str:
    params: dict[str, str] = {
        "language_code": config.language_code,
        "model": REALTIME_STT_MODEL,
        "stream_type": config.stream_type,
        "mode": config.mode,
        "endpointing": config.endpointing,
        "encoding": config.encoding,
        "sample_rate": str(config.sample_rate),
        "return_timestamps": "true" if config.return_timestamps else "false",
        "threshold": str(config.threshold),
        "prefix_padding_ms": str(config.prefix_padding_ms),
        "silence_duration_ms": str(config.silence_duration_ms),
        "min_speech_duration_ms": str(config.min_speech_duration_ms),
    }
    if config.prompt:
        params["prompt"] = config.prompt
    return f"{ws_url}?{urllib.parse.urlencode(params)}"


def _parse_event(data: dict) -> STTEvent | None:
    """Returns None for an event type this module doesn't model — forward-
    compatible, same policy as transport/schemas.py::parse_twilio_event:
    an unrecognized event is ignored by the caller, never crashes the
    consuming loop."""
    event = data.get("event")
    if event == "session.begin":
        return STTSessionStarted(request_id=data.get("request_id"), raw=data)
    if event == "session.end":
        return STTSessionEnded(
            request_id=data.get("request_id"), total_duration_s=data.get("total_duration_s"),
            total_utterances=data.get("total_utterances"), audio_duration_s=data.get("audio_duration_s"), raw=data,
        )
    if event == "vad.speech_start":
        return SpeechStarted(utterance_idx=data.get("utterance_idx"), provider_confidence=data.get("confidence"), raw=data)
    if event == "vad.speech_end":
        return SpeechEnded(utterance_idx=data.get("utterance_idx"), provider_confidence=data.get("confidence"), raw=data)
    if event == "transcript.partial":
        return PartialTranscript(
            utterance_idx=data.get("utterance_idx"), text=data.get("text") or "",
            detected_language_code=data.get("language"), raw=data,
        )
    if event == "transcript.final":
        return FinalTranscript(
            utterance_idx=data.get("utterance_idx"), text=(data.get("text") or "").strip(),
            detected_language_code=data.get("language"), language_probability=data.get("language_confidence"),
            start_s=data.get("start_s"), end_s=data.get("end_s"), provider_confidence=None, raw=data,
        )
    if event == "config.update.ack" or event == "config.updated":
        return STTReconfigured(raw=data)
    if event == "error":
        return STTError(
            code=data.get("code"), message=data.get("message") or "", is_fatal=bool(data.get("is_fatal", False)),
            status_code=data.get("status_code"), raw=data,
        )
    return None


class SarvamStreamingSTT:
    def __init__(self, *, api_key: str, config: StreamingSTTConfig, ws_url: str = REALTIME_STT_WS_URL):
        if not api_key:
            raise NotConfiguredError("SARVAM_API_KEY is not set")
        self._api_key = api_key
        self._config = config
        self._ws_url = ws_url
        self._ws: ClientConnection | None = None
        self._closed = False

    @property
    def capabilities(self) -> STTCapabilities:
        return CAPABILITIES

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            _build_connect_url(self._config, ws_url=self._ws_url),
            additional_headers={"Api-Subscription-Key": self._api_key},
            ping_interval=PING_INTERVAL_SECONDS, ping_timeout=20.0, open_timeout=10.0,
        )

    async def send_audio(self, pcm16_bytes: bytes) -> None:
        if self._ws is None:
            raise SarvamStreamingSTTError("send_audio() called before connect()")
        await self._ws.send(json.dumps({"event": "audio_input", "audio": base64.b64encode(pcm16_bytes).decode("ascii")}))

    async def flush(self) -> None:
        if self._ws is None:
            raise SarvamStreamingSTTError("flush() called before connect()")
        await self._ws.send(json.dumps({"event": "flush"}))

    async def reconfigure(self, **kwargs: object) -> None:
        if self._ws is None:
            raise SarvamStreamingSTTError("reconfigure() called before connect()")
        await self._ws.send(json.dumps({"event": "config.update", **kwargs}))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"event": "end"}))
        except Exception:  # noqa: BLE001 — socket may already be dead; close() must never raise
            pass
        try:
            await self._ws.close()
        except Exception:  # noqa: BLE001 — see above
            pass

    async def events(self) -> AsyncIterator[STTEvent]:
        if self._ws is None:
            raise SarvamStreamingSTTError("events() called before connect()")
        async for raw_message in self._ws:
            try:
                data = json.loads(raw_message)
            except (TypeError, ValueError):
                continue
            event = _parse_event(data)
            if event is not None:
                yield event
