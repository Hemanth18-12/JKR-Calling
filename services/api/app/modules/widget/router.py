from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from jkr_conversation.engine import process_turn
from jkr_conversation.schemas import ConversationPolicySnapshot
from jkr_conversation.state import new_conversation_state
from jkr_db.models.agents import Agent, AgentVersion, ConversationPolicy, VoicePersona
from jkr_db.models.calls import CallEvent, CallParticipant, CallSession, CallTranscript, CallTurn
from jkr_db.models.coins import CoinTransaction, CoinWallet
from jkr_db.models.contacts import Contact
from jkr_db.models.tenancy import Workspace
from jkr_db.session import get_engine, workspace_scoped_session
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.modules.live_call.service import _sarvam_language_code, _speak

logger = logging.getLogger("jkr_api.widget")

router = APIRouter(prefix="/widget", tags=["widget"])


class WidgetConfigResponse(BaseModel):
    agent_id: str
    name: str
    business_identity: str
    primary_language: str
    supported_languages: list[str]
    greeting_text: str
    primary_objective: str
    theme_color: str = "#4f46e5"
    position: str = "bottom-right"
    launcher_text: str = "Talk to AI Assistant"
    allow_voice: bool = True


class StartWidgetSessionRequest(BaseModel):
    agent_id: uuid.UUID
    visitor_name: str | None = "Website Visitor"
    visitor_phone: str | None = None
    language: str | None = None


class StartWidgetSessionResponse(BaseModel):
    session_id: str
    agent_name: str
    business_identity: str
    greeting: str
    language: str
    theme_color: str = "#4f46e5"


class WidgetMessageRequest(BaseModel):
    message: str
    language: str | None = None


class WidgetMessageResponse(BaseModel):
    reply_text: str
    audio_url: str | None = None
    turn_ref: str
    session_status: str = "in_progress"
    appointment_booked: bool = False
    tools_executed: list[str] = []


@router.get("/config/{agent_id}", response_model=WidgetConfigResponse)
async def get_widget_config(agent_id: uuid.UUID) -> WidgetConfigResponse:
    """Public endpoint to fetch widget configuration for embedding on any site."""
    engine = get_engine()
    async with AsyncSession(engine) as session:
        res = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = res.scalar_one_or_none()
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

        version = None
        if agent.published_version_id:
            vres = await session.execute(select(AgentVersion).where(AgentVersion.id == agent.published_version_id))
            version = vres.scalar_one_or_none()

        biz_name = (agent.business_identity or "").strip() or "Aaha Dental Care"
        greeting = (version.greeting_text if version else "నమస్కారం! నేను ఏఐ అసిస్టెంట్‌ని. మీకు ఎలా సహాయపడగలను?")
        greeting = greeting.replace("{business}", biz_name).replace("{business_identity}", biz_name)

        return WidgetConfigResponse(
            agent_id=str(agent.id),
            name=agent.name,
            business_identity=biz_name,
            primary_language=agent.primary_language or "te-IN",
            supported_languages=["te-IN", "hi-IN", "en-IN"],
            greeting_text=greeting,
            primary_objective=version.primary_objective if version else "book_appointment",
            theme_color="#4f46e5",
            position="bottom-right",
            launcher_text=f"Chat with {agent.name}",
            allow_voice=True,
        )


