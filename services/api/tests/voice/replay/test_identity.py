"""P9 — ResponseIdentity, OutputGateDecision, and check_chunk_index(): the
pure, dependency-free primitives every replay-protection boundary is built
on. See docs/RESPONSE_IDENTITY_MODEL.md.
"""

from __future__ import annotations

import uuid

from app.modules.live_call.transport.identity import (
    ChunkCheckResult,
    OutputGateDecision,
    ResponseIdentity,
    check_chunk_index,
)


def _identity(**overrides: object) -> ResponseIdentity:
    base: dict[str, object] = dict(
        call_id=uuid.uuid4(), turn_id="turn_1", response_id="resp_a", generation_id="gen_a", sequence_id="resp_a", epoch=1,
    )
    base.update(overrides)
    return ResponseIdentity(**base)  # type: ignore[arg-type]


def test_response_identity_is_frozen():
    identity = _identity()
    try:
        identity.response_id = "resp_b"  # type: ignore[misc]
        raised = False
    except Exception:  # noqa: BLE001 — FrozenInstanceError, just proving immutability
        raised = True
    assert raised, "ResponseIdentity must be immutable — a new response requires a new identity, never a mutation"


def test_response_identity_equality_is_by_value():
    call_id = uuid.uuid4()
    a = _identity(call_id=call_id)
    b = _identity(call_id=call_id)
    assert a == b


def test_output_gate_decision_shape():
    allowed = OutputGateDecision(True, "ok")
    blocked = OutputGateDecision(False, "stale_response")
    assert allowed.allowed and allowed.reason == "ok"
    assert not blocked.allowed and blocked.reason == "stale_response"


# --- check_chunk_index() ----------------------------------------------------


def test_first_chunk_at_expected_index_is_accepted():
    result = check_chunk_index(index=0, fingerprint=111, next_expected=0, fingerprints_by_index={})
    assert result is ChunkCheckResult.ACCEPT


def test_sequential_chunks_are_accepted():
    fingerprints: dict[int, int] = {}
    for i in range(5):
        result = check_chunk_index(index=i, fingerprint=1000 + i, next_expected=i, fingerprints_by_index=fingerprints)
        assert result is ChunkCheckResult.ACCEPT
        fingerprints[i] = 1000 + i


def test_repeated_index_with_same_fingerprint_is_duplicate():
    fingerprints = {0: 111}
    result = check_chunk_index(index=0, fingerprint=111, next_expected=1, fingerprints_by_index=fingerprints)
    assert result is ChunkCheckResult.DUPLICATE


def test_repeated_index_with_different_fingerprint_is_conflict():
    fingerprints = {0: 111}
    result = check_chunk_index(index=0, fingerprint=999, next_expected=1, fingerprints_by_index=fingerprints)
    assert result is ChunkCheckResult.CONFLICT


def test_index_below_expected_but_never_recorded_is_conflict_not_crash():
    # Defensive/fail-closed case: an index below `next_expected` that was
    # somehow never recorded in fingerprints_by_index (should not happen in
    # normal operation, see the module's own docstring) — never silently
    # treated as a duplicate.
    result = check_chunk_index(index=0, fingerprint=111, next_expected=2, fingerprints_by_index={})
    assert result is ChunkCheckResult.CONFLICT


def test_index_ahead_of_expected_is_gap():
    result = check_chunk_index(index=5, fingerprint=111, next_expected=2, fingerprints_by_index={})
    assert result is ChunkCheckResult.GAP


def test_index_far_ahead_is_still_just_gap_not_something_else():
    result = check_chunk_index(index=100, fingerprint=1, next_expected=0, fingerprints_by_index={})
    assert result is ChunkCheckResult.GAP
