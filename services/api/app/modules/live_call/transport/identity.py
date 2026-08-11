"""P9 — the canonical identity every customer-facing output artifact must
carry from the moment it's produced to the moment it crosses the Twilio
WebSocket. See docs/RESPONSE_IDENTITY_MODEL.md for the full reasoning.

Deliberately a standalone module with zero dependencies on the rest of
transport/ (only stdlib) — every layer that needs to attach or check an
identity (coordinator.py, tts_bridge.py, base.py, twilio_media_stream.py)
imports from here, never from each other, so there is exactly one
definition of what "ownership" means, never five loose strings threaded
separately through the stack (this phase's own explicit instruction).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class ResponseIdentity:
    """Immutable by construction (frozen dataclass) — a new response always
    means a new ResponseIdentity, never a mutated one. See
    docs/RESPONSE_IDENTITY_MODEL.md for what each field means and why
    `sequence_id` is currently always equal to `response_id` in this
    implementation (same reasoning RealtimePipelineCoordinator's own
    ActiveResponseContext.sequence_id already documented in P7 — kept as a
    distinct field so a future phase that needs true sub-sequence
    granularity doesn't need to add one).

    `epoch` is the call-scoped monotonically increasing response_epoch
    captured at the moment this identity was minted (RealtimePipelineCoordinator
    .begin_response()) — a cheap integer comparison that answers "is this
    identity from a strictly older response than the one currently active"
    without needing a dict lookup, useful for the hot send-path gate."""

    call_id: uuid.UUID
    turn_id: str
    response_id: str
    generation_id: str
    sequence_id: str
    epoch: int


@dataclass(frozen=True)
class OutputGateDecision:
    """What the final send-boundary check decided, and why — logged/counted
    by the caller (twilio_media_stream.py's _send_loop), never silently
    swallowed. `reason` is a short machine-readable tag (see
    docs/REALTIME_OUTPUT_INVARIANTS.md for the full vocabulary), never a
    sentence, so it's cheap to use as a metric label."""

    allowed: bool
    reason: str


class ChunkCheckResult(StrEnum):
    """The outcome of checking one indexed, fingerprinted artifact (a
    SpeakableChunk's text, a TTSAudioChunk's bytes) against what's already
    been seen for its response — see check_chunk_index()."""

    ACCEPT = "accept"
    DUPLICATE = "duplicate"  # same index, same fingerprint — benign, drop silently
    CONFLICT = "conflict"  # same index, different fingerprint — upstream corruption
    GAP = "gap"  # index ahead of what's expected — out of order, upstream corruption


def check_chunk_index(
    *, index: int, fingerprint: int, next_expected: int, fingerprints_by_index: dict[int, int],
) -> ChunkCheckResult:
    """Shared by both the SpeakableChunk boundary (coordinator.py's
    submit_speakable_chunk) and the TTSAudioChunk boundary (tts_bridge.py's
    _run_consumer) — same shape, same policy, written once. `fingerprint` is
    a cheap, non-cryptographic content fingerprint (hash(text) for text,
    (len(data), zlib.crc32(data)) packed into an int for audio — see each
    call site) used only to distinguish a genuine duplicate from a
    same-index conflict, never as a security boundary.

    Policy (documented, per this phase's own requirement to pick one and
    write it down rather than leave the behavior implicit): indices strictly
    below `next_expected` are checked for duplicate-vs-conflict; an index
    at `next_expected` is accepted and advances it by one; an index AHEAD of
    `next_expected` is a GAP. This implementation's single-producer-per-
    generation design (both SpeakableChunk.chunk_index and
    TTSAudioChunk.audio_chunk_index are self-assigned, strictly sequential
    counters — see docs/P9_REPLAY_PROTECTION_AUDIT.md) means a genuine GAP
    is structurally anomalous, not a normal race — callers treat GAP the
    same as CONFLICT (fail the response) rather than building a reorder
    buffer for a scenario that can't occur in normal operation."""
    if index < next_expected:
        prior = fingerprints_by_index.get(index)
        if prior is not None and prior == fingerprint:
            return ChunkCheckResult.DUPLICATE
        return ChunkCheckResult.CONFLICT  # prior is None here would itself already be a bug (see docstring) — fail closed either way
    if index > next_expected:
        return ChunkCheckResult.GAP
    return ChunkCheckResult.ACCEPT