@router.post("/session", response_model=StartWidgetSessionResponse)
async def start_widget_session(
    payload: StartWidgetSessionRequest,
    settings: Settings = Depends(get_settings),
) -> StartWidgetSessionResponse:
    """Public endpoint: Starts an interactive in-browser voice/chat session with coin wallet metering."""
    engine = get_engine()
    async with AsyncSession(engine) as session:
        res = await session.execute(select(Agent).where(Agent.id == payload.agent_id))
        agent = res.scalar_one_or_none()
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

        workspace_id = agent.workspace_id

        # 1. Billing verification: Check coin wallet balance
        wallet_res = await session.execute(select(CoinWallet).where(CoinWallet.workspace_id == workspace_id))
        wallet = wallet_res.scalar_one_or_none()
        if wallet and wallet.balance_coins <= 0:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                "Insufficient coins in workspace wallet. Please recharge wallet to start AI sessions.",
            )

        vres = await session.execute(select(AgentVersion).where(AgentVersion.id == agent.published_version_id))
        version = vres.scalar_one_or_none()

    language_code = _sarvam_language_code(payload.language or agent.primary_language)
    biz_name = (agent.business_identity or "").strip() or "Aaha Dental Care"

    conversation_state = new_conversation_state(
        objective=version.primary_objective if version else "book_appointment",
        language=language_code,
    )
    conversation_state["web_widget_session"] = True
    conversation_state["business_identity"] = biz_name
    conversation_state["customer_name"] = payload.visitor_name or "Website Visitor"
    conversation_state["customer_phone"] = payload.visitor_phone or "+919876543210"

    greeting_text = (version.greeting_text if version else "నమస్కారం! నేను ఆహా డెంటల్ కేర్ నుండి ఏఐ అసిస్టెంట్‌ని. మీకు ఎలా సహాయపడగలను?")
    greeting_text = greeting_text.replace("{business}", biz_name).replace("{business_identity}", biz_name).strip()

    async with workspace_scoped_session(workspace_id) as write_db:
        # Create or find contact
        contact_id = None
        if payload.visitor_phone:
            c_res = await write_db.execute(
                select(Contact).where(Contact.workspace_id == workspace_id, Contact.phone_e164 == payload.visitor_phone)
            )
            contact = c_res.scalar_one_or_none()
            if not contact:
                contact = Contact(
                    workspace_id=workspace_id,
                    full_name=payload.visitor_name or "Website Visitor",
                    phone_e164=payload.visitor_phone,
                )
                write_db.add(contact)
                await write_db.flush()
            contact_id = contact.id

        # Create CallSession
        call_session = CallSession(
            workspace_id=workspace_id,
            direction="inbound",
            status="in_progress",
            agent_id=agent.id,
            agent_version_id=version.id if version else None,
            contact_id=contact_id,
            idempotency_key=f"widget-{uuid.uuid4()}",
            language=language_code,
            state=conversation_state,
            started_at=datetime.now(UTC),
            answered_at=None,
            is_mock=False,
            disclosure_confirmed=True,
        )
        write_db.add(call_session)
        await write_db.flush()
        session_id = call_session.id

        # Initial Agent Greeting Turn
        write_db.add(
            CallTurn(
                workspace_id=workspace_id,
                call_session_id=session_id,
                turn_ref="turn-0",
                sequence_index=0,
                speaker="agent",
                text=greeting_text,
                language=language_code,
                is_interrupted=False,
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
            )
        )
        write_db.add(
            CallEvent(
                workspace_id=workspace_id,
                call_session_id=session_id,
                event_type="call_started",
                payload={"web_widget": True, "agent_name": agent.name},
            )
        )
        await write_db.flush()

    return StartWidgetSessionResponse(
        session_id=str(session_id),
        agent_name=agent.name,
        business_identity=biz_name,
        greeting=greeting_text,
        language=language_code,
        theme_color="#4f46e5",
    )


