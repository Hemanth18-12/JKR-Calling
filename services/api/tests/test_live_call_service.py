"""Direct unit tests of the closing-grace mechanism's pure helpers — the
fix for the abrupt-hangup bug (closing audio must fully play, then a real
listening window, before the call actually ends). Twilio's own sequential
TwiML execution (<Play> always finishes before <Record> starts) is what
makes this work, not anything tested here directly; these tests cover the
TwiML this module emits and the state transitions it makes, not a full
Twilio webhook round-trip (which would need mocking signature validation,
Redis, and a live DB session together — out of scope for this module,
same reasoning as the rest of this file's existing test coverage).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.modules.live_call import service
from jkr_db.enums import ProviderName
from jkr_db.models.agents import VoicePersona


def test_webhook_urls_includes_a_distinct_closing_grace_url():
    settings = Settings(public_webhook_base_url="https://example.ngrok.io")
    voice_url, status_url, recording_url, closing_grace_url = service._webhook_urls(settings, "tok123")
    urls = {voice_url, status_url, recording_url, closing_grace_url}
    assert len(urls) == 4  # all four distinct
    assert closing_grace_url == "https://example.ngrok.io/api/v1/live-call/webhooks/twilio/closing-grace/tok123"


def test_speak_then_grace_listen_has_no_hangup_before_record():
    twiml = service._twiml_speak_then_grace_listen("play", "https://x/audio.wav", action_url="https://x/grace")
    play_index = twiml.index("<Play>")
    record_index = twiml.index("<Record")
    hangup_index = twiml.index("<Hangup/>")
    # Sequential TwiML execution means order in the string IS execution
    # order — Play must come before Record, and the (defensive, normally
    # dead) Hangup must come only after Record, never before it.
    assert play_index < record_index < hangup_index


def test_speak_then_grace_listen_record_uses_short_grace_window():
    twiml = service._twiml_speak_then_grace_listen("say", "Goodbye", action_url="https://x/grace")
    assert 'maxLength="6"' in twiml
    assert f'timeout="{service.RECORD_SILENCE_TIMEOUT_SECONDS}"' in twiml
    assert 'action="https://x/grace"' in twiml


def test_record_verbs_use_the_shared_silence_timeout_and_enable_the_beep():
    # playBeep=true is what actually addresses "must speak loudly to be
    # heard" — <Record> has no volume/sensitivity parameter at all, so a
    # beep (a clear "go" cue) is the real fix, not a threshold.
    main_twiml = service._twiml_speak_and_record("say", "hi", action_url="https://x/rec")
    grace_twiml = service._twiml_speak_then_grace_listen("say", "bye", action_url="https://x/grace")
    for twiml in (main_twiml, grace_twiml):
        assert f'timeout="{service.RECORD_SILENCE_TIMEOUT_SECONDS}"' in twiml
        assert 'playBeep="true"' in twiml


def test_speak_then_grace_listen_escapes_say_fallback_text():
    twiml = service._twiml_speak_then_grace_listen("say", "Ravi & Sons <appointment>", action_url="https://x/grace")
    assert "Ravi &amp; Sons &lt;appointment&gt;" in twiml
    assert "<appointment>" not in twiml


def test_hangup_only_has_no_say_or_play():
    twiml = service._twiml_hangup_only()
    assert "<Hangup/>" in twiml
    assert "<Play>" not in twiml
    assert "<Say" not in twiml


def test_reopen_conversation_state_flips_completed_objective_back_to_in_progress():
    state = {"objective_status": "completed", "awaiting_field": None, "next_best_action": "close_conversation", "known_fields": {"a": "b"}}
    reopened = service._reopen_conversation_state(state)
    assert reopened["objective_status"] == "in_progress"
    assert reopened["awaiting_field"] is None
    assert reopened["next_best_action"] == "ask_question"
    assert reopened["known_fields"] == {"a": "b"}  # untouched


def test_reopen_conversation_state_never_resets_do_not_call_or_wrong_number():
    state = {"objective_status": "do_not_call", "do_not_call": True, "wrong_number": False}
    reopened = service._reopen_conversation_state(state)
    assert reopened["do_not_call"] is True
    assert reopened["wrong_number"] is False


def test_reopen_conversation_state_does_not_mutate_the_input():
    state = {"objective_status": "completed"}
    service._reopen_conversation_state(state)
    assert state["objective_status"] == "completed"  # original dict untouched


@dataclass
class _FakeResult:
    planner_reason: str
    planner_action: str = "COMPLETE_OBJECTIVE"


def test_end_reason_for_maps_known_planner_reasons():
    assert service._end_reason_for(_FakeResult(planner_reason="do_not_call_requested")) == "do_not_call"
    assert service._end_reason_for(_FakeResult(planner_reason="wrong_number")) == "wrong_number"
    assert service._end_reason_for(_FakeResult(planner_reason="all_fields_collected")) == "completed"
    assert service._end_reason_for(_FakeResult(planner_reason="max_turns_reached")) == "completed"
    assert service._end_reason_for(_FakeResult(planner_reason="max_duration_reached")) == "completed"


def test_end_reason_for_human_handoff_falls_back_to_transferred():
    result = _FakeResult(planner_reason="customer_requested_human", planner_action="HUMAN_HANDOFF")
    assert service._end_reason_for(result) == "transferred"


def test_end_reason_for_unknown_reason_defaults_to_completed():
    result = _FakeResult(planner_reason="some_future_reason", planner_action="COMPLETE_OBJECTIVE")
    assert service._end_reason_for(result) == "completed"


def test_resolve_tts_speaker_uses_voice_id_when_provider_is_sarvam_tts():
    voice = VoicePersona(provider=ProviderName.SARVAM_TTS, voice_id="shubh")
    assert service._resolve_tts_speaker(voice) == "shubh"


def test_resolve_tts_speaker_ignores_mock_provider():
    # The actual bug this fixes: every seeded/demo VoicePersona today is
    # provider="mock", voice_id="mock-warm-female-te" — a placeholder that
    # is not a real Sarvam speaker name and would break a live TTS call if
    # sent as one. Must fall back to None (SarvamTTS's own "priya" default).
    voice = VoicePersona(provider=ProviderName.MOCK, voice_id="mock-warm-female-te")
    assert service._resolve_tts_speaker(voice) is None


def test_resolve_tts_speaker_handles_no_persona_configured():
    assert service._resolve_tts_speaker(None) is None


def test_resolve_tts_speaker_ignores_sarvam_tts_with_empty_voice_id():
    voice = VoicePersona(provider=ProviderName.SARVAM_TTS, voice_id="")
    assert service._resolve_tts_speaker(voice) is None


def test_resolve_tts_speaker_differs_between_two_agents_with_different_personas():
    # Stage 2 Fix 3: the resolution logic itself must be genuinely
    # per-agent, not accidentally hardcoded/memoized to one value.
    voice_a = VoicePersona(provider=ProviderName.SARVAM_TTS, voice_id="shubh")
    voice_b = VoicePersona(provider=ProviderName.SARVAM_TTS, voice_id="anushka")
    assert service._resolve_tts_speaker(voice_a) == "shubh"
    assert service._resolve_tts_speaker(voice_b) == "anushka"
    assert service._resolve_tts_speaker(voice_a) != service._resolve_tts_speaker(voice_b)


def test_resolve_tts_pace_differs_between_two_agents_with_different_personas():
    voice_a = VoicePersona(provider=ProviderName.SARVAM_TTS, voice_id="shubh", speaking_speed=0.8)
    voice_b = VoicePersona(provider=ProviderName.SARVAM_TTS, voice_id="anushka", speaking_speed=1.6)
    assert service._resolve_tts_pace(voice_a) == 0.8
    assert service._resolve_tts_pace(voice_b) == 1.6


class _FakeRedis:
    async def set(self, *args, **kwargs):
        pass


class _CapturingSarvamTTS:
    """Stands in for app.live_providers.sarvam_tts.SarvamTTS — captures the
    constructor kwargs _speak() actually passed, which is the thing under
    test (not real synthesis)."""

    captured_kwargs: dict = {}

    def __init__(self, **kwargs):
        _CapturingSarvamTTS.captured_kwargs = kwargs

    async def synthesize(self, *, text, language_code):
        return b"fake-wav-bytes"


async def test_speak_passes_the_resolved_speaker_through_to_sarvam_tts(monkeypatch):
    monkeypatch.setattr(service, "SarvamTTS", _CapturingSarvamTTS)
    settings = Settings(sarvam_tts_api_key="fake-key")

    kind, _content = await service._speak("hello", language_code="te-IN", settings=settings, redis=_FakeRedis(), speaker="shubh")
    assert kind == "play"
    assert _CapturingSarvamTTS.captured_kwargs.get("speaker") == "shubh"


async def test_speak_omits_speaker_kwarg_entirely_when_none(monkeypatch):
    # None must mean "let SarvamTTS use its own default" — not "speaker=None".
    monkeypatch.setattr(service, "SarvamTTS", _CapturingSarvamTTS)
    settings = Settings(sarvam_tts_api_key="fake-key")

    await service._speak("hello", language_code="te-IN", settings=settings, redis=_FakeRedis(), speaker=None)
    assert "speaker" not in _CapturingSarvamTTS.captured_kwargs


async def test_speak_passes_the_resolved_pace_through_to_sarvam_tts(monkeypatch):
    # Stage 2 Fix 3: _resolve_tts_pace()'s result used to be computed and
    # cached in Redis state but never actually reached SarvamTTS — a
    # configured VoicePersona.speaking_speed had zero effect on this
    # transport. See docs/STAGE2_REAL_CALL_FIXES.md.
    monkeypatch.setattr(service, "SarvamTTS", _CapturingSarvamTTS)
    settings = Settings(sarvam_tts_api_key="fake-key")

    await service._speak("hello", language_code="te-IN", settings=settings, redis=_FakeRedis(), speaker="shubh", pace=1.4)
    assert _CapturingSarvamTTS.captured_kwargs.get("pace") == 1.4


async def test_speak_defaults_pace_to_natural_speed_when_omitted(monkeypatch):
    monkeypatch.setattr(service, "SarvamTTS", _CapturingSarvamTTS)
    settings = Settings(sarvam_tts_api_key="fake-key")

    await service._speak("hello", language_code="te-IN", settings=settings, redis=_FakeRedis())
    assert _CapturingSarvamTTS.captured_kwargs.get("pace") == 1.0


def test_sarvam_tts_stores_pace_for_the_outgoing_request():
    from app.live_providers.sarvam_tts import SarvamTTS

    tts = SarvamTTS(api_key="fake-key", pace=1.7)
    assert tts._pace == 1.7


def test_sarvam_tts_defaults_pace_to_one_when_omitted():
    from app.live_providers.sarvam_tts import SarvamTTS

    tts = SarvamTTS(api_key="fake-key")
    assert tts._pace == 1.0


# --- _tool_failure_reply — Stage 2 Fix 1: never let a canned success line
# escape a real tool failure. See docs/STAGE2_REAL_CALL_FIXES.md.


def test_tool_failure_reply_is_language_specific_and_never_claims_success():
    for lang in ("te-IN", "hi-IN", "en-IN"):
        text = service._tool_failure_reply(lang)
        assert text  # non-empty
        lowered = text.lower()
        for claim in ("booked", "confirmed", "scheduled", "noted"):
            assert claim not in lowered

    texts = {service._tool_failure_reply(lang) for lang in ("te-IN", "hi-IN", "en-IN")}
    assert len(texts) == 3  # genuinely distinct per language, not one string reused


def test_tool_failure_reply_falls_back_to_english_for_an_unknown_language_code():
    assert service._tool_failure_reply("fr-FR") == service._tool_failure_reply("en-IN")
