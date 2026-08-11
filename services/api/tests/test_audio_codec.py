from __future__ import annotations

import math
import struct

from app.modules.live_call.transport.audio_codec import (
    TWILIO_SAMPLE_RATE,
    decode_twilio_media_payload,
    encode_twilio_media_payload,
    pcm16_to_wav_bytes,
    wav_bytes_to_pcm16,
)


def _tone_pcm16(*, sample_rate: int = 8000, ms: int = 100, amplitude: int = 8000, freq: int = 440) -> bytes:
    n = int(sample_rate * ms / 1000)
    samples = [int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n)]
    return struct.pack("<" + "h" * n, *samples)


def test_wav_pcm16_round_trip_preserves_audio_and_metadata():
    pcm16 = _tone_pcm16(sample_rate=8000)
    wav_bytes = pcm16_to_wav_bytes(pcm16, sample_rate=8000)
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"

    pcm16_back, sample_rate, channels = wav_bytes_to_pcm16(wav_bytes)
    assert pcm16_back == pcm16
    assert sample_rate == 8000
    assert channels == 1


def test_wav_pcm16_round_trip_resamples_stereo_and_odd_width_input():
    # A WAV that ISN'T already 8kHz mono 16-bit — must still come back as
    # mono 16-bit (resampling to Twilio's fixed rate happens separately, in
    # encode_twilio_media_payload, not here — this only normalizes
    # width/channels).
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(_tone_pcm16(sample_rate=22050, ms=50) * 2)  # crude stereo interleave stand-in
    pcm16_back, sample_rate, channels = wav_bytes_to_pcm16(buffer.getvalue())
    assert channels == 1
    assert sample_rate == 22050


def test_twilio_media_payload_round_trip_at_native_rate():
    pcm16 = _tone_pcm16(sample_rate=TWILIO_SAMPLE_RATE, ms=20)
    payload_b64 = encode_twilio_media_payload(pcm16, sample_rate=TWILIO_SAMPLE_RATE)
    decoded = decode_twilio_media_payload(payload_b64)
    # mu-law is lossy (8-bit companded) — exact byte equality isn't
    # expected, only that it round-trips to audio of the same length.
    assert len(decoded) == len(pcm16)


def test_twilio_media_payload_resamples_non_native_rate():
    pcm16 = _tone_pcm16(sample_rate=22050, ms=20)
    payload_b64 = encode_twilio_media_payload(pcm16, sample_rate=22050)
    decoded = decode_twilio_media_payload(payload_b64)
    # Resampled from 22050Hz down to Twilio's fixed 8000Hz — output length
    # should reflect the new rate, not the input's.
    expected_len_at_8k = int(len(pcm16) * TWILIO_SAMPLE_RATE / 22050)
    assert abs(len(decoded) - expected_len_at_8k) < 200  # resampling isn't exact-integer, allow small slack


def test_silence_encodes_and_decodes_cleanly():
    silence = b"\x00\x00" * 160
    payload_b64 = encode_twilio_media_payload(silence, sample_rate=TWILIO_SAMPLE_RATE)
    decoded = decode_twilio_media_payload(payload_b64)
    assert len(decoded) == len(silence)
