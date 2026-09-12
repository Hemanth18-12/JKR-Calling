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
