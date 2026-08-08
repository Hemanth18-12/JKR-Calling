from app.knowledge_retrieval import first_sentence, looks_like_a_question


def test_looks_like_a_question_detects_question_mark():
    assert looks_like_a_question("root canal ఎంత అవుతుంది?") is True


def test_looks_like_a_question_detects_price_keywords_without_question_mark():
    assert looks_like_a_question("cost enta untundi") is True
    assert looks_like_a_question("ధర ఎంత") is True


def test_looks_like_a_question_false_for_plain_statement():
    assert looks_like_a_question("రేపు ఉదయం పది గంటలకు వీలుగా ఉంటుంది") is False


def test_first_sentence_returns_only_the_first_sentence():
    text = "Root canal costs 8000 to 12000 rupees. We are open Monday to Saturday."
    assert first_sentence(text) == "Root canal costs 8000 to 12000 rupees."


def test_first_sentence_truncates_a_single_long_sentence():
    text = "A" * 300
    result = first_sentence(text, max_chars=180)
    assert len(result) == 180