@router.post("/session/{session_id}/message", response_model=WidgetMessageResponse)
async def send_widget_message(
    session_id: uuid.UUID,
    payload: WidgetMessageRequest,
    settings: Settings = Depends(get_settings),
) -> WidgetMessageResponse:
    """Processes a user message from the embeddable widget, meters coins, returns reply and audio."""
    from jkr_messaging import get_redis

    engine = get_engine()
    async with AsyncSession(engine) as session:
        res = await session.execute(select(CallSession).where(CallSession.id == session_id))
        call_sess = res.scalar_one_or_none()
        if not call_sess:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget session not found")
        workspace_id = call_sess.workspace_id
        agent_id = call_sess.agent_id

    # Verify wallet has coins to continue
    async with workspace_scoped_session(workspace_id) as write_db:
        w_res = await write_db.execute(select(CoinWallet).where(CoinWallet.workspace_id == workspace_id))
        wallet = w_res.scalar_one_or_none()
        if wallet is not None and wallet.balance_coins <= 0:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                "Your coin balance is 0. Please top up your wallet to continue interacting with this agent.",
            )

    # Load session and turns
    async with workspace_scoped_session(workspace_id) as write_db:
        res = await write_db.execute(select(CallSession).where(CallSession.id == session_id))
        call_sess = res.scalar_one()
        now = datetime.now(UTC)
        if call_sess.answered_at is None:
            call_sess.answered_at = now

        t_res = await write_db.execute(
            select(CallTurn).where(CallTurn.call_session_id == session_id).order_by(CallTurn.sequence_index)
        )
        turns = list(t_res.scalars().all())
        sequence_index = len(turns)

        now = datetime.now(UTC)
        user_turn_ref = f"turn-{sequence_index}"
        write_db.add(
            CallTurn(
                workspace_id=workspace_id,
                call_session_id=session_id,
                turn_ref=user_turn_ref,
                sequence_index=sequence_index,
                speaker="customer",
                text=payload.message,
                language=call_sess.language,
                is_interrupted=False,
                started_at=now,
                ended_at=now,
            )
        )
        await write_db.flush()

        # Load conversation policy if exists
        policy_res = await write_db.execute(
            select(ConversationPolicy).where(ConversationPolicy.workspace_id == workspace_id)
        )
        policy_row = policy_res.scalars().first()
        policy_snapshot = (
            ConversationPolicySnapshot(
                max_response_sentences=policy_row.max_response_sentences,
                human_transfer_enabled=policy_row.human_transfer_enabled,
                do_not_call_behavior=policy_row.do_not_call_behavior,
                wrong_number_behavior=policy_row.wrong_number_behavior,
                clarification_behavior=policy_row.clarification_behavior,
                confirmation_behavior=policy_row.confirmation_behavior,
            )
            if policy_row
            else ConversationPolicySnapshot()
        )

        state = dict(call_sess.state or {})
        recent_turns = [
            {"speaker": t.speaker, "text": t.text}
            for t in turns[-6:]
        ]
        recent_turns.append({"speaker": "customer", "text": payload.message})

        result = await process_turn(
            write_db,
            workspace_id=workspace_id,
            call_session_id=session_id,
            state=state,
            customer_utterance=payload.message,
            conversation_policy=policy_snapshot,
            agent_id=agent_id,
            business_identity=state.get("business_identity", "Aaha Dental Care"),
            recent_turns=recent_turns,
            engine_mode=settings.conversation_engine_mode,
            response_mode=settings.llm_response_mode,
        )

        reply_text = result.reply_text
        tools_executed_names = [t.tool_name for t in result.tool_calls_requested]
        appointment_booked = "book_appointment" in tools_executed_names

        # Execute tools if requested
        for tool_call in result.tool_calls_requested:
            try:
                from jkr_db.tools_engine import execute_tool
                await execute_tool(
                    write_db,
                    workspace_id=workspace_id,
                    tool_name=tool_call.tool_name,
                    tool_input=tool_call.tool_input,
                    idempotency_key=f"widget-{session_id}-{tool_call.idempotency_suffix}",
                    call_session_id=session_id,
                    contact_id=call_sess.contact_id,
                    agent_version_id=call_sess.agent_version_id,
                )
            except Exception as t_err:
                logger.warning(f"Widget tool execution error: {t_err}")

        agent_turn_ref = f"turn-{sequence_index + 1}"
        write_db.add(
            CallTurn(
                workspace_id=workspace_id,
                call_session_id=session_id,
                turn_ref=agent_turn_ref,
                sequence_index=sequence_index + 1,
                speaker="agent",
                text=reply_text,
                language=call_sess.language,
                is_interrupted=False,
                started_at=now,
                ended_at=now,
            )
        )

        call_sess.state = result.state
        if result.call_should_end:
            call_sess.status = "completed"
            call_sess.ended_at = now
        await write_db.flush()

    # Generate Sarvam TTS Audio for spoken playback in widget
    audio_url = None
    try:
        kind, play_target = await _speak(
            reply_text,
            language_code=call_sess.language or "te-IN",
            settings=settings,
            redis=get_redis(),
            speaker="kavitha" if "te" in (call_sess.language or "") else "shubh",
        )
        if kind == "play":
            audio_url = play_target
    except Exception as exc:
        logger.warning(f"Could not synthesize widget audio: {exc}")

    return WidgetMessageResponse(
        reply_text=reply_text,
        audio_url=audio_url,
        turn_ref=agent_turn_ref,
        session_status=call_sess.status,
        appointment_booked=appointment_booked,
        tools_executed=tools_executed_names,
    )


