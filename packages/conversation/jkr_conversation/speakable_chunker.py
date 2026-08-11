"""P5 — SpeakableChunker (spec §13-19). Converts a stream of raw text
deltas into natural, speakable chunks: not one token at a time, not the
whole response at once.

Deliberately content-driven, not timing-driven: a chunk is only ever
extracted when an actual sentence/clause boundary CHARACTER has arrived in
the buffer — never because the token stream merely paused for a moment.
This is what satisfies spec §16 ("punctuation may arrive late... do not
emit early merely because the stream paused") by construction, without
needing any timer/debounce logic at all.

Language-agnostic boundary set: `.?!;` (English/most scripts) plus `।`
(Devanagari danda, used in formal Hindi — modern spoken-register Hindi an
LLM generates often uses plain `.` too, so both are honored). Telugu has
no distinct sentence-final mark beyond the shared set. This is intentionally
NOT full sentence-segmentation NLP — a small, fast, correct-enough boundary
set, matching spec §15's own list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SENTENCE_BOUNDARY_CHARS = frozenset({".", "?", "!", ";", "।"})
_CLAUSE_BOUNDARY_CHARS = frozenset({",", ":"})

DEFAULT_MIN_CHUNK_CHARS = 4  # low enough to allow "Yes." / "అవునండి." through directly, not just via flush()
DEFAULT_MAX_CHUNK_CHARS = 220  # roughly the upper end of spec §19's "1.5-5 spoken seconds" target


@dataclass
class SpeakableChunker:
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS
    _buffer: str = field(default="", repr=False)

    def feed(self, delta: str) -> list[str]:
        """Appends a text delta and returns zero or more newly-completed
        chunks (usually zero or one; could be more than one if a single
        delta happens to contain multiple boundary characters)."""
        self._buffer += delta
        chunks: list[str] = []
        while True:
            chunk = self._try_extract_chunk()
            if chunk is None:
                break
            chunks.append(chunk)
        return chunks

    def flush(self) -> str | None:
        """Call once the underlying stream has completed — whatever's left
        in the buffer is the final chunk, regardless of min_chunk_chars
        (spec §17: a short complete answer like "Yes." must still be
        emitted, not silently dropped for being under the threshold)."""
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining if remaining else None

    def _try_extract_chunk(self) -> str | None:
        for i, ch in enumerate(self._buffer):
            if ch in _SENTENCE_BOUNDARY_CHARS:
                candidate = self._buffer[: i + 1].strip()
                if len(candidate) >= self.min_chunk_chars:
                    self._buffer = self._buffer[i + 1 :].lstrip()
                    return candidate
                # Below the minimum — keep accumulating rather than
                # returning a tiny fragment; this boundary character stays
                # in the buffer and will be included in whatever chunk
                # eventually does clear the threshold (or in flush()).
        if len(self._buffer) >= self.max_chunk_chars:
            return self._force_cut_at_max()
        return None

    def _force_cut_at_max(self) -> str | None:
        """Max length reached with no qualifying sentence boundary yet —
        find the nearest safe clause boundary working backward (spec §18),
        falling back to a hard cut only if none exists at all."""
        window = self._buffer[: self.max_chunk_chars]
        cut = None
        for i in range(len(window) - 1, -1, -1):
            if window[i] in _SENTENCE_BOUNDARY_CHARS or window[i] in _CLAUSE_BOUNDARY_CHARS:
                cut = i + 1
                break
        if cut is None:
            cut = self.max_chunk_chars
        candidate = self._buffer[:cut].strip()
        self._buffer = self._buffer[cut:].lstrip()
        return candidate if candidate else None
