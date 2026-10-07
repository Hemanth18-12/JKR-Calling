"""Real Cartesia streaming TTS WebSocket client (`sonic-3.6`) — streaming
counterpart to `cartesia_tts.py`'s batch REST client.

Implements the StreamingTTSProvider Protocol in streaming_tts.py.
Connects to Cartesia's WebSocket endpoint at wss://api.cartesia.ai/tts/websocket.
Produces raw headerless mu-law audio chunks at 8000 Hz, matching Twilio's Media Streams.
"""

from __future__ import annotations

import base64
import json
import logging
import os
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

logger = logging.getLogger(__name__)

CARTESIA_TTS_WS_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_VERSION = "2024-11-13"
DEFAULT_CARTESIA_MODEL = "sonic-3.6"
DEFAULT_CARTESIA_VOICE = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"

CAPABILITIES = TTSCapabilities(
    supports_streaming_input=True,
    supports_streaming_audio=True,
    supports_flush=True,
    supports_completion_event=True,
    supports_live_reconfiguration=False,
    supports_pronunciation_dictionary=True,
    supports_direct_mulaw_8k=True,  # Cartesia natively outputs pcm_mulaw at 8000 Hz
    supports_cancel=True,
)

_ERROR_CODE_PREFIX = re.compile(r"^(\d{3}):\s*")


class NotConfiguredError(RuntimeError):
    """Raised when CARTESIA_API_KEY is absent."""


class CartesiaStreamingTTSError(RuntimeError):
    """Raised for a send/receive attempted before connect(), or after close()."""


def _classify_error(message: str, *, status_code: int | None = None) -> TTSFailureClass:
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
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return TTSFailureClass.TIMEOUT
    if "auth" in lower or "unauthorized" in lower or "forbidden" in lower:
        return TTSFailureClass.AUTH_ERROR
    if "rate limit" in lower:
        return TTSFailureClass.RATE_LIMIT
    return TTSFailureClass.UNKNOWN


def _map_language_code(code: str) -> str:
    clean = code.lower().strip()
    if clean.startswith("te"):
        return "te"
    if clean.startswith("hi"):
        return "hi"
    if clean.startswith("en"):
        return "en"
    return clean.split("-")[0]


