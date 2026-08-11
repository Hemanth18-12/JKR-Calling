"""Internal lifecycle event names (spec §38) and structured logging (§41) —
one place for both so a new event type can't be logged under an
ad-hoc string that drifts from what observability/tests expect.

High-volume per-frame events (inbound media, outbound media) are
deliberately NOT logged here at all — only lifecycle transitions. Raw
audio bytes/base64 payloads must never appear in a log line (§41); every
call site in this module logs metadata only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jkr.live_call.media_stream")

# --- lifecycle events (persisted as CallEvent rows where noted in session.py) ---
MEDIA_STREAM_CONNECTING = "media_stream_connecting"
MEDIA_STREAM_CONNECTED = "media_stream_connected"
MEDIA_STREAM_STARTED = "media_stream_started"
MEDIA_STREAM_STOPPING = "media_stream_stopping"
MEDIA_STREAM_STOPPED = "media_stream_stopped"
MEDIA_STREAM_FAILED = "media_stream_failed"
MEDIA_PLAYBACK_CLEAR = "media_playback_clear"
MEDIA_MARK_SENT = "media_mark_sent"
MEDIA_MARK_RECEIVED = "media_mark_received"
INBOUND_MEDIA_BACKPRESSURE = "inbound_media_backpressure"

# --- P8: barge-in lifecycle events (spec's "logical lifecycle events only,
# never per-VAD-frame DB writes") — one row/log line per meaningful
# transition, not one per signal. See docs/BARGE_IN_ARCHITECTURE.md.
BARGE_IN_CANDIDATE = "barge_in_candidate"
BARGE_IN_BACKCHANNEL = "barge_in_backchannel"
BARGE_IN_CONFIRMED = "barge_in_confirmed"
BARGE_IN_CLEAR_SENT = "barge_in_clear_sent"
BARGE_IN_RESPONSE_CANCELLED = "barge_in_response_cancelled"
BARGE_IN_TURN_COMMITTED = "barge_in_turn_committed"
BARGE_IN_RECOVERY_STARTED = "barge_in_recovery_started"
BARGE_IN_RECOVERY_COMPLETED = "barge_in_recovery_completed"
# --- P8: failure normalization (spec: local stale-generation invalidation
# must preserve correctness even if provider-side cancellation fails) ---
BARGE_IN_CLEAR_FAILED = "clear_failed"
BARGE_IN_LLM_CANCEL_FAILED = "llm_cancel_failed"
BARGE_IN_TTS_CANCEL_FAILED = "tts_cancel_failed"
BARGE_IN_POLICY_ERROR = "interruption_policy_error"
BARGE_IN_RECOVERY_FAILED = "recovery_failed"

# --- high-volume, log-only (never persisted as a DB row) ---
MEDIA_FRAME_RECEIVED = "media_frame_received"
MEDIA_FRAME_SENT = "media_frame_sent"


def log_event(event: str, *, call_session_id: object = None, debug_only: bool = False, **fields: Any) -> None:
    """`debug_only=True` events (high-volume per-frame ones) only actually
    log when VOICE_MEDIA_DEBUG is enabled — checked by the caller before
    even constructing `fields` where that matters for hot-path cost; this
    function itself just gates the final emit so call sites don't all need
    their own `if debug:` guard."""
    payload = {"event": event, "call_session_id": str(call_session_id) if call_session_id else None, **fields}
    level = logging.DEBUG if debug_only else logging.INFO
    logger.log(level, payload)


@dataclass
class MediaStreamMetrics:
    """Process-local counters (§40) — deliberately not a Prometheus/statsd
    export in this pass (disproportionate for P2's scope); real export is
    a follow-up once there's an actual metrics backend wired into this
    service. These are still genuinely useful today via
    /internal debug endpoints or direct inspection in tests."""

    connections_total: int = 0
    active_connections: int = 0
    connection_failures: int = 0
    disconnects: int = 0

    inbound_frames_total: int = 0
    outbound_frames_total: int = 0
    inbound_bytes_total: int = 0
    outbound_bytes_total: int = 0
    dropped_inbound_frames: int = 0

    def record_connect(self) -> None:
        self.connections_total += 1
        self.active_connections += 1

    def record_disconnect(self, *, failed: bool = False) -> None:
        self.active_connections = max(0, self.active_connections - 1)
        self.disconnects += 1
        if failed:
            self.connection_failures += 1

    def record_inbound_frame(self, byte_count: int) -> None:
        self.inbound_frames_total += 1
        self.inbound_bytes_total += byte_count

    def record_outbound_frame(self, byte_count: int) -> None:
        self.outbound_frames_total += 1
        self.outbound_bytes_total += byte_count

    def record_dropped_inbound_frame(self) -> None:
        self.dropped_inbound_frames += 1


# One process-wide instance — deliberately module-level (not per-request
# DI) since it aggregates across every call this process handles, mirroring
# how ProviderHealth-style counters work elsewhere in this codebase.
metrics = MediaStreamMetrics()


@dataclass
class SessionMetrics:
    """Per-session counters, exposed on RealtimeMediaSession for the §75
    "answer these questions about one call" observability requirement."""

    inbound_frames: int = 0
    outbound_frames: int = 0
    inbound_bytes: int = 0
    outbound_bytes: int = 0
    dropped_inbound_frames: int = 0
    marks_sent: list[str] = field(default_factory=list)
    marks_acknowledged: list[str] = field(default_factory=list)
