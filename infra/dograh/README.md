# Dograh Voice Engine Infrastructure Setup

Dograh replaces LiveKit Agents as JKR AI Calling's real-time voice and telephony runtime.

## Architecture

```
[Twilio / Exotel Telephony]
            │ WebRTC / WebSocket Audio Stream
            ▼
[Dograh Engine / API (port 8002)]
  ├── Pipecat real-time audio pipeline
  ├── Sarvam STT (saarika:v2.5) for Telugu / Hindi / English
  ├── OpenAI LLM (gpt-4o-mini)
  ├── Sarvam TTS (bulbul:v3-beta, voices: shubh, kavitha)
  └── MCP / HTTP API Tools ───► [services/api (port 8000)]
                                  ├── book_appointment
                                  └── send_whatsapp
```

## Services in Docker Compose

1. **`dograh-api`** (Port: `8002` host -> `8000` container):
   - Real-time Pipecat audio pipeline
   - Telephony management (Twilio and Exotel)
   - BYOK integrations for Sarvam STT/TTS and OpenAI LLM
   - Shares PostgreSQL (`pgvector`), Redis, and MinIO with JKR Calling

2. **`dograh-ui`** (Port: `3001` host -> `3000` container):
   - Visual Workflow Builder
   - Test Lab and call session debugger
   - Knowledge base management

## Telephony Setup

### Twilio Integration
- Configured via `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER`.
- Dograh connects directly to Twilio Media Streams or SIP. Outbound calls can be triggered via:
  ```bash
  POST /telephony/initiate-call
  {
    "to": "+91...",
    "from": "+19453058074",
    "workflow_id": "kelly_assistant"
  }
  ```

### Exotel Integration (Target Production)
- Natively supported in Dograh (v1.47.0+, PR #639).
- Configured via `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, `EXOTEL_SUBDOMAIN`, and `EXOTEL_CALLER_ID`.
- Zero custom SIP bridging code needed.

## Workflows
- Located in `infra/dograh/workflows/`.
- `kelly_assistant.json`: Complete graph with Sarvam STT/TTS configuration, localized greetings (English, Telugu, Hindi), tool definitions (`book_appointment`, `send_whatsapp`), and human handoff.
