from __future__ import annotations

from app.modules.live_call.turns.signals import TurnSignalType
from app.modules.live_call.turns.vad import EnergyVAD, VADConfig

SAMPLE_RATE = 8000


def _loud_frame(ms: int = 20) -> bytes:
    n_samples = SAMPLE_RATE * ms // 1000
    # PCM16 samples well above the default activation threshold.
    return (b"\xff\x7f") * n_samples  # 0x7fff repeating -> max positive amplitude


def _silence_frame(ms: int = 20) -> bytes:
    n_samples = SAMPLE_RATE * ms // 1000
    return b"\x00\x00" * n_samples


def test_no_signal_on_pure_silence():
    vad = EnergyVAD(VADConfig(min_speech_duration_ms=40, min_silence_duration_ms=40))
    now = 0.0
    for _ in range(10):
        signal = vad.process_frame(_silence_frame(), sample_rate=SAMPLE_RATE, now=now)
        assert signal is None
        now += 0.02


def test_speech_start_emitted_after_min_speech_duration():
    vad = EnergyVAD(VADConfig(min_speech_duration_ms=40, min_silence_duration_ms=40))
    now = 0.0
    first_signal = vad.process_frame(_loud_frame(), sample_rate=SAMPLE_RATE, now=now)
    assert first_signal is None  # not enough accumulated speech yet (one 20ms frame < 40ms threshold)
    now += 0.02
    second_signal = vad.process_frame(_loud_frame(), sample_rate=SAMPLE_RATE, now=now)
    assert second_signal is not None
    assert second_signal.type == TurnSignalType.LOCAL_VAD_SPEECH_START


def test_speech_end_emitted_after_min_silence_duration_following_speech():
    vad = EnergyVAD(VADConfig(min_speech_duration_ms=20, min_silence_duration_ms=40))
    now = 0.0
    vad.process_frame(_loud_frame(), sample_rate=SAMPLE_RATE, now=now)  # triggers speech start
    now += 0.02
    vad.process_frame(_silence_frame(), sample_rate=SAMPLE_RATE, now=now)  # 20ms silence, not enough yet
    now += 0.02
    end_signal = vad.process_frame(_silence_frame(), sample_rate=SAMPLE_RATE, now=now)  # 40ms silence total
    assert end_signal is not None
    assert end_signal.type == TurnSignalType.LOCAL_VAD_SPEECH_END


def test_no_duplicate_start_signals_while_continuously_speaking():
    vad = EnergyVAD(VADConfig(min_speech_duration_ms=20, min_silence_duration_ms=40))
    now = 0.0
    signals = []
    for _ in range(10):
        signals.append(vad.process_frame(_loud_frame(), sample_rate=SAMPLE_RATE, now=now))
        now += 0.02
    starts = [s for s in signals if s is not None and s.type == TurnSignalType.LOCAL_VAD_SPEECH_START]
    assert len(starts) == 1


def test_reset_clears_state():
    vad = EnergyVAD(VADConfig(min_speech_duration_ms=20, min_silence_duration_ms=40))
    vad.process_frame(_loud_frame(), sample_rate=SAMPLE_RATE, now=0.0)
    vad.process_frame(_loud_frame(), sample_rate=SAMPLE_RATE, now=0.02)
    assert vad._is_speaking is True
    vad.reset()
    assert vad._is_speaking is False


def test_empty_frame_returns_none():
    vad = EnergyVAD()
    assert vad.process_frame(b"", sample_rate=SAMPLE_RATE, now=0.0) is None
