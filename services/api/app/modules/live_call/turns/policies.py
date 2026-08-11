"""P4 — TurnPolicy: the tunable numbers TurnManager decides against (spec
§10/§15/§16). Presets (FAST/BALANCED/PATIENT) are starting points for
benchmarking, explicitly NOT presented as measured-optimal — spec §16: "Do
not treat these as permanent values," §56: "the same pause behavior may
not work equally well across profiles."

Deliberately NOT diverged per language profile in this pass: doing that
credibly requires real per-language PSTN benchmark data (spec §79-81),
which requires actual test calls this pass hasn't placed. Inventing
different numbers per language without measurement would be indistinguishable
from guessing — see docs/P4_TURN_DETECTION_RESULTS.md for what real
benchmarking (once performed) should do with this function's `language_code`
parameter, which is accepted now specifically so that plumbing doesn't need
to change later.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TurnPolicy:
    mode: str = "provider"  # "provider" | "vad" | "hybrid"
    profile: str = "balanced"  # "fast" | "balanced" | "patient" — informational under provider mode
    min_endpoint_delay_ms: int = 0
    max_endpoint_delay_ms: int = 2000
    thinking_pause_extension_ms: int = 800
    # Max gap between two STT finals for them to still be coalesced as one
    # logical turn (spec §26) — a gap larger than this is treated as a
    # genuinely new, separate turn (spec §71), not a continuation.
    fragment_coalesce_ms: int = 1500


# provider mode: TurnManager reproduces pre-P4 behavior exactly — commit on
# the first valid, non-duplicate STT final, no waiting. This is what makes
# TURN_DETECTION_MODE=provider (the default) byte-behavior-identical to P3.
PROVIDER_POLICY = TurnPolicy(mode="provider", profile="provider", min_endpoint_delay_ms=0, max_endpoint_delay_ms=0, thinking_pause_extension_ms=0, fragment_coalesce_ms=0)

FAST = TurnPolicy(mode="hybrid", profile="fast", min_endpoint_delay_ms=150, max_endpoint_delay_ms=1200, thinking_pause_extension_ms=500, fragment_coalesce_ms=900)
BALANCED = TurnPolicy(mode="hybrid", profile="balanced", min_endpoint_delay_ms=300, max_endpoint_delay_ms=2000, thinking_pause_extension_ms=900, fragment_coalesce_ms=1500)
PATIENT = TurnPolicy(mode="hybrid", profile="patient", min_endpoint_delay_ms=500, max_endpoint_delay_ms=3000, thinking_pause_extension_ms=1400, fragment_coalesce_ms=2200)

_PRESETS: dict[str, TurnPolicy] = {"fast": FAST, "balanced": BALANCED, "patient": PATIENT}


def get_policy(*, mode: str, profile: str = "balanced", language_code: str | None = None) -> TurnPolicy:
    """`language_code` is accepted but not yet used to diverge values — see
    module docstring. Kept as a required-shaped parameter now so callers
    (streaming_bridge.py) don't need to change when real per-language
    tuning is added later."""
    del language_code  # not yet used — see module docstring
    if mode == "provider":
        return PROVIDER_POLICY
    base = _PRESETS.get(profile, BALANCED)
    return replace(base, mode=mode)
