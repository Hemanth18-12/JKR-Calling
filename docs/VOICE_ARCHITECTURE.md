# Voice Architecture

## 1. Pipeline (per master spec §10)

```
Phone/SIP participant → LiveKit room → noise cancellation → VAD → streaming STT →
language/turn detection → conversation state update → knowledge retrieval / tools →
LLM response generation → SpokenResponseFormatter → streaming TTS → LiveKit audio output
```

In this build, the pipeline runs against a **text-simulated** transport by default
(`MockMediaRuntime`): "audio" is typed/fixture text plus simulated timing, so every stage above
the transport (STT boundary through TTS boundary) is real code exercised by real timers, not a
demo-only shortcut. See `docs/DECISIONS/0002-voice-runtime.md`.

## 2. Provider interfaces (`services/voice-worker/app/providers/base.py`)

```python
class TelephonyProvider(Protocol):
    async def create_outbound_call(self, to: str, from_: str, context: dict) -> CallHandle: ...
    async def accept_inbound_call(self, call_ref: str) -> CallHandle: ...
    async def end_call(self, call_ref: str) -> None: ...
    async def transfer_call(self, call_ref: str, target: str) -> None: ...
    async def get_call_status(self, call_ref: str) -> CallStatus: ...

class SpeechToTextProvider(Protocol):
    async def start_stream(self, language: str) -> STTStream: ...
    async def send_audio(self, stream: STTStream, chunk: bytes) -> None: ...
    async def close_stream(self, stream: STTStream) -> TranscriptResult: ...

class LLMProvider(Protocol):
    async def stream_response(self, messages: list[Message], tools: list[ToolDef]) -> AsyncIterator[Token]: ...
    async def generate_structured_output(self, prompt: str, schema: type[T]) -> T: ...

class TextToSpeechProvider(Protocol):
    async def stream_audio(self, text: str, voice: VoiceConfig) -> AsyncIterator[AudioChunk]: ...
    async def stop_audio(self, session_id: str) -> None: ...

class MediaRuntime(Protocol):
    async def create_session(self, call_id: str) -> MediaSession: ...
    async def publish_audio(self, session: MediaSession, chunk: bytes) -> None: ...
    async def cancel_output(self, session: MediaSession) -> None: ...
```

Implementations this pass: `MockSTT`, `MockLLM` (rule-driven; falls back to a real
`OpenAILLM`/`AnthropicLLM` adapter if credentials are present in env), `MockTTS`,
`MockTelephony`, `MockMediaRuntime`. Adapter files for `TwilioTelephony`, `SIPTrunkTelephony`,
`DeepgramSTT`, `SarvamSTT`, `GoogleSTT`, `ElevenLabsTTS`, `CartesiaTTS`, `SarvamTTS`, `OpenAITTS`
exist as typed stubs with a `NotConfiguredError` raised until credentials are supplied — this
satisfies "clean interfaces for Exotel/Plivo/Telnyx" style extensibility without pretending they
work unconfigured.

## 3. Provider router

`services/voice-worker/app/providers/router.py` selects a provider per (workspace, language,
agent config) using a priority list stored on `provider_accounts`, checks `provider_health`
before selecting, and on a `ProviderUnavailable` falls back to the next entry, writing a
`call_events` row of type `provider_fallback` with the reason — this is the audit trail for "why
did this call use provider B instead of A."

## 4. TurnManager (`services/voice-worker/app/turn_manager.py`)

State: `user_speaking`, `agent_speaking`, `interim_transcript`, `final_transcript`,
`active_sequence_id`, `cancelled_sequence_ids`, `turn_id`, `user_interruption_count`,
`agent_interruption_count`, `recovery_count`, `silence_ms`, `user_stop_ts`, `agent_start_ts`,
`agent_end_ts`.

On a user utterance arriving while `agent_speaking = true`:

1. Classify as **meaningful** vs **false interruption** using, in order: phrase-list match
   against a configurable short-acknowledgement list (`hmm`, `okay`, `haa`, `అవును`, `right`,
   ...) in the agent's active language(s); word count (`< 3` words + phrase-list hit ⇒ false);
   VAD-equivalent duration (simulated from typed input length in mock mode, real VAD duration in
   a real runtime); confidence.
2. If meaningful: cancel `active_sequence_id` (mark it `interrupted` in `call_turns`, stop
   emitting further formatted text for it), append to `interruption_events`, increment
   `user_interruption_count`, transition to listening, and generate the next agent turn from the
   *already-said* portion of the interrupted turn plus the new user input — never a full restart
   of the previous sentence (spec §11 requirement 8).
3. If false: agent continues; the utterance is logged but does not cancel output.

Every transition writes a `call_latency_metrics` row: `user_stop_ts → agent_first_output_ts`,
plus a `stop_latency_ms` for how fast the in-flight output was cancelled. Targets tracked (not
guaranteed, per spec §11): meaningful-interrupt stop < 300ms, P50 stop→next-audio < 700ms, P95 <
1.5s, false-interruption rate < 5%, monologue < 12s. These are dashboarded in
`/app/analytics/conversations`, computed from real numbers — simulated timing in mock mode, real
provider timing once a real runtime is configured.

## 5. Conversation engine

Per spec §12: after every user turn, `voice-worker` updates a structured `conversation_state`
JSON (objective, language, intent, sentiment, known/missing/uncertain fields, risk flags,
`customer_requested_human`, `do_not_call`, `next_best_action`, `objective_status`), persists it on
`call_sessions.state`, and selects a next-best-action from: ask_question, clarify,
answer_from_knowledge, confirm_critical_info, execute_tool, wait_for_tool, offer_human_transfer,
schedule_callback, close_conversation, add_do_not_call, end_wrong_number_call.

## 6. SpokenResponseFormatter

`services/voice-worker/app/spoken_formatter.py` — never sends raw LLM output to TTS. Strips
markdown/URLs, expands abbreviations, normalizes numbers/currency/dates for speech, enforces
short-sentence output, inserts natural pause punctuation, rotates through a
non-repeating acknowledgement library (never the same acknowledgement twice in a row), and — this
is a hard rule, not a style preference — refuses to silently guess name/date/time/amount/rank/
phone/booking/payment/address: below a confidence threshold it emits a clarification request
instead of a stated value. Unit-tested directly (`services/voice-worker/tests/test_spoken_formatter.py`).

## 7. Latency instrumentation

Every provider call (STT partial/final, LLM first-token, TTS first-audio) writes to
`call_latency_metrics` with `provider`, `stage`, `duration_ms`. Mock providers produce
deterministic-but-realistic simulated numbers (seeded per call, so re-running a fixture gives
reproducible dashboards) with a `is_simulated=true` flag on the metric row, so real vs. mock
timing is never conflated in analytics.
