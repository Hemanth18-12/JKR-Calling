import asyncio
import logging
import numpy as np
from livekit import api, rtc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live-voice-dialogue")

SAMPLE_RATE = 48000
NUM_CHANNELS = 1
SAMPLES_PER_10MS = SAMPLE_RATE // 100

async def main():
    token = (
        api.AccessToken("devkey", "secret")
        .with_identity("live-caller")
        .with_name("Live Caller")
        .with_grants(api.VideoGrants(room_join=True, room="test-voice-room"))
        .to_jwt()
    )

    room = rtc.Room()

    agent_spoke = asyncio.Event()

    @room.on("participant_connected")
    def on_participant(p: rtc.RemoteParticipant):
        logger.info(f"🟢 [ROOM EVENT] Participant joined: {p.identity}")

    @room.on("track_subscribed")
    def on_track(track: rtc.Track, pub: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant):
        logger.info(f"🎧 [AUDIO TRACK SUBSCRIBED] Type: {track.kind} from {p.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.create_task(listen_agent(rtc.AudioStream(track), p.identity))

    async def listen_agent(stream: rtc.AudioStream, identity: str):
        logger.info(f"🔊 [AUDIO STREAM OPEN] Listening to {identity} audio packets...")
        frames = 0
        total_bytes = 0
        async for event in stream:
            frames += 1
            total_bytes += len(event.frame.data)
            agent_spoke.set()
            if frames == 1:
                logger.info(f"🎙️ [AGENT STARTED SPEAKING] First audio frame received from {identity}!")
            if frames % 100 == 0:
                logger.info(f"🔊 [AGENT SPEAKING] Received {frames} frames ({total_bytes} bytes from Sarvam TTS)")

    logger.info("Connecting to ws://localhost:7880...")
    await room.connect("ws://localhost:7880", token)
    logger.info("Connected to room 'test-voice-room'!")

    # Publish local mic track
    audio_source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
    local_track = rtc.LocalAudioTrack.create_audio_track("user-mic", audio_source)
    await room.local_participant.publish_track(local_track)
    logger.info("Published local microphone track.")

    # Trigger agent dispatch to this room
    logger.info("Dispatching agent worker to 'test-voice-room'...")
    lkapi = api.LiveKitAPI("http://localhost:7880", "devkey", "secret")
    dispatch = await lkapi.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(room="test-voice-room"))
    logger.info(f"Agent dispatch created: {dispatch.id}")
    await lkapi.aclose()

    # Stream ambient audio
    silence = np.zeros(SAMPLES_PER_10MS, dtype=np.int16)
    for _ in range(50):
        await audio_source.capture_frame(rtc.AudioFrame(silence.tobytes(), SAMPLE_RATE, NUM_CHANNELS, SAMPLES_PER_10MS))
        await asyncio.sleep(0.01)

    logger.info("Waiting for agent to enter and speak greeting...")
    try:
        await asyncio.wait_for(agent_spoke.wait(), timeout=15.0)
        logger.info("🎉 SUCCESS: Agent Kelly connected and audio stream is actively speaking!")
        # Stream silence while listening to Kelly speak
        for _ in range(600):
            await audio_source.capture_frame(rtc.AudioFrame(silence.tobytes(), SAMPLE_RATE, NUM_CHANNELS, SAMPLES_PER_10MS))
            await asyncio.sleep(0.01)
    except asyncio.TimeoutError:
        logger.warning("Timeout waiting for agent audio.")

    await room.disconnect()
    logger.info("Dialogue run finished.")

if __name__ == "__main__":
    asyncio.run(main())
