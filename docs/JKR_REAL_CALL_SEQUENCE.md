# JKR Real-Call Sequence — What Exactly Happens During One Real Call

This document describes the **currently active** code path only (batch STT, batch TTS, legacy conversation engine, no barge-in — see [`JKR_RUNTIME_CONFIG_MATRIX.md`](./JKR_RUNTIME_CONFIG_MATRIX.md) for why). Diagram D (barge-in) is explicitly the *dormant/designed* path, clearly labeled as such, since it never executes today but is worth understanding for when it's activated.

**[Stage 2 update]** Diagram B's acknowledgement-rotation note below is now stale — see the inline correction and `docs/STAGE2_REAL_CALL_FIXES.md` Fix 1–3 for what changed. Everything else in this document (batch STT/TTS, 4.0s TurnBuffer, sequential pipeline, dormant barge-in) is unchanged and still accurate.

---

## Layer A — Non-technical (for a product manager)

**Scenario**: Aaha Dental Care's AI agent calls Ravi, a patient, in Telugu-English (`te-en-IN`).

1. Someone clicks "Live Test Call" in the admin UI and picks Ravi's number. The system checks that number is on an approved allow-list (a hard safety gate — only pre-authorized numbers can ever be dialed this way), then asks Twilio to place the call and simultaneously starts preparing the greeting audio.
2. Ravi's phone rings. He answers. Twilio connects a live audio channel back to JKR's server.
3. The greeting plays: a short self-introduction that explicitly says "I'm an AI assistant," then asks if he has a minute. Ravi cannot interrupt this greeting even by talking over it — the system doesn't listen for that yet.
4. Ravi says "Root canal గురించి enquiry ఇచ్చాను" (I made an enquiry about a root canal). The system waits until he's been silent for **a full 4 seconds** before it assumes he's finished talking — this is currently a flat timer, not a smart "did they actually finish their thought" check.
5. His speech is sent off to a transcription service, then to a language-understanding step that pulls out what he's asking about, then — if a factual question was detected — to a knowledge-base lookup, then to a response-writing step. All of this happens sequentially, each step waiting for the previous one, before anything is said back to him.
6. The reply is spoken back using a text-to-speech voice. Right now this is a generic default voice, not one specifically chosen for this business, because the per-agent voice was never actually configured.
7. Ravi asks "Cost entha?" (What's the cost?) mid-conversation. Same sequence repeats: 4-second wait, transcribe, understand, look up pricing in the FAQ, respond.
8. Ravi tries to interrupt with "One minute, Sunday open aa?" while the agent is still mid-sentence about pricing. **Today, this interruption is silently ignored** — the agent keeps talking over him until it finishes its planned sentence, then processes his next turn normally afterward. This is one of the most noticeable gaps between what the system is built to do and what it actually does on a call today.
9. Once the appointment objective is satisfied, the agent delivers a closing line and waits 4 seconds to see if Ravi says anything else before actually hanging up. If he speaks again in that window, the call correctly resumes instead of hanging up on him.
10. After the call ends, a background process re-validates what was extracted, classifies the outcome, writes a summary, and (if applicable) sends a WhatsApp follow-up — none of this happens live, all of it after hangup.

**The one thing worth knowing above everything else**: the system was built with a much more sophisticated real-time architecture (live interruption handling, streaming responses, smarter pause detection) — that code exists and is tested, but a configuration setting that would turn it on was never flipped. The call described above is running the simpler, older behavior underneath a newer transport wrapper.

---

## Layer B — Engineering detail

### Diagram A — Call setup

```mermaid
sequenceDiagram
    participant UI as Admin UI
    participant API as services/api<br/>live_call/service.py
    participant DB as Postgres
    participant Redis as Redis
    participant Sarvam as Sarvam TTS
    participant Twilio as Twilio

    UI->>API: POST /api/v1/live-call {agent_id, to_number}
    API->>API: enable_live_calls check (403 if off)
    API->>API: normalize_e164() + AUTHORIZED_TEST_NUMBERS check (403)
    API->>DB: load Agent + AgentVersion + ConversationPolicy + VoicePersona
    API->>DB: INSERT CallSession(direction="outbound", is_mock=False)<br/>INSERT CallParticipant x2, CallEvent(call_started)
    par concurrent (asyncio.gather)
        API->>Sarvam: POST /text-to-speech (greeting text)
        Sarvam-->>API: WAV audio
        API->>Redis: cache_audio(greeting_id)
    and
        API->>Twilio: POST /Calls.json {To, From, Url=voice webhook, StatusCallback}
        Twilio-->>API: CallSid
    end
    API->>Redis: SET jkr:live_call:{token} {recent_turns:[], policy, tts_speaker, ...} TTL=1800s
    API->>DB: UPDATE CallSession status="dialing"
    Twilio-->>UI: (ringing, out of band)
```

### Diagram B — Normal turn (active path: batch STT, batch TTS, legacy engine)

```mermaid
sequenceDiagram
    participant Customer
    participant Twilio
    participant WS as twilio_media_stream.py<br/>_run_batch_turn_loop
    participant Buf as transitional_bridge.py<br/>TurnBuffer
    participant STT as sarvam_stt.py (batch REST)
    participant Eng as jkr_conversation.engine<br/>process_turn()
    participant RAG as rag.py
    participant OpenAI
    participant TTS as sarvam_tts.py (batch REST)
    participant DB as Postgres

    Customer->>Twilio: speaks
    loop every ~20ms media frame
        Twilio->>WS: media frame (mulaw/8k, base64)
        WS->>Buf: add_frame() — audioop.rms() check
    end
    Note over Buf: speech_ms >= 300 AND<br/>trailing_silence_ms >= 4000<br/>(flat 4.0s wait, no semantics)
    Buf-->>WS: is_turn_complete() = True
    WS->>STT: POST /speech-to-text (full turn WAV)
    STT-->>WS: raw transcript (no confidence, no partials)
    WS->>DB: INSERT CallTurn(speaker=customer, raw transcript)
    WS->>Eng: process_turn(engine_mode="legacy", ...)
    Eng->>DB: load domain vocabulary (every turn, uncached)
    Eng->>OpenAI: extraction call (gpt-4o-mini, JSON mode)
    OpenAI-->>Eng: extracted fields, detected_question, etc.
    Eng->>Eng: domain_normalizer fuzzy-match ("fruit canal" → "root canal treatment")
    Eng->>Eng: planner.decide() — pure Python
    opt question detected
        Eng->>RAG: search_knowledge_with_timing()
        RAG->>OpenAI: embed_text(query)
        RAG->>DB: pgvector cosine_distance search (no index — seq scan)
    end
    Eng->>OpenAI: response-generation call (gpt-4o-mini, max_tokens=150)
    OpenAI-->>Eng: reply text
    Eng->>Eng: SpokenResponseFormatter (fresh instance, but now<br/>seeded from CallSession.state — rotation works<br/>across turns since Stage 2 Fix 2, see quality audit)
    Eng-->>WS: formatted reply
    WS->>DB: INSERT CallTurn(speaker=agent, reply)
    WS->>TTS: POST /text-to-speech (speaker="priya" — fallback default)
    TTS-->>WS: WAV audio
    WS->>Twilio: media frames (mulaw/8k)
    Twilio->>Customer: agent speaks
```

### Diagram C — RAG-answering turn

Same as Diagram B's "question detected" branch, expanded: `rewritten_query` from the extraction call must be non-null (it isn't schema-enforced to agree with `detected_question`); if it's null, RAG is silently skipped and the question goes unanswered even though the customer clearly asked something.

