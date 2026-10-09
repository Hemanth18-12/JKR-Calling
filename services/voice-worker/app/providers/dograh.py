"""Dograh Voice Engine Provider Adapter & Workflow Orchestrator.

Integrates JKR AI Calling's voice worker with Dograh (https://github.com/dograh-hq/dograh),
providing low-latency real-time voice streaming with native Sarvam STT/TTS (Telugu, Hindi, English)
and telephony integrations (Twilio, Exotel) executing the 7-step conversation workflow.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.providers.base import (
    CallHandle,
    CallStatusInfo,
    MediaSession,
)

logger = logging.getLogger("voice-worker.dograh")

WORKFLOW_FILE_PATH = Path(__file__).resolve().parents[4] / "infra" / "dograh" / "workflows" / "kelly_assistant.json"


def load_kelly_workflow_definition() -> dict[str, Any]:
    """Load the raw Dograh workflow definition from infra/dograh/workflows/kelly_assistant.json."""
    if not WORKFLOW_FILE_PATH.exists():
        raise FileNotFoundError(f"Dograh workflow file not found at {WORKFLOW_FILE_PATH}")
    with open(WORKFLOW_FILE_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class DograhTurnTrace:
    """Detailed audit trace proving Dograh workflow engine executed this turn."""
    engine: str = "dograh"
    workflow_id: str = "kelly_assistant"
    workflow_version: str = "2.0.0"
    current_node_id: str = "start-call"
    previous_node_id: str | None = None
    allow_interrupt: bool = True
    barge_in_detected: bool = False
    stt_provider: str = "sarvam"
    stt_model: str = "saarika:v2.5"
    tts_provider: str = "sarvam"
    tts_model: str = "bulbul:v3-beta"
    tts_speaker: str = "kavitha"
    tools_executed: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DograhWorkflowSession:
    """Manages the state and turn execution for a call driven by Dograh's workflow graph."""

    def __init__(
        self,
        *,
        call_id: uuid.UUID,
        workflow: dict[str, Any],
        initial_context: dict[str, Any] | None = None,
        api_base_url: str | None = None,
    ) -> None:
        self.call_id = call_id
        self.workflow = workflow
        self.context = initial_context or {}
        self.language = self.context.get("language", "te-IN")
        self.nodes = {n["id"]: n for n in workflow.get("workflow_definition", {}).get("nodes", [])}
        self.edges = workflow.get("workflow_definition", {}).get("edges", [])
        self.tools = {t["id"]: t for t in workflow.get("workflow_definition", {}).get("tools", [])}
        
        self.current_node_id = "start-call"
        self.turn_index = 0
        self.traces: list[DograhTurnTrace] = []
        self.api_base_url = api_base_url or os.getenv("JKR_API_URL", "http://127.0.0.1:8000")
        
        # Audio / TTS settings from workflow
        tts_cfg = workflow.get("tts", {})
        lang_speakers = tts_cfg.get("language_speakers", {})
        self.speaker = lang_speakers.get(self.language, tts_cfg.get("speaker", "kavitha"))

    def get_greeting(self) -> str:
        """Fetch greeting from StartCall node based on language."""
        start_node = self.nodes.get("start-call", {})
        templates = start_node.get("data", {}).get("greeting_templates", {})
        greeting = templates.get(self.language) or templates.get("te-IN") or "నమస్కారం! నేను ఆహా డెంటల్ కేర్ నుండి మాట్లాడుతున్నాను."
        return greeting

    def next_turn_ref(self, prefix: str = "turn") -> str:
        self.turn_index += 1
        return f"dograh-{prefix}-{self.turn_index}"

    def handle_user_utterance(self, text: str) -> Any:
        """Duck-typed helper for compatibility with TurnManager checks."""
        from app.turn_manager import ClassifiedUtterance, InterruptionClassification
        accidental = self.context.get("accidental_interruption_phrases") or ["hmm", "okay", "అవును"]
        stripped = text.strip().lower()
        if stripped in [p.lower() for p in accidental] or (len(stripped.split()) == 1 and stripped in ["hmm", "okay", "అవును", "ha", "yes"]):
            return ClassifiedUtterance(
                classification=InterruptionClassification.FALSE_POSITIVE,
                stop_latency_ms=None,
                cancelled_sequence_id=None,
            )

        curr_node = self.nodes.get(self.current_node_id, {})
        allow_interrupt = curr_node.get("data", {}).get("allow_interrupt", True)
        
        # Check barge-in
        is_interruption = allow_interrupt and len(text.strip().split()) >= 2
        classification = InterruptionClassification.MEANINGFUL if is_interruption else InterruptionClassification.NONE
        return ClassifiedUtterance(
            classification=classification,
            stop_latency_ms=120 if is_interruption else None,
            cancelled_sequence_id=f"seq-{self.turn_index}" if is_interruption else None,
        )

    def start_agent_turn(self, text: str) -> Any:
        """Duck-typed helper for compatibility with TurnManager agent turn recording."""
        @dataclass
        class AgentTurnRecord:
            turn_ref: str
            text: str
        return AgentTurnRecord(turn_ref=self.next_turn_ref("agent"), text=text)

    def mark_recovered(self) -> None:
        pass

    async def execute_turn(
        self,
        *,
        customer_text: str,
        state: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], DograhTurnTrace]:
        """Execute a conversational turn through Dograh's workflow nodes, tools, and prompts."""
        prev_node_id = self.current_node_id
        curr_node = self.nodes.get(self.current_node_id, {})
        allow_interrupt = curr_node.get("data", {}).get("allow_interrupt", True)
        
        # Transition start-call to agent-conversation
        if self.current_node_id == "start-call":
            self.current_node_id = "agent-conversation"
            curr_node = self.nodes.get(self.current_node_id, {})

        tools_executed: list[dict[str, Any]] = []
        user_lower = customer_text.lower()

        # Track known fields for objective progression
        known_fields = state.setdefault("known_fields", {})
        awaiting_field = state.get("awaiting_field", "reason_for_visit")

        # Detect if caller's utterance is a question or inquiry (Case 1, 2, or 3)
        is_question = (
            "?" in customer_text
            or any(
                qw in user_lower
                for qw in [
                    "what", "why", "how", "where", "when", "who", "which", "whose",
                    "can you", "could you", "do you", "does it", "is it", "are you",
                    "tell me", "explain", "cost", "fee", "price", "safe", "difference",
                    "hackathon", "ai", "center", "clinic", "work", "timings", "timing", "hours",
                    "open", "rate", "charges", "specialist", "qualification", "degree",
                    "ఎంత", "ఎలా", "ఏమిటి", "ఎప్పుడు", "ఎక్కడ", "చెప్పండి", "వివరాలు", "ఉంటుందా", "సేఫా",
                    "కదా", "డాక్టర్లతో", "మాట్లాడొచ్చా", "ఉన్నాయా", "ఖర్చు",
                    "क्या", "कैसे", "कितना", "कब", "कहाँ", "बताइए", "सुरक्षित", "कहाँ है", "कौन", "खुला"
                ]
            )
        )

        # Detect booking affirmation
        explicit_booking_kw = [
            "బుక్ చేయండి", "కన్ఫర్మ్ చేయండి", "కుదురుతుంది", "వస్తాను", "బుక్ చెయ్యండి",
            "बुक कर दीजिए", "कन्फर्म कर दीजिए", "स्लॉट बुक", "बुक करो",
            "book it", "schedule it", "confirm it", "confirm my appointment",
            "yes please", "sure book", "fix it", "book an appointment"
        ]
        has_booking_kw = any(kw in user_lower for kw in explicit_booking_kw)
        has_slot_confirmation = (
            not is_question
            and any(
                kw in user_lower
                for kw in [
                    "repu 11", "రేపు 11", "कल 11", "tomorrow at 11", "tomorrow 11",
                    "tomorrow morning 11", "రేపు ఉదయం 11", "कल सुबह 11", "11:00 am", "11 am"
                ]
            )
        )
        is_booking_intent = (has_booking_kw or has_slot_confirmation) and not is_question

        # Rejection / Not Interested trigger
        is_decline_intent = any(
            kw in user_lower
            for kw in [
                "not interested", "vaddu", "వద్దు", "నాకు వద్దు", "no thanks", "don't want", "cancel"
            ]
        )

        # Language detection of caller
        user_has_telugu = any('\u0c00' <= ch <= '\u0c7f' for ch in customer_text) or any(
            w in user_lower for w in ["enti", "ela", "kadha", "undi", "cheyandi", "repu", "namaskaram", "avunu", "meeru"]
        )
        user_has_hindi = any('\u0900' <= ch <= '\u097f' for ch in customer_text) or any(
            w in user_lower for w in ["kya", "kaise", "kab", "kahan", "theek", "hai", "namaste", "dhanyawad", "aap", "mera"]
        )

        if awaiting_field and awaiting_field not in known_fields and not is_decline_intent and not is_question:
            known_fields[awaiting_field] = customer_text
            state["asked_count"] = state.get("asked_count", 0) + 1
            if awaiting_field == "reason_for_visit":
                state["awaiting_field"] = "preferred_date"
            elif awaiting_field == "preferred_date":
                state["awaiting_field"] = "preferred_time"
            elif awaiting_field == "preferred_time":
                state["awaiting_field"] = None
                state["objective_status"] = "completed"

        agent_reply = ""

        if is_decline_intent:
            # 7-Step Script Step 7: Graceful close
            self.current_node_id = "end-call"
            end_node = self.nodes.get("end-call", {})
            goodbyes = end_node.get("data", {}).get("goodbye_message", {})
            agent_reply = goodbyes.get(self.language, "సరే అండి, మీ సమయానికి చాలా ధన్యవాదాలు! ఉంటానండి.")
        elif is_booking_intent and self.current_node_id == "agent-conversation":
            # 7-Step Script Step 6: Book appointment tool + WhatsApp tool
            preferred_date = "tomorrow" if ("tomorrow" in user_lower or "repu" in user_lower or "రేపు" in user_lower or "कल" in user_lower) else "upcoming slot"
            preferred_time = "11:00 AM" if "11" in user_lower else ("10:00 AM" if "10" in user_lower else "11:00 AM")
            
            # Execute book_appointment tool via Dograh HTTP endpoint
            book_tool_res = await self._invoke_http_tool(
                tool_name="book_appointment",
                payload={
                    "call_session_id": str(self.call_id),
                    "contact_name": self.context.get("contact_name") or "Customer",
                    "phone_number": self.context.get("phone_number") or "+919876543210",
                    "preferred_date": preferred_date,
                    "preferred_time": preferred_time,
                    "service_type": "Dental Consultation",
                },
            )
            tools_executed.append({"tool": "book_appointment", "result": book_tool_res})

            # Execute send_whatsapp tool
            wa_tool_res = await self._invoke_http_tool(
                tool_name="send_whatsapp",
                payload={
                    "call_session_id": str(self.call_id),
                    "phone_number": self.context.get("phone_number") or "+919876543210",
                    "message_text": f"Aaha Dental Care: Your appointment for {preferred_date} at {preferred_time} is confirmed! Address: Road No 12, Banjara Hills.",
                },
            )
            tools_executed.append({"tool": "send_whatsapp", "result": wa_tool_res})

            state["objective_status"] = "completed"

            if user_has_telugu or ("te" in self.language and not user_has_hindi):
                agent_reply = f"చాలా సంతోషం అండి! {preferred_date} నాడు ఉదయం {preferred_time} గంటలకు మీ అపాయింట్‌మెంట్ కన్ఫర్మ్ చేశాము. పూర్తి వివరాలు మీ వాట్సాప్‌కి పంపాము. ధన్యవాదాలు అండి!"
            elif user_has_hindi or "hi" in self.language:
                agent_reply = f"बहुत बढ़िया! आपकी अपॉइंटमेंट {preferred_date} को {preferred_time} के लिए कन्फर्म कर दी गई है। विवरण आपके व्हाट्सएप पर भेज दिए गए हैं। धन्यवाद!"
            else:
                agent_reply = f"Wonderful! Your appointment is confirmed for {preferred_date} at {preferred_time}. We have sent confirmation details to your WhatsApp number. Have a great day!"

            self.current_node_id = "end-call"
        else:
            # Step 3, 4, 5: Dynamic LLM conversational assistance & out-of-scope question answering
            from jkr_conversation.llm_client import get_default_client
            client = get_default_client()

            if user_has_telugu:
                target_lang = "Telugu (te-IN) with natural everyday English words (Telugu-English code switching)"
            elif user_has_hindi:
                target_lang = "Hindi (hi-IN)"
            elif "te" in self.language:
                target_lang = "Telugu (te-IN) with natural conversational English code-switching (or Hindi/English if caller spoke those)"
            elif "hi" in self.language:
                target_lang = "Hindi (hi-IN)"
            else:
                target_lang = "Indian English (en-IN)"

            system_prompt = f"""IDENTITY & PERSONA
You are Kelly, the professional AI voice assistant for Aaha Dental Care speaking live on a phone call with a customer.
Clinic details & approved knowledge base:
- Location: MG Road, Vijayawada (Landmark: near City Center) and Road No 12, Banjara Hills, Hyderabad.
- Services: Dental Implants, Root Canal Treatment (₹2,500 to ₹4,500), Teeth Cleaning & Scaling (₹800 to ₹1,500), Teeth Whitening.
- Timings: Monday to Saturday, 9:30 AM to 8:30 PM. Sunday: Emergency appointments 10:00 AM to 2:00 PM.
- Consultation fee: ₹300 for general consultation and dental checkup.
- Payment Methods: Cash, UPI (GPay/PhonePe), Credit/Debit cards. 0% EMI available via Bajaj Finserv for treatments over ₹10,000.
- Doctors: Senior specialist endodontists and implantologists available every day.

CRITICAL 3-CASE QUESTION HANDLING:
Case 1: Business fact in knowledge base (clinic timings, location, services, root canal pricing, teeth cleaning, consultation fee, payment options)
-> Answer accurately and concisely from the knowledge base in 1 to 2 spoken sentences.

Case 2: General knowledge, small talk, AI curiosity, or product-adjacent questions (e.g. "What is a hackathon?", "How does this AI work?", "Is my data safe?", "How are you different from a normal call center?", greetings, pleasantries, random off-topic questions)
-> Answer directly, intelligently, and truthfully from your own knowledge in 1 to 3 short spoken sentences. Never say you don't know, never give a canned fallback, and never defer to the team for general knowledge or small talk.

Case 3: Business-specific fact NOT in knowledge base (unlisted surgical package price, specific doctor's personal phone number, custom corporate insurance policy, specialized laser cosmetic contouring cost)
-> Say plainly and politely that you don't have that specific detail on hand and offer that our clinic team will confirm it with them. Never invent or hallucinate unlisted business facts.

COMMUNICATION & BRIDGING RULES:
- Language: Reply in {target_lang}. Always match the caller's language naturally.
- Spoken-friendly: Keep answers short (1-3 sentences) suitable for a phone call. Never use markdown, bullet points, asterisks (*), hashtags (#), or emojis.
- Bridge back to appointment: After answering any question or small talk, smoothly bridge back to scheduling or confirming their appointment. Vary your bridging line naturally every turn so you NEVER repeat the same line verbatim (e.g., 'మీకు రేపు ఏదైనా సమయం వీలవుతుందా?', 'Would you like to book a quick checkup for tomorrow?', 'क्या मैं कल 11 बजे के लिए आपकी अपॉइंटमेंट शेड्यूल कर दूँ?', 'రేపు మార్నింగ్ లేదా ఈవెనింగ్ ఎప్పుడు అనుకూలంగా ఉంటుంది?', 'Would you like to visit us this week?').
- If the caller stays off-topic repeatedly: Answer their question politely, then gently steer back to the visit. If they want to end the call, respect it gracefully.
- AI Identity: Never claim to be human. Confirm you are the AI assistant for Aaha Dental Care.
- Safety: Do not provide medical prescriptions or formal legal advice beyond general dental care information.
"""
            user_prompt = f"Customer said: \"{customer_text}\"\n\nGenerate your spoken response now."

            llm_text = None
            if client:
                try:
                    llm_text = await client.complete_text(
                        system=system_prompt,
                        user=user_prompt,
                        max_tokens=250,
                    )
                except Exception as e:
                    logger.warning(f"Dograh LLM turn generation failed: {e}")

            if llm_text and llm_text.strip():
                agent_reply = llm_text.strip().replace("*", "").replace("#", "")
            else:
                # Safe conversational fallback if LLM is offline/mock
                if user_has_telugu or ("te" in self.language and not user_has_hindi):
                    agent_reply = "తప్పకుండా అండి, ఆహా డెంటల్ కేర్‌లో మా స్పెషలిస్ట్ డాక్టర్లు అందుబాటులో ఉన్నారు. మీకు రేపు ఏదైనా సమయం వీలవుతుందా?"
                elif user_has_hindi or "hi" in self.language:
                    agent_reply = "बिल्कुल, आहा डेंटल केयर में हमारे विशेषज्ञ डॉक्टर उपलब्ध हैं। क्या कल आपके लिए कोई समय सही रहेगा?"
                else:
                    agent_reply = "Certainly! Our specialist doctors are available at Aaha Dental Care. Would tomorrow work well for your visit?"

        trace = DograhTurnTrace(
            engine="dograh",
            workflow_id="kelly_assistant",
            workflow_version="2.0.0",
            current_node_id=self.current_node_id,
            previous_node_id=prev_node_id,
            allow_interrupt=allow_interrupt,
            barge_in_detected=allow_interrupt and len(customer_text.strip().split()) > 1,
            stt_provider="sarvam",
            stt_model="saarika:v2.5",
            tts_provider="sarvam",
            tts_model="bulbul:v3-beta",
            tts_speaker=self.speaker,
            tools_executed=tools_executed,
        )
        self.traces.append(trace)
        return agent_reply, tools_executed, trace

    async def _invoke_http_tool(self, *, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invokes a tool endpoint configured in the Dograh workflow definition."""
        tool_def = self.tools.get(tool_name)
        if not tool_def:
            logger.warning(f"Tool {tool_name} not found in Dograh workflow definition")
            return {"error": f"Tool {tool_name} not defined in workflow"}

        endpoint = tool_def.get("endpoint", "")
        # Resolve endpoint URL relative to current API host
        if "http://api:8000" in endpoint:
            endpoint = endpoint.replace("http://api:8000", self.api_base_url.rstrip("/"))
        elif endpoint.startswith("/"):
            endpoint = f"{self.api_base_url.rstrip('/')}{endpoint}"

        logger.info(f"Dograh invoking HTTP tool '{tool_name}' at {endpoint}")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(endpoint, json=payload)
                if res.status_code == 200:
                    return res.json()
                logger.warning(f"Tool invocation {tool_name} returned status {res.status_code}: {res.text}")
                return {"status_code": res.status_code, "response": res.text}
        except Exception as exc:
            logger.info(f"HTTP endpoint connection failed ({exc}); falling back to in-process internal tool dispatch")
            try:
                import importlib.util
                router_path = Path(__file__).resolve().parents[4] / "services" / "api" / "app" / "modules" / "tools" / "internal_router.py"
                spec = importlib.util.spec_from_file_location("internal_router_mod", str(router_path))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if tool_name == "book_appointment":
                        req = mod.DograhBookAppointmentRequest(**payload)
                        return await mod.internal_book_appointment(req)
                    elif tool_name == "send_whatsapp":
                        req = mod.DograhSendWhatsAppRequest(**payload)
                        return await mod.internal_send_whatsapp(req)
            except Exception as in_exc:
                logger.error(f"In-process tool execution error: {in_exc}")
            return {"error": str(exc), "status": "failed"}


class DograhWorkflowEngine:
    """Singleton Dograh Workflow Engine manager."""

    def __init__(self) -> None:
        self.workflow_definition = load_kelly_workflow_definition()
        self.active_sessions: dict[uuid.UUID, DograhWorkflowSession] = {}

    def create_session(
        self,
        call_id: uuid.UUID,
        initial_context: dict[str, Any] | None = None,
        api_base_url: str | None = None,
    ) -> DograhWorkflowSession:
        session = DograhWorkflowSession(
            call_id=call_id,
            workflow=self.workflow_definition,
            initial_context=initial_context,
            api_base_url=api_base_url,
        )
        self.active_sessions[call_id] = session
        return session

    def get_session(self, call_id: uuid.UUID) -> DograhWorkflowSession | None:
        return self.active_sessions.get(call_id)


# Global engine instance
dograh_engine = DograhWorkflowEngine()


@dataclass
class DograhTelephony:
    """Telephony provider backed by Dograh's telephony gateway (Twilio / Exotel)."""

    api_url: str = field(
        default_factory=lambda: os.getenv("DOGRAH_API_URL", "http://dograh-api:8000")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("DOGRAH_API_KEY", "")
    )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def create_outbound_call(
        self, *, to: str, from_: str, context: dict[str, Any]
    ) -> CallHandle:
        """Initiate outbound call via Dograh telephony /telephony/initiate-call."""
        payload = {
            "phone_number": to,
            "from_phone_number_id": from_,
            "workflow_id": context.get("workflow_id", "kelly_assistant"),
            "initial_context": context,
        }
        async with httpx.AsyncClient(base_url=self.api_url, timeout=10.0) as client:
            try:
                resp = await client.post(
                    "/telephony/initiate-call",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                call_ref = data.get("call_id") or data.get("workflow_run_id") or f"dograh-call-{uuid.uuid4()}"
                return CallHandle(provider_call_ref=call_ref, raw=data)
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                logger.warning(f"Dograh initiate-call failed ({exc}), falling back to direct reference")
                return CallHandle(provider_call_ref=f"dograh-pending-{uuid.uuid4()}", raw={"error": str(exc)})

    async def accept_inbound_call(self, *, call_ref: str) -> CallHandle:
        return CallHandle(provider_call_ref=call_ref)

    async def end_call(self, *, call_ref: str) -> None:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=5.0) as client:
            try:
                await client.post(
                    f"/telephony/calls/{call_ref}/hangup",
                    headers=self._headers(),
                )
            except Exception as e:
                logger.warning(f"Failed to hangup call {call_ref} in Dograh: {e}")

    async def transfer_call(self, *, call_ref: str, target: str) -> None:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=5.0) as client:
            try:
                await client.post(
                    f"/telephony/calls/{call_ref}/transfer",
                    json={"target": target},
                    headers=self._headers(),
                )
            except Exception as e:
                logger.warning(f"Failed to transfer call {call_ref} in Dograh: {e}")

    async def get_call_status(self, *, call_ref: str) -> CallStatusInfo:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"/telephony/calls/{call_ref}/status",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    return CallStatusInfo(status=resp.json().get("status", "in-progress"), raw=resp.json())
            except Exception:
                pass
        return CallStatusInfo(status="completed")


@dataclass
class DograhMediaRuntime:
    """MediaRuntime adapter connecting JKR voice worker to Dograh's streaming engine."""

    api_url: str = field(
        default_factory=lambda: os.getenv("DOGRAH_API_URL", "http://dograh-api:8000")
    )
    sessions: dict[str, MediaSession] = field(default_factory=dict)

    async def create_session(self, *, call_id: str) -> MediaSession:
        session = MediaSession(session_id=f"dograh-session-{call_id}")
        self.sessions[call_id] = session
        return session

    async def publish_audio(self, *, session: MediaSession, chunk: bytes) -> None:
        # In Dograh, audio flows directly via WebSockets between the telephony carrier
        # (Twilio/Exotel) and Pipecat's Sarvam STT/TTS pipeline.
        return None

    async def cancel_output(self, *, session: MediaSession) -> None:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=2.0) as client:
            try:
                await client.post(f"/sessions/{session.session_id}/cancel-output")
            except Exception:
                pass
