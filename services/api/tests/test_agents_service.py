from app.modules.agents.persona_templates import TEMPLATES
from app.modules.agents.service import _has_ai_disclosure


def test_has_ai_disclosure_true_for_spec_example():
    assert _has_ai_disclosure("నేను ఆహా డెంటల్ కేర్ తరఫున మాట్లాడుతున్న AI సహాయకురాలిని.") is True


def test_has_ai_disclosure_false_when_absent():
    assert _has_ai_disclosure("నమస్కారం, నేను రవి గారు తో మాట్లాడుతున్నాను.") is False


def test_has_ai_disclosure_false_for_empty_string():
    assert _has_ai_disclosure("") is False


def test_every_persona_template_greeting_keeps_name_placeholder_literal():
    """Regression test for the "గారు గారు" bug: {business} must fill in at
    creation time but {name} must survive as a literal token for voice-worker
    to substitute per-call — see agents/service.py::create_agent's `fill`."""
    for key, template in TEMPLATES.items():
        filled = template["greeting_text"].replace("{business}", "Test Business")
        assert "{name}" in filled, f"{key} lost its {{name}} placeholder after filling {{business}}"
        assert "{business}" not in filled, f"{key} did not fill {{business}}"
        assert "గారు గారు" not in filled, f"{key} produces a doubled honorific"


def test_every_persona_template_has_ai_disclosure():
    for key, template in TEMPLATES.items():
        assert _has_ai_disclosure(template["ai_disclosure_text"]), f"{key} template fails disclosure check"


def test_safety_blocks_abusive_telugu_and_english_content():
    import pytest
    from fastapi import HTTPException
    from app.modules.agents.safety import detect_abusive_content, validate_and_sanitize_persona_field

    # Clean text passes
    clean_telugu = "నమస్కారం {name} గారు, నేను Aaha Dental Care తరఫున మాట్లాడుతున్న AI assistant ని."
    assert detect_abusive_content(clean_telugu) is None
    sanitized = validate_and_sanitize_persona_field(clean_telugu, "Greeting")
    assert sanitized == clean_telugu

    # Abusive Telugu (script)
    bad_telugu = "నేను AI assistant ని. లంజకొడుకు"
    assert detect_abusive_content(bad_telugu) is not None
    with pytest.raises(HTTPException) as exc:
        validate_and_sanitize_persona_field(bad_telugu, "Greeting")
    assert exc.value.status_code == 422

    # Abusive Telugu (transliteration)
    bad_translit = "Hello, I am AI assistant. lanjakodaka how are you"
    assert detect_abusive_content(bad_translit) is not None
    with pytest.raises(HTTPException):
        validate_and_sanitize_persona_field(bad_translit, "Greeting")

    # Abusive English
    bad_english = "Hello, I am AI assistant. What the fuck do you want?"
    assert detect_abusive_content(bad_english) is not None
    with pytest.raises(HTTPException):
        validate_and_sanitize_persona_field(bad_english, "Greeting")


def test_multilingual_persona_templates_and_retail_clothing():
    from app.modules.agents.persona_templates import get_template_content

    # 1. Retail clothing (Crazy Cloths) in en-IN
    clothing_en = get_template_content("sales_qualifier", language="en-IN", business_name="Crazy Cloths")
    assert "Crazy Cloths" in clothing_en["greeting_text"]
    assert "Crazy Cloths" in clothing_en["ai_disclosure_text"]
    assert "clothing" in clothing_en["greeting_text"].lower() or "collection" in clothing_en["greeting_text"].lower()
    assert "appointment" not in clothing_en["greeting_text"].lower()

    # 2. Retail clothing in Telugu (te-IN)
    clothing_te = get_template_content("sales_qualifier", language="te-IN", business_name="Crazy Cloths")
    assert "Crazy Cloths" in clothing_te["greeting_text"]
    assert "AI అసిస్టెంట్" in clothing_te["ai_disclosure_text"] or "AI assistant" in clothing_te["ai_disclosure_text"]
    assert "బట్టల కలెక్షన్స్" in clothing_te["greeting_text"] or "Crazy Cloths" in clothing_te["greeting_text"]
    assert "అపాయింట్‌మెంట్" not in clothing_te["greeting_text"]

    # 3. Retail clothing in Hindi (hi-IN)
    clothing_hi = get_template_content("sales_qualifier", language="hi-IN", business_name="Crazy Cloths")
    assert "Crazy Cloths" in clothing_hi["greeting_text"]
    assert "कपड़ों" in clothing_hi["greeting_text"] or "कलेक्शन" in clothing_hi["greeting_text"]

    # 4. Standard appointment coordinator in Telugu (te-IN)
    appt_te = get_template_content("appointment_coordinator", language="te-IN", business_name="Dr. Rao Clinic")
    assert "Dr. Rao Clinic" in appt_te["greeting_text"]
    assert "అపాయింట్‌మెంట్" in appt_te["greeting_text"]


def test_live_call_hallucination_and_vad_filtering():
    import io
    import wave
    from app.modules.live_call.service import is_hallucinatory_transcript, analyze_audio_vad, ensure_16k_wav

    # 1. Hallucination filter tests
    assert is_hallucinatory_transcript("you") is True
    assert is_hallucinatory_transcript("you.") is True
    assert is_hallucinatory_transcript("thank you") is True
    assert is_hallucinatory_transcript("I") is True
    assert is_hallucinatory_transcript(".") is True
    assert is_hallucinatory_transcript("...") is True
    assert is_hallucinatory_transcript("") is True

    # Real customer replies must NOT be filtered
    assert is_hallucinatory_transcript("Yes, I want to see shirts") is False
    assert is_hallucinatory_transcript("What is the price?") is False
    assert is_hallucinatory_transcript("రేపు ఉదయం మాట్లాడతాను") is False
    assert is_hallucinatory_transcript("हाँ, मुझे जानकारी चाहिए") is False

    # 2. VAD on silent audio (8000 16-bit zero samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 8000)
    silent_bytes = buf.getvalue()

    has_speech, rms = analyze_audio_vad(silent_bytes)
    assert has_speech is False
    assert rms < 10.0

    # 3. 16kHz upsampler
    upsampled = ensure_16k_wav(silent_bytes)
    with wave.open(io.BytesIO(upsampled), "rb") as wf:
        assert wf.getframerate() == 16000