### Diagram D — Barge-in (AS DESIGNED — this path is currently DORMANT, see config matrix)

```mermaid
sequenceDiagram
    participant Customer
    participant Twilio
    participant VAD as EnergyVAD
    participant TM as TurnManager
    participant IP as InterruptionPolicy
    participant Coord as RealtimePipelineCoordinator
    participant TTS as Streaming TTS session
    participant OpenAI as Streaming LLM

    Note over VAD,Coord: NONE of this executes on a real call today —<br/>requires STT_MODE=streaming AND TTS_MODE=streaming AND<br/>TURN_DETECTION_MODE=vad|hybrid AND BARGE_IN_ENABLED=true.<br/>All four are unset/false in current .env.
    Customer->>Twilio: "One minute, cost entha?" (while agent still speaking)
    Twilio->>VAD: audio frames
    VAD->>TM: speech-start signal
    TM->>IP: decide(utterance_so_far, expecting_confirmation)
    IP->>IP: check critical cues, then high-priority cues,<br/>then backchannel list, then word-count threshold
    IP-->>Coord: INTERRUPT (high-priority: "wait"/"one minute")
    Coord->>Coord: interrupt_active_response()<br/>— atomic state flip + cancellation_token.cancel()
    par
        Coord->>OpenAI: cancel in-flight stream
    and
        Coord->>TTS: cancel session, purge unsent text queue
    and
        Coord->>Twilio: send "clear" event
    end
    Coord->>Coord: increment _clear_epoch —<br/>any late-arriving audio for the old response_id<br/>fails can_send_media() and is dropped
    Note over Customer,Twilio: expected total reaction time if active: ~200-450ms
```

### Diagram E — Closing

```mermaid
sequenceDiagram
    participant Eng as engine.py
    participant WS as twilio_media_stream.py
    participant TTS as sarvam_tts.py
    participant Twilio
    participant Customer

    Eng->>Eng: planner returns COMPLETE_OBJECTIVE or SAFETY_STOP
    Eng->>Eng: closing.py::build_closing_text() — canned, always has a finality marker
    Eng-->>WS: closing reply
    WS->>TTS: synthesize closing text
    TTS-->>WS: audio
    WS->>Twilio: send audio + mark
    Twilio-->>WS: mark acknowledged (audio confirmed played)
    WS->>WS: start grace timer (4.0s) — only NOW, not at enqueue time
    alt customer speaks again within 4.0s (and reason wasn't DNC/wrong-number)
        Customer->>Twilio: "Actually, one more thing..."
        WS->>Eng: reopen — objective_status back to "in_progress"
        Note over Eng: call resumes as ACTIVE, correctly
    else silence for 4.0s, or DNC/wrong-number reason
        WS->>Twilio: hangup
    end
```

### What the customer has actually heard — the state the coordinator tracks (when active)

Five distinct, never-collapsed values: `text_generated` (full LLM output) → `text_committed_to_tts` (handed to TTS) → `audio_ms_generated` (TTS produced) → `audio_ms_sent` (enqueued to Twilio) → `audio_ms_acknowledged` (Twilio confirmed via `mark`). The one honest "what did they hear" answer is `_conservative_delivered_text()`: every chunk logged at or before the last **acknowledged** playback unit's timestamp — anything submitted after that point is excluded even if bytes reached the TTS provider, because there's no positive evidence it played.
