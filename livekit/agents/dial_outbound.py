import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

from livekit import api

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("outbound-dialer")


async def dial(target_phone_number: str):
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    outbound_trunk_id = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK")

    if not livekit_url or not api_key or not api_secret:
        logger.error("Missing LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET in .env!")
        return

    if not outbound_trunk_id:
        logger.error(
            "Missing LIVEKIT_SIP_OUTBOUND_TRUNK in .env! "
            "Please create an Outbound SIP Trunk in LiveKit Cloud Console -> SIP tab."
        )
        return

    # Convert wss:// to https:// for REST API
    http_url = livekit_url.replace("wss://", "https://").replace("ws://", "http://")
    lkapi = api.LiveKitAPI(http_url, api_key, api_secret)

    room_name = f"call-{target_phone_number.replace('+', '')}"
    logger.info(f"Initiating outbound call to {target_phone_number} in room '{room_name}'...")

    try:
        req = api.CreateSIPParticipantRequest(
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=target_phone_number,
            room_name=room_name,
            participant_identity=f"phone-{target_phone_number}",
        )
        sip_res = await lkapi.sip.create_sip_participant(req)
        logger.info(f"SIP Participant created successfully: ID = {sip_res.sip_participant_id}")
        logger.info("The phone should now be ringing! Make sure your agent worker (my_phone_agent.py) is running.")
    except Exception as e:
        logger.error(f"Failed to create SIP participant: {e}")
    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python dial_outbound.py <PHONE_NUMBER_E164>")
        print("Example: python dial_outbound.py +919876543210")
        sys.exit(1)

    phone = sys.argv[1]
    asyncio.run(dial(phone))