@router.post("/session/{session_id}/end")
async def end_widget_session(session_id: uuid.UUID) -> dict[str, Any]:
    """Ends the widget session and persists final transcript."""
    engine = get_engine()
    async with AsyncSession(engine) as session:
        res = await session.execute(select(CallSession).where(CallSession.id == session_id))
        call_sess = res.scalar_one_or_none()
        if not call_sess:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget session not found")
        workspace_id = call_sess.workspace_id

    async with workspace_scoped_session(workspace_id) as write_db:
        res = await write_db.execute(select(CallSession).where(CallSession.id == session_id))
        call_sess = res.scalar_one()

        t_res = await write_db.execute(
            select(CallTurn).where(CallTurn.call_session_id == session_id).order_by(CallTurn.sequence_index)
        )
        turns = list(t_res.scalars().all())
        full_text = "\n".join(f"[{t.speaker.upper()}]: {t.text}" for t in turns)

        call_sess.status = "completed"
        now = datetime.now(UTC)
        call_sess.ended_at = now
        had_exchange = len(turns) > 1  # At least greeting + 1 visitor turn
        if not had_exchange or call_sess.answered_at is None:
            call_sess.duration_seconds = 0
        else:
            call_sess.duration_seconds = max(0, int((now - call_sess.answered_at).total_seconds()))

        write_db.add(
            CallTranscript(
                workspace_id=workspace_id,
                call_session_id=session_id,
                full_text=full_text,
                language=call_sess.language,
                is_final=True,
            )
        )

        if call_sess.duration_seconds > 0:
            from app.modules.coins.service import deduct_call_coins
            await deduct_call_coins(
                write_db,
                workspace_id=workspace_id,
                call_id=session_id,
                duration_seconds=call_sess.duration_seconds,
            )

        await write_db.flush()

    return {"status": "completed", "session_id": str(session_id), "duration_seconds": call_sess.duration_seconds}


class CheckInstallRequest(BaseModel):
    url: str


class CheckInstallResponse(BaseModel):
    installed: bool
    url: str
    message: str
    details: dict[str, Any] = {}


@router.post("/check-install", response_model=CheckInstallResponse)
async def check_widget_installed(payload: CheckInstallRequest) -> CheckInstallResponse:
    """Verifies whether the embed snippet is present on a given target URL."""
    import httpx

    target_url = payload.url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"

    try:
        async with httpx.AsyncClient(
            timeout=8.0, follow_redirects=True, headers={"User-Agent": "JKR-Widget-Checker/1.0"}
        ) as client:
            resp = await client.get(target_url)
            html = resp.text

            if "jkr-widget.js" in html:
                return CheckInstallResponse(
                    installed=True,
                    url=target_url,
                    message="Widget script successfully detected on your website!",
                    details={"status_code": resp.status_code, "has_script": True},
                )
            else:
                return CheckInstallResponse(
                    installed=False,
                    url=target_url,
                    message="Widget script was not found in the HTML of this page. Ensure you pasted the script tag right before the closing </body> tag.",
                    details={"status_code": resp.status_code, "has_script": False},
                )
    except Exception as exc:
        return CheckInstallResponse(
            installed=False,
            url=target_url,
            message=f"Could not reach {target_url}: {str(exc)}",
            details={"error": str(exc)},
        )
