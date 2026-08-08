# ADR-0005: Live Call Console updates via SSE over short-interval DB poll

## Status
Accepted

## Context
Spec §10/§20 wants real-time call state, transcript, and metrics visible in a Live Console.
Options: dedicated pub/sub (Redis Streams/NATS) fanned out over WebSocket, or a simpler
SSE-over-poll approach reading directly from the tables `voice-worker` already writes.

## Decision
`GET /calls/{id}/events` on `services/api` is an SSE endpoint that polls `call_turns` /
`call_events` / `call_latency_metrics` / `interruption_events` for the given `call_id` every
~500ms and emits new rows as typed SSE events. This avoids standing up and operating a second
real-time transport for a local-dev/demo-scale product, and keeps the browser's trust boundary at
`services/api` only (`docs/ARCHITECTURE.md` §1) rather than also trusting `voice-worker`
directly.

## Consequences
At meaningfully higher concurrent-call counts, DB-poll fan-out will not scale as cleanly as a
push-based pub/sub — noted as the first thing to revisit if/when load testing (spec §31) shows
it's the bottleneck. Until then it is the lower-operational-complexity choice consistent with
spec §2's tie-breaker rules.
