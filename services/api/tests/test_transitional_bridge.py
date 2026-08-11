from __future__ import annotations

import math
import struct

from app.modules.live_call.transport.base import AudioFrame
from app.modules.live_call.transport.transitional_bridge import (
    MIN_SPEECH_MS_TO_COUNT,
    TRAILING_SILENCE_SECONDS,
    TurnBuffer,
)


def _tone_frame(*, sample_rate: int = 8000, ms: int = 20, amplitude: int = 8000, freq: int = 440) -> AudioFrame:
    n = int(sample_rate * ms / 1000)
    samples = [int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n)]
    data = struct.pack("<" + "h" * n, *samples)
    return AudioFrame(data=data, codec="pcm16", sample_rate=sample_rate, channels=1)


def _silence_frame(*, sample_rate: int = 8000, ms: int = 20) -> AudioFrame:
    n = int(sample_rate * ms / 1000)
    return AudioFrame(data=b"\x00\x00" * n, codec="pcm16", sample_rate=sample_rate, channels=1)


def test_speech_then_trailing_silence_completes_a_turn():
    buf = TurnBuffer()
    for _ in range(25):  # 500ms of speech, well over MIN_SPEECH_MS_TO_COUNT
        buf.add_frame(_tone_frame())
    assert buf.has_speech() is True
    assert buf.is_turn_complete() is False  # no trailing silence yet

    silence_frames_needed = int(TRAILING_SILENCE_SECONDS * 1000 / 20) + 5
    for _ in range(silence_frames_needed):
        buf.add_frame(_silence_frame())
    assert buf.is_turn_complete() is True


def test_pure_silence_never_completes_a_turn_even_past_max_duration():
    # The exact bug class this must never reproduce: calling STT on a
    # buffer that's nothing but silence.
    buf = TurnBuffer()
    for _ in range(1100):  # 22s of silence, over MAX_TURN_SECONDS
        buf.add_frame(_silence_frame())
    assert buf.has_speech() is False
    assert buf.is_turn_complete() is False
    assert buf.is_over_max_duration() is True


def test_brief_noise_below_min_speech_threshold_does_not_count_as_speech():
    buf = TurnBuffer()
    # One 20ms frame of tone is far below MIN_SPEECH_MS_TO_COUNT.
    buf.add_frame(_tone_frame(ms=20))
    assert buf.speech_ms < MIN_SPEECH_MS_TO_COUNT
    assert buf.has_speech() is False


def test_new_speech_resets_trailing_silence_counter():
    buf = TurnBuffer()
    for _ in range(25):
        buf.add_frame(_tone_frame())
    for _ in range(100):  # 2s of silence — not yet a full turn
        buf.add_frame(_silence_frame())
    assert buf.is_turn_complete() is False
    buf.add_frame(_tone_frame())  # customer starts talking again
    assert buf.trailing_silence_ms == 0.0


def test_reset_clears_everything():
    buf = TurnBuffer()
    for _ in range(25):
        buf.add_frame(_tone_frame())
    buf.reset()
    assert buf.has_speech() is False
    assert buf.total_ms == 0.0
    assert buf.trailing_silence_ms == 0.0


def test_build_wav_produces_a_valid_wav_header():
    buf = TurnBuffer()
    for _ in range(10):
        buf.add_frame(_tone_frame())
    wav_bytes = buf.build_wav()
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"
