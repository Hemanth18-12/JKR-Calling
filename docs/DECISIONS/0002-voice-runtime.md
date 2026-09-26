# ADR-0002: Voice runtime powered by Dograh (Pipecat pipeline), replacing LiveKit

## Status
Accepted (Migrated from LiveKit Agents to Dograh)

## Context
Initial prototypes evaluated LiveKit Agents, but turn-by-turn response latency across WebRTC room
joins, SIP trunk gateways, and worker dispatch caused callers to experience noticeable response lag.
Dograh (https://github.com/dograh-hq/dograh) was chosen to replace LiveKit as the primary real-time
voice runtime due to its ultra-low latency Pipecat streaming core, native BYOK support for Sarvam STT/TTS
(Telugu, Hindi, English), and native telephony integrations for Twilio and Exotel.

## Decision
The real-time voice and telephony pipeline is standardized on **Dograh** (`infra/dograh/`),
running via Docker Compose alongside PostgreSQL, Redis, and MinIO. Dograh handles low-latency
media streaming directly via WebSockets/WebRTC, routing audio to Sarvam Streaming STT (`saarika:v2.5`),
OpenAI LLM (`gpt-4o-mini`), and Sarvam Streaming TTS (`bulbul:v3-beta`). Custom business tools
(`book_appointment`, `send_whatsapp`) are bound as HTTP API / MCP tools executed against `services/api`.
The headless text-simulated `MockMediaRuntime` remains available for offline testing.

## Consequences
Latency numbers shown in local analytics are simulated (flagged `is_simulated=true` on
`call_latency_metrics`) until a real provider is wired in — this must never be presented to a
user as measured production latency. The Voice Benchmark Lab (spec §30) is scaffolded, not fully
built, in this pass, since it's most valuable once real providers exist to compare.
