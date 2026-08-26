import asyncio
import logging
import os
import aiohttp
from dotenv import load_dotenv

from livekit import rtc, api
from livekit.agents import (
    Agent,
    AgentSession,
    utils,
    room_io,
)
from livekit.plugins import openai, sarvam

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent-daemon")

class KellyVoiceAgent(Agent):
    def __init__(self, greeting="Hello! I am Kelly from JKR AI Calling. How can I help you today?"):
        super().__init__(
            instructions=(
                "You are Kelly, a friendly, concise AI voice assistant for JKR AI Calling. "
                "Keep all responses short, natural, and conversational in English or Telugu as requested. "
                "Do not use markdown formatting, bullets, asterisks, or emojis."
            )
        )
        self._greeting = greeting

    async def on_enter(self) -> None:
        logger.info(f"Speaking initial greeting: {self._greeting}")
        self.session.generate_reply(
            instructions=f"Speak this greeting naturally to the user: '{self._greeting}'"
        )


async def run_agent_in_room(room_name="test-voice-room"):
    async with utils.http_context.open():
        while True:
            try:
                logger.info(f"Starting agent session for room: {room_name}...")
                
                token = (
                    api.AccessToken("devkey", "secret")
                    .with_identity("kelly-agent")
                    .with_name("Kelly (AI Assistant)")
                    .with_grants(api.VideoGrants(room_join=True, room=room_name))
                    .to_jwt()
                )

                room = rtc.Room()

                sarvam_stt_key = os.getenv("SARVAM_API_KEY")
                sarvam_tts_key = os.getenv("SARVAM_TTS_API_KEY") or sarvam_stt_key
                openai_key = os.getenv("OPENAI_API_KEY")

                stt_provider = sarvam.STT(
                    language="en-IN",
                    model="saarika:v2.5",
                    api_key=sarvam_stt_key,
                )

                llm_provider = openai.LLM(
                    model="gpt-4o-mini",
                    api_key=openai_key,
                )

                tts_provider = sarvam.TTS(
                    target_language_code="en-IN",
                    speaker="shubh",
                    model="bulbul:v3-beta",
                    api_key=sarvam_tts_key,
                )

                session = AgentSession(
                    stt=stt_provider,
                    llm=llm_provider,
                    tts=tts_provider,
                )

                agent = KellyVoiceAgent()

                logger.info(f"Connecting to ws://localhost:7880 in room '{room_name}'...")
                await room.connect("ws://localhost:7880", token)
                logger.info(f"Agent connected to '{room_name}'! Starting session...")

                await session.start(
                    agent=agent,
                    room=room,
                    room_input_options=room_io.RoomInputOptions(close_on_disconnect=False)
                )
                logger.info("Kelly is ONLINE and READY! Waiting for caller audio...")

                # Loop while connected
                while room.isconnected():
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Session error: {e}, restarting in 2 seconds...", exc_info=True)
                await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(run_agent_in_room())
