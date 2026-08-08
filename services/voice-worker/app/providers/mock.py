"""Mock provider adapters — the default for every workspace (spec §2 rules
19-20, docs/DECISIONS/0002-voice-runtime.md). No credentials, no network
calls, no cost. `MockSTT`/`MockTTS`/`MockTelephony`/`MockMediaRuntime` satisfy
the Protocols in `base.py` directly. `MockLLM` is deliberately a narrower,
purpose-built scripted-FSM class rather than a generic chat-completion
streamer — a real LLM adapter (OpenAILLM/AnthropicLLM, still a Phase 3 stub
pending credentials) is what implements the general `LLMProvider` Protocol;
forcing this rule-driven mock into that same shape would buy nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.providers.base import (
    CallHandle,
    CallStatusInfo,
    MediaSession,
    SynthesisResult,
    TranscriptResult,
    VoiceConfig,
)

# Objective -> ordered list of (field_key, question by language prefix).
# See docs/VOICE_ARCHITECTURE.md §5 / spec §9 for why the greeting itself
# (disclosure + reason + "is now convenient" + value statement) is handled
# separately (agent_version.greeting_text) — these scripts pick up right
# after the customer responds to that opener, per spec's 17-25s "ask one
# simple question" beat, repeated a couple of times before closing.
MOCK_SCRIPTS: dict[str, list[dict[str, str]]] = {
    "qualify_and_route": [
        {
            "field": "topic",
            "te": "ప్రస్తుతం ఏ విషయంలో సహాయం కావాలి అండి?",
            "hi": "आपको किस बारे में मदद चाहिए?",
            "en": "What can I help you with today?",
        },
        {
            "field": "preferred_callback_time",
            "te": "మీకు ఎప్పుడు కాల్ చేస్తే వీలుగా ఉంటుంది అండి?",
            "hi": "आपको कब कॉल करना सही रहेगा?",
            "en": "When would be a good time to call you back?",
        },
    ],
    "qualify_lead": [
        {
            "field": "interest_detail",
            "te": "మీరు దేని గురించి enquiry ఇచ్చారు, కొంచెం చెప్పగలరా అండి?",
            "hi": "आपने किस बारे में पूछताछ की थी?",
            "en": "Could you tell me a bit more about what you're looking for?",
        },
        {
            "field": "timeline",
            "te": "మీరు ఎప్పటికల్లా decision తీసుకోవాలని అనుకుంటున్నారు?",
            "hi": "आप कब तक निर्णय लेना चाहते हैं?",
            "en": "What's your timeline for making a decision?",
        },
    ],
    "book_appointment": [
        {
            "field": "reason_for_visit",
            "te": "మీకు ఏ సమస్య కోసం అపాయింట్‌మెంట్ కావాలి అండి?",
            "hi": "आपको अपॉइंटमेंट किस लिए चाहिए?",
            "en": "What's this appointment for?",
        },
        {
            "field": "preferred_date",
            "te": "మీకు ఏ రోజు వీలుగా ఉంటుంది అండి?",
            "hi": "आपको कौन सा दिन सही रहेगा?",
            "en": "Which day works best for you?",
        },
        {
            "field": "preferred_time",
            "te": "ఏ సమయం మీకు వీలుగా ఉంటుంది?",
            "hi": "कौन सा समय ठीक रहेगा?",
            "en": "What time works for you?",
        },
    ],
    "renewal_reminder": [
        {
            "field": "renewal_interest",
            "te": "మీరు renewal గురించి ఆలోచించారా అండి?",
            "hi": "क्या आपने रिन्यूअल के बारे में सोचा है?",
            "en": "Have you had a chance to think about renewing?",
        },
        {
            "field": "preferred_callback_time",
            "te": "మీకు ఎప్పుడు కాల్ చేస్తే వీలుగా ఉంటుంది?",
            "hi": "आपको कब कॉल करना ठीक रहेगा?",
            "en": "When's a good time to follow up with you?",
        },
    ],
    "collect_feedback": [
        {
            "field": "satisfaction",
            "te": "మీ అనుభవం ఎలా ఉంది అండి?",
            "hi": "आपका अनुभव कैसा रहा?",
            "en": "How was your experience with us?",
        },
        {
            "field": "improvement_area",
            "te": "మేము ఇంకా ఏమి మెరుగుపరచాలి అంటారు?",
            "hi": "हमें और क्या सुधारना चाहिए?",
            "en": "Is there anything we could improve?",
        },
    ],
}

CLOSING_BY_OBJECTIVE: dict[str, dict[str, str]] = {
    "book_appointment": {
        "te": "సరే అండి, మీ అపాయింట్‌మెంట్ వివరాలు నోట్ చేసుకున్నాను. మా టీమ్ confirm చేసి మీకు తెలియజేస్తుంది.",
        "hi": "ठीक है, मैंने आपकी अपॉइंटमेंट की जानकारी नोट कर ली है। हमारी टीम कन्फर्म करके आपको बताएगी।",
        "en": "Great, I've noted your appointment details. Our team will confirm and follow up with you.",
    },
    "default": {
        "te": "ధన్యవాదాలు అండి, మీ వివరాలు నోట్ చేసుకున్నాను. మా టీమ్ మిమ్మల్ని త్వరలో సంప్రదిస్తుంది.",
        "hi": "धन्यवाद, मैंने आपकी जानकारी नोट कर ली है। हमारी टीम जल्द ही आपसे संपर्क करेगी।",
        "en": "Thank you, I've noted that down. Our team will follow up with you shortly.",
    },
}

CLARIFICATION_TRIGGER_WORDS = {"?", "sorry", "again", "repeat", "అర్థం కాలేదు", "మళ్ళీ చెప్పండి"}


def _lang_prefix(language: str) -> str:
    prefix = language.split("-")[0].lower()
    return prefix if prefix in ("te", "hi", "en") else "en"


@dataclass
class MockLLM:
    """Rule-driven script-following mock (docs/DECISIONS/0002-voice-runtime.md).
    A real key (OPENAI_API_KEY/ANTHROPIC_API_KEY) swaps this for an adapter
    implementing the general `LLMProvider` Protocol without touching
    conversation_engine.py's call sites — see app/providers/real_llm.py.
    """

    objective: str
    language: str

    def script(self) -> list[dict[str, str]]:
        return MOCK_SCRIPTS.get(self.objective, MOCK_SCRIPTS["qualify_and_route"])

    def next_question(self, *, asked_count: int) -> dict[str, str] | None:
        steps = self.script()
        if asked_count >= len(steps):
            return None
        return steps[asked_count]

    def closing_text(self) -> str:
        by_lang = CLOSING_BY_OBJECTIVE.get(self.objective, CLOSING_BY_OBJECTIVE["default"])
        return by_lang.get(_lang_prefix(self.language), by_lang["en"])

    def question_text(self, step: dict[str, str]) -> str:
        return step.get(_lang_prefix(self.language), step["en"])


@dataclass
class MockSTT:
    async def transcribe(self, *, audio_or_text: str, language: str) -> TranscriptResult:
        # Text-simulated: the "audio" already is the text. Confidence is
        # deliberately imperfect-looking (not always 1.0) so downstream
        # confidence-threshold logic has something real to react to.
        confidence = 0.97 if len(audio_or_text.strip()) > 2 else 0.6
        return TranscriptResult(text=audio_or_text.strip(), confidence=confidence, language=language, is_final=True)


@dataclass
class MockTTS:
    async def synthesize(self, *, text: str, voice: VoiceConfig) -> SynthesisResult:
        from app.turn_manager import estimate_speaking_duration_ms

        return SynthesisResult(audio_duration_ms=estimate_speaking_duration_ms(text), is_simulated=True)

    async def stop(self, *, session_id: str) -> None:
        return None


@dataclass
class MockTelephony:
    async def create_outbound_call(self, *, to: str, from_: str, context: dict) -> CallHandle:
        return CallHandle(provider_call_ref=f"mock-call-{uuid.uuid4()}", raw={"to": to, "from": from_})

    async def accept_inbound_call(self, *, call_ref: str) -> CallHandle:
        return CallHandle(provider_call_ref=call_ref)

    async def end_call(self, *, call_ref: str) -> None:
        return None

    async def transfer_call(self, *, call_ref: str, target: str) -> None:
        return None

    async def get_call_status(self, *, call_ref: str) -> CallStatusInfo:
        return CallStatusInfo(status="completed")


@dataclass
class MockMediaRuntime:
    sessions: dict[str, MediaSession] = field(default_factory=dict)

    async def create_session(self, *, call_id: str) -> MediaSession:
        session = MediaSession(session_id=f"mock-media-{call_id}")
        self.sessions[call_id] = session
        return session

    async def publish_audio(self, *, session: MediaSession, chunk: bytes) -> None:
        return None

    async def cancel_output(self, *, session: MediaSession) -> None:
        return None
