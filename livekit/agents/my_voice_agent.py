import json
import logging
import os
from dotenv import load_dotenv

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

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my-voice-agent")

LANGUAGE_CONFIGS = {
    "en-IN": {
        "speaker": "shubh",
        "instructions": (
            "You are Kelly, a friendly, concise AI voice assistant for JKR AI Calling. "
            "Speak naturally in Indian English. Keep answers short and concise. "
            "Do not use markdown formatting, bullets, or emojis."
        ),
        "greeting": "Hello! I am Kelly from JKR AI Calling. How can I help you today?",
    },
    "te-IN": {
        "speaker": "kavitha",
        "instructions": (
            "You are a friendly, concise Telugu voice assistant for JKR AI Calling. "
            "Speak naturally in clear Telugu. Keep all answers short, concise, and helpful. "
            "Do not use markdown formatting, bullets, or emojis."
        ),
        "greeting": "నమస్కారం! నేను జేకేఆర్ ఏఐ కాలింగ్ అసిస్టెంట్ ని. మీకు ఎలా సహాయపడగలను?",
    },
    "hi-IN": {
        "speaker": "shubh",
        "instructions": (
            "You are a friendly, concise Hindi voice assistant for JKR AI Calling. "
            "Speak naturally in clear Hindi. Keep all answers short, concise, and helpful. "
            "Do not use markdown formatting, bullets, or emojis."
        ),
        "greeting": "नमस्ते! मैं जेकेआर एआई कॉलिंग से आपका सहायक हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
    },
}


class DynamicVoiceAgent(Agent):
    def __init__(self, language: str = "en-IN", custom_instructions: str | None = None, greeting: str | None = None) -> None:
        cfg = LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["en-IN"])
        instructions = custom_instructions or cfg["instructions"]
        self._greeting = greeting or cfg["greeting"]
        super().__init__(instructions=instructions)

    async def on_enter(self) -> None:
        logger.info(f"Agent entered session, speaking greeting: {self._greeting}")
        self.session.generate_reply(
            instructions=f"Speak this exact greeting naturally to the user: '{self._greeting}'"
        )


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info(f"Agent session entrypoint invoked for room: {ctx.room.name}")

    # Read room metadata if provided by dialer / frontend
    meta = {}
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
        except Exception:
            pass

    lang = meta.get("language", "en-IN")
    speaker = meta.get("speaker") or LANGUAGE_CONFIGS.get(lang, LANGUAGE_CONFIGS["en-IN"])["speaker"]
    phone_number = meta.get("phone_number", "")
    
    logger.info(f"Session Configuration -> Language: {lang}, Speaker: {speaker}, Phone: {phone_number or 'Browser Client'}")

    sarvam_stt_key = os.getenv("SARVAM_API_KEY")
    sarvam_tts_key = os.getenv("SARVAM_TTS_API_KEY") or sarvam_stt_key
    openai_key = os.getenv("OPENAI_API_KEY")

    stt_provider = sarvam.STT(
        language=lang,
        model="saarika:v2.5",
        api_key=sarvam_stt_key,
    )

    llm_provider = openai.LLM(
        model="gpt-4o-mini",
        api_key=openai_key,
    )

    tts_provider = sarvam.TTS(
        target_language_code=lang,
        speaker=speaker,
        model="bulbul:v3-beta",
        api_key=sarvam_tts_key,
    )

    session = AgentSession(
        stt=stt_provider,
        llm=llm_provider,
        tts=tts_provider,
    )

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)

    agent = DynamicVoiceAgent(language=lang)

    logger.info("Starting AgentSession with room...")
    await session.start(agent=agent, room=ctx.room)
    logger.info("AgentSession started successfully!")


if __name__ == "__main__":
    cli.run_app(server)
