from app.spoken_formatter import SpokenResponseFormatter, build_clarification


def test_strips_markdown_and_urls():
    formatter = SpokenResponseFormatter(max_sentences=5)
    result = formatter.format("Check **this** out at https://example.com for `details`.")
    assert "**" not in result.text
    assert "https://" not in result.text
    assert "`" not in result.text


def test_normalizes_rupee_amounts():
    formatter = SpokenResponseFormatter(max_sentences=5)
    result = formatter.format("The cost is ₹28,000 for the full treatment.")
    assert "28000 rupees" in result.text
    assert "₹" not in result.text


def test_truncates_to_max_sentences():
    formatter = SpokenResponseFormatter(max_sentences=2)
    result = formatter.format("First sentence. Second sentence. Third sentence. Fourth sentence.")
    assert result.truncated is True
    assert result.original_sentence_count == 4
    assert result.text.count(".") <= 2


def test_does_not_truncate_when_within_limit():
    formatter = SpokenResponseFormatter(max_sentences=3)
    result = formatter.format("Only one sentence here.")
    assert result.truncated is False


def test_acknowledgement_never_repeats_consecutively():
    formatter = SpokenResponseFormatter(language="te-en-IN", max_sentences=3)
    seen = []
    for _ in range(10):
        result = formatter.format("Some follow-up question.", prepend_acknowledgement=True)
        assert result.acknowledgement_used is not None
        if seen:
            assert result.acknowledgement_used != seen[-1]
        seen.append(result.acknowledgement_used)


def test_expands_known_abbreviations():
    formatter = SpokenResponseFormatter(max_sentences=5)
    result = formatter.format("Please see Dr. Rao for your appt.")
    assert "Dr." not in result.text
    assert "Doctor" in result.text


def test_build_clarification_never_states_a_bare_value():
    text = build_clarification("amount", ["twenty eight thousand", "eighteen thousand"], language="te-en-IN")
    assert "twenty eight thousand" in text
    assert "eighteen thousand" in text
    assert "?" in text


def test_build_clarification_english():
    text = build_clarification("date", ["Monday", "Tuesday"], language="en-IN")
    assert text.startswith("Sorry")
    assert "Monday" in text and "Tuesday" in text
