from __future__ import annotations

from app.modules.live_call.transport.schemas import (
    TwilioConnectedEvent,
    TwilioMarkEvent,
    TwilioMediaEvent,
    TwilioStartEvent,
    TwilioStopEvent,
    build_outbound_clear_message,
    build_outbound_mark_message,
    build_outbound_media_message,
    parse_twilio_event,
)


def test_parses_connected_event():
    raw = {"event": "connected", "protocol": "Call", "version": "1.0.0"}
    parsed = parse_twilio_event(raw)
    assert isinstance(parsed, TwilioConnectedEvent)


def test_parses_start_event_with_exact_verified_field_names():
    raw = {
        "event": "start", "sequenceNumber": "1", "streamSid": "MZ1",
        "start": {
            "accountSid": "AC1", "streamSid": "MZ1", "callSid": "CA1", "tracks": ["inbound"],
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            "customParameters": {"SessionToken": "abc"},
        },
    }
    parsed = parse_twilio_event(raw)
    assert isinstance(parsed, TwilioStartEvent)
    assert parsed.start.callSid == "CA1"
    assert parsed.start.mediaFormat.encoding == "audio/x-mulaw"
    assert parsed.start.mediaFormat.sampleRate == 8000
    assert parsed.start.customParameters["SessionToken"] == "abc"


def test_parses_media_event_with_top_level_sequence_number():
    raw = {
        "event": "media", "sequenceNumber": "4", "streamSid": "MZ1",
        "media": {"track": "inbound", "chunk": "2", "timestamp": "5", "payload": "no+JhoaJjpzS"},
    }
    parsed = parse_twilio_event(raw)
    assert isinstance(parsed, TwilioMediaEvent)
    assert parsed.sequenceNumber == "4"  # top-level, not nested inside media
    assert parsed.media.payload == "no+JhoaJjpzS"


def test_parses_mark_event():
    raw = {"event": "mark", "sequenceNumber": "4", "streamSid": "MZ1", "mark": {"name": "my label"}}
    parsed = parse_twilio_event(raw)
    assert isinstance(parsed, TwilioMarkEvent)
    assert parsed.mark.name == "my label"


def test_parses_stop_event():
    raw = {"event": "stop", "sequenceNumber": "5", "streamSid": "MZ1", "stop": {"accountSid": "AC1", "callSid": "CA1"}}
    parsed = parse_twilio_event(raw)
    assert isinstance(parsed, TwilioStopEvent)
    assert parsed.stop.callSid == "CA1"


def test_unrecognized_event_type_returns_raw_dict_not_a_crash():
    raw = {"event": "some_future_event_type", "streamSid": "MZ1"}
    parsed = parse_twilio_event(raw)
    assert parsed == raw  # forward-compatible: never crashes the receive loop on an unknown event


def test_outbound_media_message_shape_matches_twilio_contract():
    msg = build_outbound_media_message(stream_sid="MZ1", payload_b64="abc123")
    assert msg == {"event": "media", "streamSid": "MZ1", "media": {"payload": "abc123"}}


def test_outbound_mark_message_shape_matches_twilio_contract():
    msg = build_outbound_mark_message(stream_sid="MZ1", name="jkr-mark-1")
    assert msg == {"event": "mark", "streamSid": "MZ1", "mark": {"name": "jkr-mark-1"}}


def test_outbound_clear_message_shape_matches_twilio_contract():
    msg = build_outbound_clear_message(stream_sid="MZ1")
    assert msg == {"event": "clear", "streamSid": "MZ1"}
