import os
import sys
import logging
from dotenv import load_dotenv
from twilio.rest import Client

from pathlib import Path

# Load .env from both the agent directory and workspace root
agent_env = Path(__file__).resolve().parent / ".env"
root_env = Path(__file__).resolve().parents[2] / ".env"
if agent_env.exists():
    load_dotenv(agent_env)
if root_env.exists():
    load_dotenv(root_env)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("outbound-caller")


def make_call(target_phone_number: str):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER") or "+19453058074"
    sip_uri = os.getenv("LIVEKIT_SIP_ENDPOINT") or "jkr-ai-calling-bfz7gt4b.sip.livekit.cloud"

    if not account_sid or not auth_token:
        logger.error("❌ Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN in .env!")
        logger.error("Please add your Twilio Account SID and Auth Token to .env before calling.")
        return

    logger.info(f"Connecting to Twilio with Account SID: {account_sid[:6]}...")
    client = Client(account_sid, auth_token)

    # When the user picks up, Twilio dials into the LiveKit SIP endpoint matching the trunk number
    twiml_instruction = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>sip:{twilio_number}@{sip_uri};transport=tcp</Sip>
    </Dial>
</Response>"""

    logger.info(f"📞 Placing outbound call to: {target_phone_number} from Twilio number: {twilio_number}...")

    try:
        call = client.calls.create(
            to=target_phone_number,
            from_=twilio_number,
            twiml=twiml_instruction,
        )
        logger.info(f"🎉 Outbound call initiated successfully! Call SID: {call.sid}")
        logger.info(f"Status: {call.status}")
        logger.info("Your phone should start ringing in a few seconds! Answer the call to talk with Kelly.")
    except Exception as e:
        logger.error(f"❌ Failed to initiate call: {e}")
        logger.info("\nTroubleshooting:")
        logger.info("- Check if your Twilio account is active and has sufficient balance / trial credits.")
        logger.info("- If using Twilio Trial, ensure the recipient phone number is added to 'Verified Caller IDs'.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nUsage: python call_user.py <YOUR_PHONE_NUMBER>")
        print("Example: python call_user.py +919876543210\n")
        sys.exit(1)

    recipient = sys.argv[1].strip()
    make_call(recipient)
