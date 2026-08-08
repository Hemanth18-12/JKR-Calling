import math

from jkr_db.embeddings import EMBEDDING_DIM, mock_embed


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def test_embedding_has_expected_dimension():
    assert len(mock_embed("hello world")) == EMBEDDING_DIM


def test_embedding_is_deterministic():
    assert mock_embed("root canal appointment") == mock_embed("root canal appointment")


def test_shared_vocabulary_is_more_similar_than_unrelated_text():
    a = mock_embed("What is the cost of a root canal treatment?")
    b = mock_embed("How much does root canal treatment cost?")
    c = mock_embed("What time does the college admission office open?")

    sim_related = _cosine(a, b)
    sim_unrelated = _cosine(a, c)
    assert sim_related > sim_unrelated


def test_empty_string_does_not_crash_and_is_normalized():
    vec = mock_embed("")
    assert len(vec) == EMBEDDING_DIM
    assert abs(sum(v * v for v in vec) - 1.0) < 1e-9
