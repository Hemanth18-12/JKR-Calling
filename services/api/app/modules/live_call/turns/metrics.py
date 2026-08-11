"""P4 — process-wide turn-detection counters (spec §97), same module-level-
singleton pattern as transport/events.py's MediaStreamMetrics. Per-turn
debug trace lives on TurnManager itself (state.TurnDebugTrace) since it's
per-call, not process-wide; these counters aggregate across every call this
process handles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TurnMetrics:
    user_speech_bursts_total: int = 0
    turns_committed_total: int = 0
    turn_fragments_coalesced_total: int = 0
    probable_premature_commit_total: int = 0
    endpoint_max_timeout_total: int = 0
    empty_speech_burst_total: int = 0
    backchannel_detected_total: int = 0

    def record_speech_burst(self) -> None:
        self.user_speech_bursts_total += 1

    def record_turn_committed(self) -> None:
        self.turns_committed_total += 1

    def record_fragment_coalesced(self) -> None:
        self.turn_fragments_coalesced_total += 1

    def record_probable_premature_commit(self) -> None:
        self.probable_premature_commit_total += 1

    def record_endpoint_max_timeout(self) -> None:
        self.endpoint_max_timeout_total += 1

    def record_empty_speech_burst(self) -> None:
        self.empty_speech_burst_total += 1

    def record_backchannel_detected(self) -> None:
        self.backchannel_detected_total += 1


# One process-wide instance — same reasoning as transport/events.py's
# `metrics` singleton: aggregates across every call this process handles.
metrics = TurnMetrics()
