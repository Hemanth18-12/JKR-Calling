"""P8 — process-wide barge-in counters. Same module-level-singleton pattern
as turns/metrics.py's TurnMetrics and transport/events.py's MediaStreamMetrics
— plain totals, aggregated across every call this process handles, not a
per-call/persisted structure.

Latency numbers (barge_in_clear_latency_ms, barge_in_local_stop_latency_ms,
barge_in_decision_latency_ms, barge_in_recovery_latency_ms) are deliberately
NOT aggregated here as histograms/percentiles — no such infrastructure
exists anywhere else in this codebase either (per-call latencies go through
service.py's _record_latency() DB rows; general lifecycle timing goes
through transport/events.py's log_event() structured fields, e.g.
_connect_streaming_tts's own connect_ms). Barge-in latencies follow the
second pattern: emitted as fields on the relevant log_event() call
(coordinator.py's pipeline_response_interrupted event), not duplicated
into a counter here. See docs/BARGE_IN_ARCHITECTURE.md.

barge_in_false_positive_total / barge_in_false_negative_total cannot be
detected automatically (this process has no way to know a customer's true
intent) — the record_* methods exist for a future human-QA/manual-flagging
path (spec's own human QA rubric) to call; nothing in this pass calls them
automatically, which is stated honestly here rather than faked with a
heuristic that would just be guessing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BargeInMetrics:
    barge_in_candidates_total: int = 0
    barge_in_confirmed_total: int = 0
    backchannels_ignored_total: int = 0
    barge_in_false_positive_total: int = 0
    barge_in_false_negative_total: int = 0
    barge_in_recovery_success_total: int = 0
    barge_in_recovery_failed_total: int = 0
    barge_in_during_generation_total: int = 0
    barge_in_during_tts_total: int = 0
    barge_in_during_playback_total: int = 0
    barge_in_during_closing_total: int = 0

    def record_candidate(self) -> None:
        self.barge_in_candidates_total += 1

    def record_confirmed(self, *, response_state: str | None) -> None:
        self.barge_in_confirmed_total += 1
        if response_state in ("created", "generating_text", "text_streaming"):
            self.barge_in_during_generation_total += 1
        elif response_state == "tts_streaming":
            self.barge_in_during_tts_total += 1
        elif response_state in ("generation_complete", "playback_pending"):
            self.barge_in_during_playback_total += 1

    def record_during_closing(self) -> None:
        self.barge_in_during_closing_total += 1

    def record_backchannel_ignored(self) -> None:
        self.backchannels_ignored_total += 1

    def record_false_positive(self) -> None:
        self.barge_in_false_positive_total += 1

    def record_false_negative(self) -> None:
        self.barge_in_false_negative_total += 1

    def record_recovery_success(self) -> None:
        self.barge_in_recovery_success_total += 1

    def record_recovery_failed(self) -> None:
        self.barge_in_recovery_failed_total += 1


# One process-wide instance — same reasoning as turns/metrics.py's own
# singleton.
metrics = BargeInMetrics()
