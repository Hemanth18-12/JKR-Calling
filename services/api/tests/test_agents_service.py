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