class CartesiaStreamingTTS:
    """Persistent WebSocket streaming TTS provider for Cartesia."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        ws_url: str = CARTESIA_TTS_WS_URL,
        model: str = DEFAULT_CARTESIA_MODEL,
        default_voice_id: str = DEFAULT_CARTESIA_VOICE,
    ):
        key = api_key or os.getenv("CARTESIA_API_KEY", "")
        if not key:
            raise NotConfiguredError("CARTESIA_API_KEY is not set")
        self._api_key = key
        self._ws_url = ws_url
        self._model = model
        self._default_voice_id = default_voice_id
        self._ws: ClientConnection | None = None
        self._closed = False

        self._active_response_id: str | None = None
        self._audio_chunk_index_by_response: dict[str, int] = {}
        self._first_audio_seen: set[str] = set()
        self._cancelled_response_ids: set[str] = set()
        self._config: StreamingTTSConfig | None = None

    @property
    def capabilities(self) -> TTSCapabilities:
        return CAPABILITIES

    async def connect(self, *, config: StreamingTTSConfig, context: TTSCallContext) -> None:
        self._config = config
        model = config.model if config.model and config.model != "bulbul:v3" else self._model
        self._model = model

        url = f"{self._ws_url}?cartesia_version={CARTESIA_VERSION}&api_key={self._api_key}"
        self._ws = await websockets.connect(
            url,
            additional_headers={"X-API-Key": self._api_key, "Cartesia-Version": CARTESIA_VERSION},
            open_timeout=10.0,
        )
        logger.info(
            "Connected Cartesia streaming TTS WebSocket (model=%s, lang=%s)",
            self._model,
            config.target_language_code,
        )

    def _get_voice_id(self) -> str:
        if self._config and self._config.voice_id:
            return self._config.voice_id
        return os.getenv("CARTESIA_VOICE_ID") or self._default_voice_id

    def _get_language(self) -> str:
        if self._config and self._config.target_language_code:
            return _map_language_code(self._config.target_language_code)
        return "en"

    async def send_text(self, *, text: str, response_id: str, chunk_index: int) -> None:
        if self._ws is None:
            raise CartesiaStreamingTTSError("send_text() called before connect()")
        self._active_response_id = response_id
        self._audio_chunk_index_by_response.setdefault(response_id, 0)

        payload = {
            "context_id": response_id,
            "model_id": self._model,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": self._get_voice_id(),
            },
            "output_format": {
                "container": "raw",
                "encoding": "pcm_mulaw",
                "sample_rate": 8000,
            },
            "language": self._get_language(),
            "continue": True,
        }
        if self._config and self._config.pace != 1.0:
            payload["generation_config"] = {"speed": self._config.pace}

        await self._ws.send(json.dumps(payload))

    async def flush(self, *, response_id: str) -> None:
        if self._ws is None:
            raise CartesiaStreamingTTSError("flush() called before connect()")
        self._active_response_id = response_id

        payload = {
            "context_id": response_id,
            "model_id": self._model,
            "transcript": "",
            "voice": {
                "mode": "id",
                "id": self._get_voice_id(),
            },
            "output_format": {
                "container": "raw",
                "encoding": "pcm_mulaw",
                "sample_rate": 8000,
            },
            "language": self._get_language(),
            "continue": False,
        }
        await self._ws.send(json.dumps(payload))

    async def cancel(self, response_id: str) -> None:
        """Cancel an in-flight synthesis for this response."""
        self._cancelled_response_ids.add(response_id)
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"context_id": response_id, "cancel": True}))
            except Exception:
                pass

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._ws is None:
            return
        try:
            await self._ws.close()
        except Exception:
            pass

    async def events(self) -> AsyncIterator[TTSStreamEvent]:
        if self._ws is None:
            raise CartesiaStreamingTTSError("events() called before connect()")
        async for raw_message in self._ws:
            try:
                msg = json.loads(raw_message)
            except (TypeError, ValueError):
                continue
            for event in self._parse_event(msg):
                yield event

    def _parse_event(self, msg: dict) -> list[TTSStreamEvent]:
        mtype = msg.get("type")
        context_id = msg.get("context_id") or self._active_response_id
        response_id = context_id

        # Cartesia chunk message: type == "chunk" with "data" or "audio" base64
        if mtype == "chunk" or "data" in msg or "audio" in msg:
            if response_id is None:
                return []
            if response_id in self._cancelled_response_ids:
                return []
            b64 = msg.get("data") or msg.get("audio") or ""
            decoded = base64.b64decode(b64) if b64 else b""
            if not decoded:
                return []
            index = self._audio_chunk_index_by_response.get(response_id, 0)
            self._audio_chunk_index_by_response[response_id] = index + 1
            events: list[TTSStreamEvent] = []
            if response_id not in self._first_audio_seen:
                self._first_audio_seen.add(response_id)
                events.append(TTSFirstAudio(response_id=response_id))
            events.append(
                TTSAudioChunk(
                    response_id=response_id,
                    audio_chunk_index=index,
                    data=decoded,
                    content_type="audio/basic",
                    codec="mulaw",
                    sample_rate=8000,
                )
            )
            return events

        # Cartesia done/completed event: type == "done" or type == "timestamps"
        if mtype in ("done", "flush_done"):
            if response_id is None:
                return []
            if response_id in self._cancelled_response_ids:
                return [TTSStreamCancelled(response_id=response_id)]
            return [TTSGenerationCompleted(response_id=response_id)]

        if mtype == "error":
            message = msg.get("error") or msg.get("message") or "unknown Cartesia error"
            return [
                TTSStreamFailed(
                    response_id=response_id,
                    failure_class=_classify_error(message, status_code=msg.get("code") or msg.get("status_code")),
                    message=message,
                )
            ]

        return []
