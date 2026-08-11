from jkr_conversation.speakable_chunker import DEFAULT_MAX_CHUNK_CHARS, SpeakableChunker


def test_no_chunk_until_boundary_character_arrives():
    chunker = SpeakableChunker()
    assert chunker.feed("Hostel facility") == []
    assert chunker.feed(" is available") == []
    chunks = chunker.feed(" here.")
    assert chunks == ["Hostel facility is available here."]


def test_does_not_emit_early_merely_because_stream_paused():
    """spec §16 — punctuation arriving late must not cause an early emit;
    the chunker has no timer/pause logic at all, so this is really just
    confirming feed() never emits without a boundary character, no matter
    how many separate deltas accumulate first."""
    chunker = SpeakableChunker()
    for word in ["The", " root", " canal", " treatment", " takes", " about", " an", " hour"]:
        assert chunker.feed(word) == []
    chunks = chunker.feed(".")
    assert chunks == ["The root canal treatment takes about an hour."]


def test_multiple_boundaries_in_one_delta_all_surfaced():
    chunker = SpeakableChunker()
    chunks = chunker.feed("Sentence one. Sentence two. Sentence three.")
    assert chunks == ["Sentence one.", "Sentence two.", "Sentence three."]


def test_below_min_chunk_chars_keeps_accumulating():
    chunker = SpeakableChunker(min_chunk_chars=10)
    assert chunker.feed("Ok.") == []  # 3 chars, below the 10-char floor
    chunks = chunker.feed(" Let's continue from here.")
    assert chunks == ["Ok. Let's continue from here."]


def test_flush_returns_leftover_regardless_of_min_chunk_chars():
    """spec §17 — a short complete answer like 'Yes.' must still be spoken,
    not silently dropped for being under the threshold."""
    chunker = SpeakableChunker(min_chunk_chars=10)
    assert chunker.feed("Yes") == []
    assert chunker.flush() == "Yes"


def test_flush_after_full_sentences_returns_none():
    chunker = SpeakableChunker()
    chunker.feed("Complete sentence.")
    assert chunker.flush() is None


def test_devanagari_danda_is_a_boundary():
    chunker = SpeakableChunker()
    chunks = chunker.feed("ठीक है।")
    assert chunks == ["ठीक है।"]


def test_telugu_english_codemixed_chunking_matches_spec_example():
    """Manually traced against the P5 spec's own worked example (§59):
    'Hostel facility ఉంది అండి.' then 'Campus visit ఎప్పుడు plan
    చేస్తున్నారు?' as two separate speakable chunks."""
    chunker = SpeakableChunker()
    deltas = [
        "Hostel", " facility", " ఉంది", " అండి.", " Campus", " visit", " ఎప్పుడు", " plan", " చేస్తున్నారు?",
    ]
    chunks: list[str] = []
    for delta in deltas:
        chunks.extend(chunker.feed(delta))
    assert chunks == ["Hostel facility ఉంది అండి.", "Campus visit ఎప్పుడు plan చేస్తున్నారు?"]


def test_force_cuts_at_clause_boundary_when_max_length_exceeded_without_sentence_end():
    chunker = SpeakableChunker(max_chunk_chars=40)
    long_run_on = "This is a very long clause, followed by more words that keep going without stopping at all here"
    chunks = chunker.feed(long_run_on)
    assert chunks  # at least one forced cut happened
    first = chunks[0]
    assert len(first) <= 40
    assert first.endswith(",")  # cut backward to the nearest clause boundary, not mid-word


def test_force_cuts_hard_when_no_boundary_exists_at_all():
    chunker = SpeakableChunker(max_chunk_chars=20)
    no_boundary = "a" * 50
    chunks = chunker.feed(no_boundary)
    assert chunks
    assert len(chunks[0]) == 20  # no clause/sentence char anywhere — hard cut at the max


def test_default_max_chunk_chars_is_reasonable_for_spoken_pacing():
    # spec §19: roughly the upper end of a 1.5-5 spoken-second chunk.
    assert 100 <= DEFAULT_MAX_CHUNK_CHARS <= 300
