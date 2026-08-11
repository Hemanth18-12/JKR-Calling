from jkr_conversation.domain_normalizer import normalize
from jkr_conversation.schemas import DomainTermSnapshot

_DENTAL_TERMS = [
    DomainTermSnapshot(
        canonical="root canal treatment", category="procedure", criticality="critical",
        languages=["te", "en"], aliases=["ఫ్రూట్ కెనాల్స్", "fruit canals", "RCT"],
    ),
    DomainTermSnapshot(canonical="filling", category="procedure", criticality="standard", languages=["te", "en"]),
]


def test_seeded_alias_matches_the_mistranscribed_telugu_term():
    # The exact bug from real call 1482f303-3dc9-4fa2-b32c-83f43f24d7c0.
    candidates = normalize("నాకు ఫ్రూట్ కెనాల్స్ కావాలి", vocabulary_terms=_DENTAL_TERMS)
    assert candidates
    assert candidates[0].canonical == "root canal treatment"
    assert candidates[0].ratio == 1.0
    assert candidates[0].criticality == "critical"


def test_seeded_alias_abbreviation_matches_exactly():
    candidates = normalize("I need RCT done", vocabulary_terms=_DENTAL_TERMS)
    assert candidates
    assert candidates[0].canonical == "root canal treatment"
    assert candidates[0].ratio == 1.0


def test_unseeded_same_script_variant_still_fuzzy_matches():
    # Not a pre-seeded alias — genuine fuzzy matching against the canonical
    # term itself must still catch a same-script spelling/wording variant.
    candidates = normalize("I want a route canal treatment", vocabulary_terms=_DENTAL_TERMS)
    assert candidates
    assert candidates[0].canonical == "root canal treatment"
    assert candidates[0].ratio >= 0.72


def test_unrelated_value_returns_no_candidates():
    candidates = normalize("I want a filling", vocabulary_terms=_DENTAL_TERMS)
    # "filling" is itself a seeded canonical term — it should match itself,
    # not root canal treatment.
    assert candidates
    assert candidates[0].canonical == "filling"
    assert candidates[0].matched_alias == "filling"


def test_completely_unrelated_value_returns_empty():
    candidates = normalize("what time do you close today", vocabulary_terms=_DENTAL_TERMS)
    assert candidates == []


def test_cross_script_corruption_without_a_seeded_alias_is_not_bridged():
    # Documents the honest, known limitation: difflib.SequenceMatcher cannot
    # connect Telugu-script "ఫ్రూట్ కెనాల్స్" to Latin-script "root canal
    # treatment" on character similarity alone — this is exactly why the
    # real fix combines pinned STT language + a curated literal alias
    # (test_seeded_alias_matches_the_mistranscribed_telugu_term above),
    # not smarter fuzzy matching.
    term_without_the_alias = [
        DomainTermSnapshot(canonical="root canal treatment", category="procedure", criticality="critical", languages=["te", "en"]),
    ]
    candidates = normalize("నాకు ఫ్రూట్ కెనాల్స్ కావాలి", vocabulary_terms=term_without_the_alias)
    assert candidates == []


def test_empty_vocabulary_returns_empty():
    assert normalize("root canal treatment", vocabulary_terms=[]) == []


def test_empty_raw_text_returns_empty():
    assert normalize("   ", vocabulary_terms=_DENTAL_TERMS) == []
