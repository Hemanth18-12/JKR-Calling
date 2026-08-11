from __future__ import annotations

from app.config import Settings


def test_effective_tts_mode_defaults_to_batch():
    settings = Settings()
    assert settings.tts_mode == "batch"
    assert settings.effective_tts_mode == "batch"


def test_effective_tts_mode_streaming_requires_media_stream_transport():
    settings = Settings(tts_mode="streaming", twilio_voice_transport="record")
    assert settings.effective_tts_mode == "batch"  # silently degrades — spec §13, no combination nothing implements


def test_effective_tts_mode_streaming_with_media_stream_transport():
    settings = Settings(tts_mode="streaming", twilio_voice_transport="media_stream")
    assert settings.effective_tts_mode == "streaming"


def test_tts_stream_failure_policy_defaults_to_batch_fallback():
    settings = Settings()
    assert settings.tts_stream_failure_policy == "batch_fallback"


def test_barge_in_defaults_disabled():
    settings = Settings()
    assert settings.barge_in_enabled is False
    assert settings.barge_in_sensitivity == "balanced"
    assert settings.effective_barge_in_enabled is False


def test_effective_barge_in_enabled_requires_full_realtime_stack():
    settings = Settings(
        barge_in_enabled=True, twilio_voice_transport="media_stream", stt_mode="streaming",
        tts_mode="streaming", turn_detection_mode="hybrid",
    )
    assert settings.effective_barge_in_enabled is True


def test_effective_barge_in_enabled_stays_false_without_streaming_tts():
    settings = Settings(
        barge_in_enabled=True, twilio_voice_transport="media_stream", stt_mode="streaming",
        tts_mode="batch", turn_detection_mode="hybrid",
    )
    assert settings.effective_barge_in_enabled is False


def test_effective_barge_in_enabled_stays_false_under_provider_turn_detection():
    settings = Settings(
        barge_in_enabled=True, twilio_voice_transport="media_stream", stt_mode="streaming",
        tts_mode="streaming", turn_detection_mode="provider",
    )
    assert settings.effective_barge_in_enabled is False


def test_effective_barge_in_enabled_stays_false_when_flag_itself_is_off():
    settings = Settings(
        barge_in_enabled=False, twilio_voice_transport="media_stream", stt_mode="streaming",
        tts_mode="streaming", turn_detection_mode="hybrid",
    )
    assert settings.effective_barge_in_enabled is False
