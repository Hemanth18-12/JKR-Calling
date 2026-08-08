# ADR-0002: Voice runtime defaults to text-simulated mock, LiveKit kept as an adapter

## Status
Accepted

## Context
Spec §4/§10 wants LiveKit Agents as the primary real-time voice runtime, with Siphon/Bolna/mock
as alternates behind an abstraction. Real LiveKit + real STT/LLM/TTS credentials are not
available in this local build, and spec §2 rule 18-20 requires the platform to be demonstrable
without spending telephony credits and to never place real calls by default. Confirmed with the
project owner: simulate via typed/fixture text rather than real captured/synthesized audio, to
spend the engineering budget on real conversation-engine logic (TurnManager, interruption
classification, spoken formatting, conversation state) rather than audio plumbing.

## Decision
`voice-worker` defines `MediaRuntime`/`SpeechToTextProvider`/`LLMProvider`/`TextToSpeechProvider`
as `Protocol` interfaces. `MockMediaRuntime` + `MockSTT` + `MockTTS` are the default
implementation for every workspace; they operate on text input/output with simulated (seeded,
reproducible) timing metadata standing in for real audio latency. `MockLLM` is rule-driven by
default but the `LLMProvider` interface is satisfied by real `OpenAILLM`/`AnthropicLLM` adapters
if API keys are present in env — so the conversational *content* can be real even when the
*audio* is simulated. `LiveKitMediaRuntime` exists as a typed adapter stub (raises
`NotConfiguredError` without a running LiveKit server + credentials) so swapping in real
infrastructure later touches only the provider registration, not `TurnManager` or the
conversation engine. `docker-compose.yml` includes a LiveKit server for architectural
completeness; the demo path (`make demo`) does not depend on it being healthy.

## Consequences
Latency numbers shown in local analytics are simulated (flagged `is_simulated=true` on
`call_latency_metrics`) until a real provider is wired in — this must never be presented to a
user as measured production latency. The Voice Benchmark Lab (spec §30) is scaffolded, not fully
built, in this pass, since it's most valuable once real providers exist to compare.
