# ADR-0003: Safety gate runs regardless of dry-run; dry-run vs. mock-provider are orthogonal

## Status
Accepted

## Context
Spec §14 wants dry-run as the default campaign mode and §2 rule 19-20 wants no real outbound
calls by default with live calls gated behind explicit config + an authorized number allow-list.
Taken literally, "dry-run only logs a structured result and never calls" would mean the Campaign
Engine's dialer loop, retry policy, and outcome pipeline are never exercised end-to-end in the
local demo — which conflicts with §33's demo flow expecting a mock call to actually run through
campaign → call → outcome → intelligence → analytics.

## Decision
Treat **dry-run** and **provider realness** as independent axes:
- `campaign.mode` (`dry_run` | `live`) controls whether the *safety gate's dispatch step* is
  allowed to reach a **real** telephony provider.
- Every workspace's default `provider_accounts` entry for telephony is `mock`. Calls to a `mock`
  provider always execute the full mock call pipeline end-to-end (they cost nothing and reach no
  real phone), **regardless of `campaign.mode`** — this is what makes the campaign engine
  genuinely demoable.
- If a **real** telephony provider is configured, `campaign.mode = live` is required, plus
  `ENABLE_LIVE_CALLS=true` and destination-in-`AUTHORIZED_TEST_NUMBERS`; failing any of those, the
  gate forces the attempt into a structured dry-run result (logged, not dialed) even though the
  campaign is nominally "live."
- The full ten-check safety gate (`docs/SECURITY_AND_COMPLIANCE.md` §2) runs identically whether
  the eventual dispatch is mock or real — dry-run/mock does not skip consent, suppression,
  calling-hours, or rate-limit checks. This keeps the gate's logic honest under test even though
  it never risks a real dial in local dev.

## Consequences
"Dry-run" in the UI is relabeled internally as validate-only vs execute (mock or real); the
`/campaigns/{id}/dry-run` endpoint specifically runs the gate for every pending contact and
reports the would-be outcome **without** reserving contacts or dispatching anything (true
dry-run, no side effects) — this is distinct from launching a campaign with a mock provider,
which does dispatch (safely, to nothing real). Documented clearly in the Campaign UI copy so
operators don't confuse "dry-run validated" with "campaign launched against mock provider."
