from jkr_conversation.language import get_language_profile, lang_prefix


def test_five_profiles_resolve_with_correct_code_mixing_flags():
    te = get_language_profile("te-IN")
    assert te.base_language == "te" and te.code_mixed is False and te.strict_language is True

    hi = get_language_profile("hi-IN")
    assert hi.base_language == "hi" and hi.code_mixed is False and hi.strict_language is True

    en = get_language_profile("en-IN")
    assert en.base_language == "en" and en.code_mixed is False and en.strict_language is True

    te_en = get_language_profile("te-en-IN")
    assert te_en.base_language == "te" and te_en.code_mixed is True and te_en.strict_language is False

    hi_en = get_language_profile("hi-en-IN")
    assert hi_en.base_language == "hi" and hi_en.code_mixed is True and hi_en.strict_language is False


def test_pure_and_mixed_profiles_are_distinguishable():
    # The bug this whole module fixes: lang_prefix("te-IN") == lang_prefix("te-en-IN") == "te",
    # which is correct for script/pronunciation but loses the code-mixing distinction entirely.
    assert lang_prefix("te-IN") == lang_prefix("te-en-IN") == "te"
    assert get_language_profile("te-IN").code_mixed != get_language_profile("te-en-IN").code_mixed


def test_unrecognized_code_falls_back_to_the_code_mixed_variant_for_its_prefix():
    # Matches this system's historical default behavior (always code-mixed)
    # rather than surprising an unexpected input into sudden strict mode.
    profile = get_language_profile("te-XX")
    assert profile.code == "te-en-IN"


def test_completely_unrecognized_code_falls_back_to_english():
    assert get_language_profile("garbage").code == "en-IN"


def test_lang_prefix_unchanged():
    assert lang_prefix("te-en-IN") == "te"
    assert lang_prefix("hi-IN") == "hi"
    assert lang_prefix("something-else") == "en"
