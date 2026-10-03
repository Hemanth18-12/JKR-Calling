"""Test runner for testing and tuning the AI across 20 real-world question types.

Executes real conversations against voice-worker / conversation engine with Neon DB.
Captures actual turn-by-turn transcripts and checks against quality criteria.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any
import httpx
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

VOICE_WORKER_URL = "http://127.0.0.1:8100"
INTERNAL_TOKEN = "change_me_dev_only_service_to_service_token"
HEADERS = {"X-Internal-Token": INTERNAL_TOKEN}

WORKSPACE_ID = "91b2abf1-9a7b-48d3-ac51-5a1cad458bc7"  # Aaha Dental Care
AGENT_ID = "8991b84a-75db-4b9d-9a30-f3c61de9632f"      # Front Desk Assistant


SCENARIOS = [
    {
        "id": 1,
        "name": "Price question",
        "description": "Caller asks how much a treatment costs ('How much does teeth cleaning cost?')",
        "turns": [
            "Hi, how much does teeth cleaning cost at your clinic?",
        ],
    },
    {
        "id": 2,
        "name": "Trust/skepticism",
        "description": "Caller is skeptical ('Are you even a real AI? How do I know this is legit?')",
        "turns": [
            "Wait, are you even a real AI? How do I know this is legit and not some scam?",
        ],
    },
    {
        "id": 3,
        "name": "Comparison",
        "description": "Caller compares with competitors ('Why should I choose you over Apollo Dental?')",
        "turns": [
            "Why should I choose Aaha Dental Care over other clinics like Apollo Dental?",
        ],
    },
    {
        "id": 4,
        "name": "Scheduling conflict",
        "description": "Caller has a conflict ('I'm busy that day, can we do a different time?')",
        "turns": [
            "I'm really busy on that day, can we do a different time or later this weekend?",
        ],
    },
    {
        "id": 5,
        "name": "Request for a human",
        "description": "Caller asks to speak to a real person ('Can I just talk to a real person?')",
        "turns": [
            "Can I just talk to a real person please? Connect me to a human.",
        ],
    },
    {
        "id": 6,
        "name": "Confusion / repeat request",
        "description": "Caller asks to repeat ('Sorry, what did you say? Can you repeat that?')",
        "turns": [
            "Sorry, what did you say? The line broke up a bit, can you repeat that?",
        ],
    },
    {
        "id": 7,
        "name": "Off-topic tangent",
        "description": "Caller makes small talk / off-topic tangent ('It is so hot today, do you think it will rain?')",
        "turns": [
            "It is so hot outside today in Hyderabad, do you think it is going to rain?",
        ],
    },
    {
        "id": 8,
        "name": "Mid-call language switch",
        "description": "Caller starts in Telugu, switches to English or Hindi partway through",
        "turns": [
            "నమస్కారం అండి, డాక్టర్ గారు ఎప్పుడు ఉంటారు?",
            "Actually, can we talk in English please? I am more comfortable in English.",
        ],
    },
    {
        "id": 9,
        "name": "Impatience",
        "description": "Caller is impatient ('Just get to the point, what do you want?')",
        "turns": [
            "Look, just get to the point, what do you want from me?",
        ],
    },
    {
        "id": 10,
        "name": "Hesitation/indecision",
        "description": "Caller is hesitant ('Let me think about it, I'm not sure')",
        "turns": [
            "Let me think about it, I'm really not sure right now.",
        ],
    },
    {
        "id": 11,
        "name": "Annoyance",
        "description": "Caller is irritated about being called ('Why are you calling me? I didn't ask for this')",
        "turns": [
            "Why are you calling me? Who gave you my number? I'm busy and this is annoying.",
        ],
    },
    {
        "id": 12,
        "name": "Opt-out request",
        "description": "Caller wants to opt out ('Stop calling me, remove my number')",
        "turns": [
            "Stop calling me, remove my number from your database immediately.",
        ],
    },
    {
        "id": 13,
        "name": "Business-specific question",
        "description": "Caller asks concrete business question ('What are your clinic working hours and are you open on Sundays?')",
        "turns": [
            "What are your clinic working hours, and are you open on Sundays?",
        ],
    },
    {
        "id": 14,
        "name": "Personal question to the AI",
        "description": "Caller asks personal question ('What's your name? Are you human? Do you have feelings?')",
        "turns": [
            "What is your name? Are you a human or a robot? Do you have feelings?",
        ],
    },
    {
        "id": 15,
        "name": "Negotiation/discount request",
        "description": "Caller asks for lower price or special deal ('Can you give me a discount or special deal?')",
        "turns": [
            "That sounds a bit steep, can you give me a discount or a special deal on root canal?",
        ],
    },
    {
        "id": 16,
        "name": "Barge-in",
        "description": "Caller interrupts agent mid-flow with new question ('Wait wait, hold on, what is your emergency number?')",
        "turns": [
            "Wait wait, hold on! Quick question, what is your emergency contact number?",
        ],
    },
    {
        "id": 17,
        "name": "Reschedule request",
        "description": "Caller wants to reschedule an existing appointment",
        "turns": [
            "I have an appointment booked with Dr. Sneha tomorrow, but something came up and I need to reschedule it to next week.",
        ],
    },
    {
        "id": 18,
        "name": "Cancellation request",
        "description": "Caller wants to cancel an appointment",
        "turns": [
            "I want to cancel my dental consultation appointment. I won't be able to make it.",
        ],
    },
    {
        "id": 19,
        "name": "Out-of-knowledge-base question",
        "description": "Caller asks question outside knowledge base ('Do you perform robotic laser heart surgery?')",
        "turns": [
            "Do you perform robotic laser cardiac bypass surgery at your clinic?",
        ],
    },
    {
        "id": 20,
        "name": "Genuine disinterest",
        "description": "Caller politely declines ('No thank you, I am really not interested. Have a good day.')",
        "turns": [
            "No thank you, I am really not interested in dental services right now. Have a nice day.",
        ],
    },
]


async def run_scenario(scenario: dict) -> dict[str, Any]:
    print(f"\n================================================================================", flush=True)
    print(f"RUNNING SCENARIO {scenario['id']}: {scenario['name']}", flush=True)
    print(f"Description: {scenario['description']}", flush=True)
    print(f"================================================================================", flush=True)

    transcript_turns = []

    async with httpx.AsyncClient(base_url=VOICE_WORKER_URL, headers=HEADERS, timeout=60.0) as client:
        # 1. Start Session
        start_payload = {
            "workspace_id": WORKSPACE_ID,
            "agent_id": AGENT_ID,
            "contact_name": "Ramesh",
        }
        res = await client.post("/sessions", json=start_payload)
        session = res.json()
        call_id = session["call_id"]
        greeting = session["greeting"]
        transcript_turns.append({"speaker": "Agent", "text": greeting})
        print(f"[Agent]: {greeting}", flush=True)

        # 2. Execute turns
        for user_text in scenario["turns"]:
            print(f"[Caller]: {user_text}", flush=True)
            transcript_turns.append({"speaker": "Caller", "text": user_text})

            turn_res = await client.post(f"/sessions/{call_id}/user-turn", json={
                "workspace_id": WORKSPACE_ID,
                "text": user_text,
            })
            turn_data = turn_res.json()
            agent_text = turn_data.get("agent_turn", {}).get("text") if turn_data.get("agent_turn") else "(No reply / call ended)"
            print(f"[Agent]: {agent_text}", flush=True)
            transcript_turns.append({"speaker": "Agent", "text": agent_text})

            call_status = turn_data.get("call_status")
            if call_status in ("completed", "human_takeover"):
                print(f"--> Call status transitioned to: {call_status}", flush=True)

        # 3. End session if still active
        try:
            await client.post(f"/sessions/{call_id}/end", json={"workspace_id": WORKSPACE_ID})
        except Exception:
            pass

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "description": scenario["description"],
        "transcript": transcript_turns,
    }


async def main():
    import json
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    target_ids = None
    if arg:
        if ".." in arg:
            start_s, end_s = arg.split("..")
            target_ids = set(range(int(start_s), int(end_s) + 1))
        elif "," in arg:
            target_ids = {int(x.strip()) for x in arg.split(",") if x.strip()}
        elif arg.isdigit():
            target_ids = {int(arg)}

    results = []
    output_file = "test_20_results.json"
    
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            results = []

    for sc in SCENARIOS:
        if target_ids is not None and sc["id"] not in target_ids:
            continue
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                res = await run_scenario(sc)
                break
            except Exception as e:
                print(f"Scenario {sc['id']} attempt {attempt} failed: {e}", flush=True)
                if attempt < max_attempts:
                    await asyncio.sleep(2)
                else:
                    raise
        
        # Update or append
        existing = next((r for r in results if r["id"] == sc["id"]), None)
        if existing:
            results[results.index(existing)] = res
        else:
            results.append(res)
            
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        await asyncio.sleep(1)

    print("\n\nExecution finished. Output saved to test_20_results.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
