import json
import logging
import os
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    cli,
    metrics,
)
from livekit.plugins import openai, sarvam

try:
    from livekit.plugins import silero
    HAS_SILERO = True
except ImportError:
    HAS_SILERO = False

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jkr-phone-agent")

# Telephony prompts optimized for short, snappy conversational phone calls
LANGUAGE_PROMPTS = {
    "en-IN": {
        "speaker": "shubh",
        "instructions": (
            "You are Kelly, a friendly, concise AI voice assistant for JKR AI Calling. "
            "You are talking to a user on a live phone call. "
            "Speak naturally in Indian English. Keep responses very short (1-2 sentences), conversational, and friendly. "
            "Never use markdown formatting, bullet points, asterisks, or emojis."
        ),
        "greeting": "Hello! I am Kelly from JKR AI Calling. How can I help you today?",
    },
    "te-IN": {
        "speaker": "kavitha",
        "instructions": (
            "You are a friendly, concise Telugu voice assistant for JKR AI Calling on a live phone call. "
            "Speak naturally in clear Telugu. Keep all answers short, concise, and helpful (1-2 sentences). "
            "Do not use markdown formatting, bullets, or emojis."
        ),
        "greeting": "నమస్కారం! నేను జేకేఆర్ ఏఐ కాలింగ్ అసిస్టెంట్ ని. మీకు ఎలా సహాయపడగలను?",
    },
    "hi-IN": {
        "speaker": "shubh",
        "instructions": (
            "You are a friendly, concise Hindi voice assistant for JKR AI Calling on a live phone call. "
            "Speak naturally in clear Hindi. Keep all answers short, concise, and helpful (1-2 sentences). "
            "Do not use markdown formatting, bullets, or emojis."
        ),
        "greeting": "नमस्ते! मैं जेकेआर एआई कॉलिंग से आपका सहायक हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
    },
}


class PhoneVoiceAgent(Agent):
    def __init__(
        self,
        language: str = "en-IN",
        custom_instructions: str | None = None,
        greeting: str | None = None,
    ) -> None:
        cfg = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["en-IN"])
        instructions = custom_instructions or cfg["instructions"]
        self._greeting = greeting or cfg["greeting"]
        super().__init__(instructions=instructions)

    async def on_enter(self) -> None:
        logger.info(f"📞 Agent entered phone session. Speaking greeting: '{self._greeting}'")
        self.session.generate_reply(
            instructions=f"Speak this exact greeting naturally to the caller: '{self._greeting}'"
        )


server = AgentServer()


@server.rtc_session(agent_name="jkr-phone")
async def entrypoint(ctx: JobContext) -> None:
    logger.info(f"Incoming call connected to room: {ctx.room.name}")

    # Inspect room metadata or SIP participant details
    meta = {}
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
        except Exception:
            pass

    lang = meta.get("language", "en-IN")
    speaker = meta.get("speaker") or LANGUAGE_PROMPTS.get(lang, LANGUAGE_PROMPTS["en-IN"])["speaker"]

    sarvam_key = os.getenv("SARVAM_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        logger.error("❌ OPENAI_API_KEY is not set in .env! Please add it before starting.")
    if not sarvam_key:
        logger.warning("⚠️ SARVAM_API_KEY is not set in .env! Falling back may be required.")

    # 1. Speech-To-Text (STT) - Sarvam Saarika v2.5
    try:
        stt_provider = sarvam.STT(
            language=lang,
            model="saarika:v2.5",
            api_key=sarvam_key,
        )
        logger.info(f"🎙️ STT Provider: Sarvam (model: saarika:v2.5, lang: {lang})")
    except Exception as e:
        logger.warning(f"Could not init Sarvam STT ({e}), falling back to OpenAI Whisper")
        stt_provider = openai.STT(api_key=openai_key)

    # 2. LLM - OpenAI GPT-4o-mini
    llm_provider = openai.LLM(
        model="gpt-4o-mini",
        api_key=openai_key,
    )
    logger.info("🧠 LLM Provider: OpenAI (model: gpt-4o-mini)")

    # 3. Text-To-Speech (TTS) - Sarvam Bulbul v3-beta (or OpenAI fallback)
    try:
        tts_provider = sarvam.TTS(
            target_language_code=lang,
            speaker=speaker,
            model="bulbul:v3-beta",
            api_key=sarvam_key,
        )
        logger.info(f"🔊 TTS Provider: Sarvam (model: bulbul:v3-beta, speaker: {speaker})")
    except Exception as e:
        logger.warning(f"Could not init Sarvam TTS ({e}), falling back to OpenAI TTS")
        tts_provider = openai.TTS(model="tts-1", voice="alloy", api_key=openai_key)

    # 4. Voice Activity Detection (VAD) / Turn Detection for barge-in
    session_kwargs = {
        "stt": stt_provider,
        "llm": llm_provider,
        "tts": tts_provider,
    }

    if HAS_SILERO:
        try:
            session_kwargs["vad"] = silero.VAD.load()
            logger.info("⚡ Silero VAD loaded for real-time barge-in.")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD ({e}), using default turn detector.")

    session = AgentSession(**session_kwargs)

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)

    @ctx.room.on("participant_connected")
    def _on_participant_connected(p: rtc.RemoteParticipant) -> None:
        is_sip = p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        logger.info(f"👤 Caller joined room: {p.identity} (Kind: {'SIP Phone' if is_sip else 'Web/App'})")

    agent = PhoneVoiceAgent(language=lang)

    logger.info("🚀 Starting agent session with phone room...")
    await session.start(agent=agent, room=ctx.room)
    logger.info("✅ Agent is now live on the call!")


if __name__ == "__main__":
    cli.run_app(server)
