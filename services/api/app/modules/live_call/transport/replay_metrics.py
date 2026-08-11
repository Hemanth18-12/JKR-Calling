"""P9 — process-wide stale/duplicate/replay counters. Same module-level-
singleton pattern as turns/metrics.py's TurnMetrics, turns/barge_in_metrics
.py's BargeInMetrics, and transport/events.py's MediaStreamMetrics — plain
totals, aggregated across every call this process handles.

`stale_audio_sent_total` is the single most important number here (spec
§97/§150-151: "must remain 0, always; if >0, serious production bug") —
every other counter records something GOOD happening (a replay attempt
correctly blocked); this one records something BAD happening (one got
through). Kept as its own field specifically so it's never accidentally
summed together with the "blocked" counters when reporting call health.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReplayProtectionMetrics:
    stale_llm_delta_dropped_total: int = 0
    stale_speakable_chunk_dropped_total: int = 0
    duplicate_speakable_chunk_dropped_total: int = 0
    chunk_identity_conflict_total: int = 0
    stale_tts_text_dropped_total: int = 0
    stale_tts_audio_dropped_total: int = 0
    duplicate_tts_audio_dropped_total: int = 0
    audio_identity_conflict_total: int = 0
    stale_twilio_media_dropped_total: int = 0
    duplicate_twilio_media_dropped_total: int = 0
    stale_mark_ignored_total: int = 0
    duplicate_mark_ignored_total: int = 0
    stale_turn_result_dropped_total: int = 0
    queue_stale_items_purged_total: int = 0
    unknown_response_artifact_dropped_total: int = 0
    replay_attempt_blocked_total: int = 0
    invalid_state_transition_total: int = 0
    # The zero-leak metric (spec §97) — must stay 0 in every test and every
    # healthy real call. Incremented ONLY in the (should-be-unreachable)
    # branch where the output gate itself would have to be bypassed.
    stale_audio_sent_total: int = 0

    def record_replay_attempt_blocked(self) -> None:
        self.replay_attempt_blocked_total += 1

    def record_blocked(self, specific_field: str) -> None:
        """Increments the specific counter named by `specific_field` AND the
        umbrella `replay_attempt_blocked_total` together (spec §90: the
        umbrella metric fires "whenever old sequence tries to cross a
        guarded boundary," i.e. alongside every specific drop, not instead
        of it) — one call site, both numbers always move together, never
        drift apart from a missed increment at one of two call sites."""
        setattr(self, specific_field, getattr(self, specific_field) + 1)
        self.replay_attempt_blocked_total += 1

    def reset(self) -> None:
        """Test-only — process-wide singletons persist across the whole
        pytest session, so tests that assert on exact counts reset first."""
        for field_name in self.__dataclass_fields__:
            setattr(self, field_name, 0)


# One process-wide instance — same reasoning as every other metrics
# singleton in this codebase.
metrics = ReplayProtectionMetrics()
