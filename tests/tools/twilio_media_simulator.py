"""Twilio Media Streams simulator (spec §77) — sends the same
connected/start/media/mark/stop event sequence a real Twilio call would,
so the WebSocket transport (services/api/app/modules/live_call/transport/)
can be exercised without a paid phone call.

Dual-purpose: the event-builder functions below are pure (no I/O) and are
what services/api/tests/test_twilio_media_stream.py imports directly
against FastAPI's in-process TestClient — no real network, no real Twilio,
no real server process needed for the automated test suite. `main()` below
is the standalone version: a real `websockets` client against an actually
running `uvicorn` process, for manual local debugging (e.g. pointed at
`ws://localhost:8000/api/v1/live-call/ws/twilio/media/{token}` with a
token minted by a real `start_live_test_call` with
TWILIO_VOICE_TRANSPORT=media_stream).

Run standalone:
    uv run --package jkr-api python tests/tools/twilio_media_simulator.py <ws_url>
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import struct
import sys

TWILIO_SAMPLE_RATE = 8000
FRAME_MS = 20  # Twilio's own inbound media chunking convention
SAMPLES_PER_FRAME = TWILIO_SAMPLE_RATE * FRAME_MS // 1000  # 160


def _pcm16_tone_frame(*, amplitude: int = 8000, freq: int = 440) -> bytes:
    samples = [int(amplitude * math.sin(2 * math.pi * freq * i / TWILIO_SAMPLE_RATE)) for i in range(SAMPLES_PER_FRAME)]
    return struct.pack("<" + "h" * SAMPLES_PER_FRAME, *samples)


def _pcm16_silence_frame() -> bytes:
    return b"\x00\x00" * SAMPLES_PER_FRAME


def _mulaw_b64(pcm16_bytes: bytes) -> str:
    import audioop  # noqa: DEP001 — see app/modules/live_call/transport/audio_codec.py's module docstring

    return base64.b64encode(audioop.lin2ulaw(pcm16_bytes, 2)).decode("ascii")


def build_connected_event() -> dict:
    return {"event": "connected", "protocol": "Call", "version": "1.0.0"}


def build_start_event(*, stream_sid: str, call_sid: str, account_sid: str = "AC_SIMULATED", sequence: str = "1") -> dict:
    return {
        "event": "start",
        "sequenceNumber": sequence,
        "streamSid": stream_sid,
        "start": {
            "accountSid": account_sid,
            "streamSid": stream_sid,
            "callSid": call_sid,
            "tracks": ["inbound"],
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": TWILIO_SAMPLE_RATE, "channels": 1},
            "customParameters": {},
        },
    }


def build_media_event(*, stream_sid: str, payload_b64: str, chunk: str, timestamp_ms: int, sequence: str) -> dict:
    return {
        "event": "media",
        "sequenceNumber": sequence,
        "streamSid": stream_sid,
        "media": {"track": "inbound", "chunk": chunk, "timestamp": str(timestamp_ms), "payload": payload_b64},
    }


def build_mark_event(*, stream_sid: str, name: str, sequence: str) -> dict:
    return {"event": "mark", "sequenceNumber": sequence, "streamSid": stream_sid, "mark": {"name": name}}


def build_stop_event(*, stream_sid: str, call_sid: str, account_sid: str = "AC_SIMULATED", sequence: str = "999") -> dict:
    return {"event": "stop", "sequenceNumber": sequence, "streamSid": stream_sid, "stop": {"accountSid": account_sid, "callSid": call_sid}}


def build_speech_and_silence_sequence(
    *, stream_sid: str, speech_frames: int = 25, silence_frames: int = 220, start_chunk: int = 1
) -> list[dict]:
    """~500ms of a 440Hz tone (stands in for speech — real speech isn't
    needed to exercise the transport/buffering logic, only enough signal
    energy to clear TurnBuffer's silence-RMS threshold) followed by enough
    silence to cross TRAILING_SILENCE_SECONDS and trigger a turn."""
    events: list[dict] = []
    chunk = start_chunk
    timestamp = 0
    for _ in range(speech_frames):
        events.append(build_media_event(stream_sid=stream_sid, payload_b64=_mulaw_b64(_pcm16_tone_frame()), chunk=str(chunk), timestamp_ms=timestamp, sequence=str(chunk + 1)))
        chunk += 1
        timestamp += FRAME_MS
    for _ in range(silence_frames):
        events.append(build_media_event(stream_sid=stream_sid, payload_b64=_mulaw_b64(_pcm16_silence_frame()), chunk=str(chunk), timestamp_ms=timestamp, sequence=str(chunk + 1)))
        chunk += 1
        timestamp += FRAME_MS
    return events


def build_short_speech_burst(*, stream_sid: str, speech_frames: int = 8, start_chunk: int = 1) -> list[dict]:
    """A brief burst of speech with NO trailing silence — enough for a real
    streaming STT connection to plausibly emit a transcript.partial event,
    deliberately not enough to ever reach a completed turn. Used by
    --partial to probe early-partial latency by hand against server logs,
    never against a batch/<Record> path (which has no partial concept)."""
    events: list[dict] = []
    chunk = start_chunk
    timestamp = 0
    for _ in range(speech_frames):
        events.append(build_media_event(stream_sid=stream_sid, payload_b64=_mulaw_b64(_pcm16_tone_frame()), chunk=str(chunk), timestamp_ms=timestamp, sequence=str(chunk + 1)))
        chunk += 1
        timestamp += FRAME_MS
    return events


async def main() -> None:
    """Manual local debugging against a REAL running server (real Sarvam
    connection if STT_MODE=streaming — this tool sends Twilio-shaped audio
    over the wire, it does not and cannot inject fake Sarvam server-side
    events, since those only ever exist inside the server's own persistent
    STT connection). --partial/--final/--speech-events/--disconnect select
    audio/connection SCENARIOS that exercise different parts of the
    streaming STT path; actually observing partial vs. final transcript
    behavior means watching the server's own structured logs
    (stt_stream_* events — see docs/SARVAM_STREAMING_STT_CONTRACT.md and
    transport/streaming_bridge.py) in parallel with this tool's output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ws_url", help="Full wss://.../ws/twilio/media/{token} URL (token from a real start_live_test_call in media_stream mode)")
    parser.add_argument("--call-sid", default="CA_SIMULATED")
    parser.add_argument("--stream-sid", default="MZ_SIMULATED")
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument(
        "--final", action="store_true",
        help="Default scenario: one full speech-then-silence utterance, wait for the agent's reply.",
    )
    scenario.add_argument(
        "--partial", action="store_true",
        help="Send a short speech burst with no trailing silence, then exit immediately — for eyeballing "
        "early transcript.partial / stt_stream_first_partial behavior in server logs before any final would fire.",
    )
    scenario.add_argument(
        "--speech-events", action="store_true",
        help="Send THREE separate speech-then-pause cycles in one call (multiple utterances), to watch "
        "several speech-start/partial/final cycles and dedup behavior over a longer session.",
    )
    scenario.add_argument(
        "--disconnect", action="store_true",
        help="Send a short speech burst then abruptly close the raw connection (no clean `stop` event) — "
        "for manually verifying the server's watchdog / streaming-STT reconnect-or-teardown behavior.",
    )
    args = parser.parse_args()

    import websockets

    async with websockets.connect(args.ws_url) as ws:
        await ws.send(json.dumps(build_connected_event()))
        await ws.send(json.dumps(build_start_event(stream_sid=args.stream_sid, call_sid=args.call_sid)))
        print("sent connected + start, waiting for greeting...", file=sys.stderr)

        async def _print_incoming() -> None:
            async for message in ws:
                data = json.loads(message)
                if data.get("event") == "media":
                    print(f"<- media (payload {len(data['media']['payload'])} b64 chars)")
                else:
                    print("<-", data)

        listener = asyncio.create_task(_print_incoming())
        await asyncio.sleep(2)  # let the greeting play out

        if args.partial:
            for event in build_short_speech_burst(stream_sid=args.stream_sid):
                await ws.send(json.dumps(event))
                await asyncio.sleep(FRAME_MS / 1000)
            print("sent a short speech burst (no trailing silence) — check server logs for stt_stream_* events", file=sys.stderr)
            await asyncio.sleep(3)
            listener.cancel()
            return

        if args.disconnect:
            for event in build_short_speech_burst(stream_sid=args.stream_sid):
                await ws.send(json.dumps(event))
                await asyncio.sleep(FRAME_MS / 1000)
            print("mid-speech — closing the connection abruptly (no stop event) to simulate a dropped call", file=sys.stderr)
            listener.cancel()
            return

        turns = 3 if args.speech_events else 1
        chunk = 1
        for turn_index in range(turns):
            for event in build_speech_and_silence_sequence(stream_sid=args.stream_sid, start_chunk=chunk):
                await ws.send(json.dumps(event))
                await asyncio.sleep(FRAME_MS / 1000)
                chunk = int(event["media"]["chunk"]) + 1
            print(f"sent utterance {turn_index + 1}/{turns}, waiting for reply...", file=sys.stderr)
            await asyncio.sleep(8)

        await ws.send(json.dumps(build_stop_event(stream_sid=args.stream_sid, call_sid=args.call_sid)))
        listener.cancel()


if __name__ == "__main__":
    asyncio.run(main())
