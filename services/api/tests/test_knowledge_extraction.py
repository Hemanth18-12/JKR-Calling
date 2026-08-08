from app.modules.knowledge.extraction import chunk_text


def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  \n") == []


def test_chunk_text_short_text_is_a_single_chunk():
    chunks = chunk_text("One short paragraph.", max_chars=800)
    assert len(chunks) == 1
    assert chunks[0] == "One short paragraph."


def test_chunk_text_splits_when_exceeding_max_chars():
    paragraphs = [f"Paragraph number {i} with some filler content to add length." for i in range(30)]
    text = "\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=300, overlap_chars=20)
    assert len(chunks) > 1
    for chunk in chunks:
        # Overlap can push a chunk slightly over; it should never be wildly over.
        assert len(chunk) <= 300 + 100


def test_chunk_text_hard_splits_a_single_paragraph_longer_than_max_chars():
    long_paragraph = "word " * 500  # ~2500 chars, no newlines at all
    chunks = chunk_text(long_paragraph, max_chars=400, overlap_chars=0)
    assert len(chunks) >= 6
    assert "".join(chunks).replace(" ", "") == long_paragraph.replace(" ", "")[: len("".join(chunks).replace(" ", ""))]


def test_chunk_text_preserves_all_content_across_chunks():
    text = "First fact about pricing.\nSecond fact about hours.\nThird fact about location."
    chunks = chunk_text(text, max_chars=40, overlap_chars=5)
    combined = " ".join(chunks)
    assert "pricing" in combined
    assert "hours" in combined
    assert "location" in combined
