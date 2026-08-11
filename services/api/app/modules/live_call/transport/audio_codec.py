"""Audio format conversion at the Twilio Media Streams transport boundary
— everything downstream (the transitional STT/TTS bridge in
twilio_media_stream.py today; a real streaming STT/TTS provider in P3+)
works in PCM16, never Twilio's wire format directly, so a future
non-Twilio transport wouldn't need this module at all.

Twilio Media Streams' codec is fixed, not configurable (confirmed against
current Twilio docs, not assumed): audio/x-mulaw, 8000 Hz, mono. See
schemas.py's module docstring for the verification.

Uses stdlib `audioop` — deprecated since Python 3.11, removed in 3.13, but
this project is pinned to Python 3.12 (pyproject.toml
`requires-python = ">=3.12,<3.13"`). If that pin ever moves past 3.12,
swap this import for the `audioop-lts` PyPI backport (drop-in same API)
rather than hand-rolling mu-law conversion.
"""

from __future__ import annotations

import audioop  # noqa: DEP001 — see module docstring; project is pinned to Python 3.12
import base64
import io
import wave

TWILIO_SAMPLE_RATE = 8000
TWILIO_CHANNELS = 1
_PCM16_SAMPLE_WIDTH = 2  # audioop represents every decoded sample as 16-bit PCM
_MULAW_SAMPLE_WIDTH = 1  # one byte per sample — this is what makes "8000 bytes ~= 1 second" true at 8kHz


def audio_duration_ms(*, byte_length: int, codec: str, sample_rate: int, channels: int = 1) -> int:
    """P7 — centralizes the duration math spec §75-76 asks for, rather than
    scattering "8000 bytes ~= 1 second" assumptions across coordinator/
    playback-accounting code. `codec` is "mulaw" (one byte/sample — Sarvam's
    verified direct streaming output, see docs/SARVAM_STREAMING_TTS_CONTRACT.md)
    or "pcm16" (two bytes/sample — the batch-TTS path). Any other value
    raises rather than silently guessing a sample width."""
    if channels < 1:
        raise ValueError(f"channels must be >= 1, got {channels}")
    if codec == "mulaw":
        sample_width = _MULAW_SAMPLE_WIDTH
    elif codec == "pcm16":
        sample_width = _PCM16_SAMPLE_WIDTH
    else:
        raise ValueError(f"unknown codec for duration calculation: {codec!r}")
    frame_bytes = sample_width * channels
    if frame_bytes == 0 or sample_rate <= 0:
        return 0
    sample_count = byte_length / frame_bytes
    return round((sample_count / sample_rate) * 1000)


def decode_twilio_media_payload(payload_b64: str) -> bytes:
    """Twilio's `media.payload` (base64 mu-law) -> raw PCM16 mono @ 8kHz."""
    mulaw_bytes = base64.b64decode(payload_b64)
    return audioop.ulaw2lin(mulaw_bytes, _PCM16_SAMPLE_WIDTH)


def encode_twilio_media_payload(pcm16_bytes: bytes, *, sample_rate: int) -> str:
    """PCM16 mono bytes at `sample_rate` -> Twilio's expected base64 mu-law
    @ 8kHz payload for an outbound `media` message. Resamples first if the
    source isn't already 8kHz (e.g. Sarvam TTS's actual output rate)."""
    if sample_rate != TWILIO_SAMPLE_RATE:
        pcm16_bytes, _ = audioop.ratecv(pcm16_bytes, _PCM16_SAMPLE_WIDTH, TWILIO_CHANNELS, sample_rate, TWILIO_SAMPLE_RATE, None)
    mulaw_bytes = audioop.lin2ulaw(pcm16_bytes, _PCM16_SAMPLE_WIDTH)
    return base64.b64encode(mulaw_bytes).decode("ascii")


def wav_bytes_to_pcm16(wav_bytes: bytes) -> tuple[bytes, int, int]:
    """Returns (pcm16_mono_bytes, sample_rate, channels) — reads the WAV
    header rather than assuming a fixed sample rate, since Sarvam TTS's
    actual output rate isn't hardcoded anywhere in this codebase and
    shouldn't be assumed here either."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != _PCM16_SAMPLE_WIDTH:
        frames = audioop.lin2lin(frames, sample_width, _PCM16_SAMPLE_WIDTH)
    if channels > 1:
        frames = audioop.tomono(frames, _PCM16_SAMPLE_WIDTH, 0.5, 0.5)
        channels = 1
    return frames, sample_rate, channels


def pcm16_to_wav_bytes(pcm16_bytes: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    """The inverse of wav_bytes_to_pcm16 — used by the transitional bridge
    to hand accumulated inbound audio to the existing, unchanged SarvamSTT
    client, which expects a WAV file (see ../../live_providers/sarvam_stt.py),
    not raw PCM."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(_PCM16_SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16_bytes)
    return buffer.getvalue()
