"""
verify_sip_setup.py — Diagnostic script for JKR AI Calling SIP setup.

Checks that the LiveKit Cloud project has the required SIP configuration
(Inbound Trunk + Dispatch Rule) for inbound phone calls to reach the agent.

Usage:
    python verify_sip_setup.py

Requires LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in .env.
"""

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sip-verify")

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"



def ok(msg: str) -> None:
    print(f"  {GREEN}[OK] {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"  {RED}[FAIL] {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN] {msg}{RESET}")


def info(msg: str) -> None:
    print(f"  {CYAN}[INFO] {msg}{RESET}")


async def main() -> None:
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER", "+19453058074")
    sip_endpoint = os.getenv("LIVEKIT_SIP_ENDPOINT", "")

    print(f"\n{BOLD}{'=' * 60}")
    print(f" JKR AI Calling — SIP Setup Verification")
    print(f"{'=' * 60}{RESET}\n")

    # ---- Step 0: Check .env basics ----
    print(f"{BOLD}[1/5] Checking .env configuration...{RESET}")

    if not livekit_url or not api_key or not api_secret:
        fail("Missing LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET in .env!")
        fail("These are required. Find them at: https://cloud.livekit.io -> Project Settings -> Keys")
        sys.exit(1)
    ok(f"LIVEKIT_URL = {livekit_url}")
    ok(f"LIVEKIT_API_KEY = {api_key[:8]}...")

    if not sip_endpoint:
        warn("LIVEKIT_SIP_ENDPOINT is empty in .env")
        # Try to derive it from LIVEKIT_URL
        # wss://jkr-ai-calling-bfz7gt4b.livekit.cloud -> extract subdomain
        if "livekit.cloud" in livekit_url:
            subdomain = livekit_url.split("//")[1].split(".livekit.cloud")[0]
            info(f"Your WebSocket subdomain is: {subdomain}")
            info("Your SIP endpoint is likely based on the Project ID, NOT the WebSocket subdomain.")
            info("Go to https://cloud.livekit.io -> Project Settings to find the exact SIP URI.")
        else:
            warn("Cannot derive SIP endpoint from LIVEKIT_URL. Check LiveKit Cloud Dashboard.")
    else:
        ok(f"LIVEKIT_SIP_ENDPOINT = {sip_endpoint}")
        info(f"Twilio Origination URI should be: sip:{sip_endpoint};transport=tcp")

    ok(f"TWILIO_PHONE_NUMBER = {twilio_number}")

    # ---- Step 1: Connect to LiveKit API ----
    print(f"\n{BOLD}[2/5] Connecting to LiveKit Cloud API...{RESET}")

    try:
        from livekit import api as lk_api
    except ImportError:
        fail("Cannot import livekit.api — make sure livekit-api is installed.")
        fail("Run: pip install livekit-api")
        sys.exit(1)

    # Convert wss:// to https:// for REST API
    http_url = livekit_url.replace("wss://", "https://").replace("ws://", "http://")
    lkapi = lk_api.LiveKitAPI(http_url, api_key, api_secret)
    ok(f"LiveKit API client initialized ({http_url})")

    # ---- Step 2: Check Inbound SIP Trunks ----
    print(f"\n{BOLD}[3/5] Checking Inbound SIP Trunks...{RESET}")

    try:
        trunks_response = await lkapi.sip.list_sip_inbound_trunk(lk_api.ListSIPInboundTrunkRequest())
        inbound_trunks = list(trunks_response.items) if hasattr(trunks_response, 'items') else []

        if not inbound_trunks:
            fail("NO inbound SIP trunks found!")
            fail("You MUST create one in LiveKit Cloud Console -> Telephony -> SIP Trunks -> Create Inbound")
            info("JSON config to paste:")
            info(f'  {{"name": "Twilio Inbound (JKR)", "numbers": ["{twilio_number}"]}}')
        else:
            ok(f"Found {len(inbound_trunks)} inbound trunk(s):")
            found_matching = False
            for t in inbound_trunks:
                trunk_name = getattr(t, 'name', 'unnamed')
                trunk_id = getattr(t, 'sip_trunk_id', 'unknown')
                trunk_numbers = list(getattr(t, 'numbers', []))
                print(f"      Trunk: {trunk_name} (ID: {trunk_id})")
                print(f"      Numbers: {trunk_numbers}")
                if twilio_number in trunk_numbers:
                    found_matching = True
                    ok(f"Trunk '{trunk_name}' includes your Twilio number {twilio_number}")

            if not found_matching:
                warn(f"None of the inbound trunks include {twilio_number}!")
                warn("Either add this number to an existing trunk, or create a new trunk with it.")
    except Exception as e:
        fail(f"Could not list inbound trunks: {e}")
        info("This may mean the LiveKit API credentials are wrong, or the SIP feature isn't enabled.")

    # ---- Step 3: Check Dispatch Rules ----
    print(f"\n{BOLD}[4/5] Checking Dispatch Rules...{RESET}")

    try:
        dispatch_response = await lkapi.sip.list_sip_dispatch_rule(lk_api.ListSIPDispatchRuleRequest())
        dispatch_rules = list(dispatch_response.items) if hasattr(dispatch_response, 'items') else []

        if not dispatch_rules:
            fail("NO dispatch rules found!")
            fail("You MUST create one in LiveKit Cloud Console -> Telephony -> Dispatch Rules")
            info("JSON config to paste:")
            info('  {"name": "JKR Inbound", "rule": {"dispatchRuleIndividual": {"roomPrefix": "call-"}}}')
        else:
            ok(f"Found {len(dispatch_rules)} dispatch rule(s):")
            for r in dispatch_rules:
                rule_name = getattr(r, 'name', 'unnamed')
                rule_id = getattr(r, 'sip_dispatch_rule_id', 'unknown')
                trunk_ids = list(getattr(r, 'trunk_ids', []))
                print(f"      Rule: {rule_name} (ID: {rule_id})")
                print(f"      Trunk IDs: {trunk_ids or '(all trunks - no filter)'}")

                # Check rule type
                rule_obj = getattr(r, 'rule', None)
                if rule_obj:
                    if hasattr(rule_obj, 'dispatch_rule_individual'):
                        ind = rule_obj.dispatch_rule_individual
                        prefix = getattr(ind, 'room_prefix', '')
                        ok(f"Rule type: Individual (each caller gets a unique room, prefix: '{prefix}')")
                    elif hasattr(rule_obj, 'dispatch_rule_direct'):
                        direct = rule_obj.dispatch_rule_direct
                        room = getattr(direct, 'room_name', '')
                        ok(f"Rule type: Direct (all callers go to room: '{room}')")
    except Exception as e:
        fail(f"Could not list dispatch rules: {e}")

    # ---- Step 4: Summary ----
    print(f"\n{BOLD}[5/5] Setup Summary & Next Steps{RESET}")
    print()

    if sip_endpoint:
        info(f"Your LiveKit SIP endpoint: {sip_endpoint}")
        info(f"Twilio Elastic SIP Trunk Origination URI: sip:{sip_endpoint};transport=tcp")
    else:
        warn("LIVEKIT_SIP_ENDPOINT not set — find it in LiveKit Cloud Dashboard -> Project Settings")

    print()
    info("Twilio Console checklist:")
    info("  1. Elastic SIP Trunking -> Trunks -> Create trunk with Origination URI above")
    info(f"  2. Assign phone number {twilio_number} to that trunk (Numbers tab)")
    info(f"  3. Verify {twilio_number} voice config is 'SIP Trunk', NOT 'Webhook'")
    print()
    info("Then start the agent and place a test call:")
    info("  python my_phone_agent.py dev")
    info(f"  Call {twilio_number} from your phone")
    print()

    await lkapi.aclose()
    print(f"{BOLD}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
