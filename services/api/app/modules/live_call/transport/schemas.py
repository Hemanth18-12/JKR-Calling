"""Twilio Media Streams' exact JSON message contract — verified against
Twilio's current official docs (docs.twilio.com/voice/media-streams/
websocket-messages, .../voice/twiml/stream), not guessed or inferred from
older/deprecated examples. Field names here are copied literally from that
contract.

Confirmed facts this module encodes:
- Every inbound message carries `sequenceNumber` (string) and `streamSid`
  at the TOP level, not nested inside the event-specific object.
- `start.mediaFormat.encoding` is always "audio/x-mulaw", `sampleRate`
  always 8000, `channels` always 1 — Twilio's docs state these are fixed,
  not configurable, for classic (non-ConversationRelay) Media Streams.
- Outbound `media`/`mark` messages need `streamSid` at the top level; the
  outbound `media` object has ONLY `payload` (no track/chunk/timestamp —
  those are inbound-only fields). Outbound `clear` has no nested object.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")  # forward-compatible with fields Twilio adds later


class TwilioMediaFormat(_Base):
    encoding: str
    sampleRate: int
    channels: int


class TwilioStartPayload(_Base):
    accountSid: str
    streamSid: str
    callSid: str
    tracks: list[str] = []
    mediaFormat: TwilioMediaFormat
    customParameters: dict[str, str] = {}


class TwilioMediaPayload(_Base):
    track: str
    chunk: str
    timestamp: str
    payload: str  # base64 mu-law audio, no file header


class TwilioMarkPayload(_Base):
    name: str


class TwilioStopPayload(_Base):
    accountSid: str
    callSid: str


class TwilioDtmfPayload(_Base):
    track: str
    digit: str


class TwilioConnectedEvent(_Base):
    event: Literal["connected"]
    protocol: str
    version: str


class TwilioStartEvent(_Base):
    event: Literal["start"]
    sequenceNumber: str
    streamSid: str
    start: TwilioStartPayload


class TwilioMediaEvent(_Base):
    event: Literal["media"]
    sequenceNumber: str
    streamSid: str
    media: TwilioMediaPayload


class TwilioMarkEvent(_Base):
    event: Literal["mark"]
    sequenceNumber: str
    streamSid: str
    mark: TwilioMarkPayload


class TwilioStopEvent(_Base):
    event: Literal["stop"]
    sequenceNumber: str
    streamSid: str
    stop: TwilioStopPayload


class TwilioDtmfEvent(_Base):
    event: Literal["dtmf"]
    sequenceNumber: str
    streamSid: str
    dtmf: TwilioDtmfPayload


def parse_twilio_event(raw: dict) -> object:
    """Dispatches on `event` — returns the matching typed model, or the raw
    dict unchanged for an event type this module doesn't model (forward-
    compatible: an unrecognized event is logged and ignored by the caller,
    never crashes the receive loop)."""
    event = raw.get("event")
    parsers: dict[str, type[BaseModel]] = {
        "connected": TwilioConnectedEvent,
        "start": TwilioStartEvent,
        "media": TwilioMediaEvent,
        "mark": TwilioMarkEvent,
        "stop": TwilioStopEvent,
        "dtmf": TwilioDtmfEvent,
    }
    model = parsers.get(event) if isinstance(event, str) else None
    return model.model_validate(raw) if model is not None else raw


def build_outbound_media_message(*, stream_sid: str, payload_b64: str) -> dict:
    return {"event": "media", "streamSid": stream_sid, "media": {"payload": payload_b64}}


def build_outbound_mark_message(*, stream_sid: str, name: str) -> dict:
    return {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}}


def build_outbound_clear_message(*, stream_sid: str) -> dict:
    return {"event": "clear", "streamSid": stream_sid}
