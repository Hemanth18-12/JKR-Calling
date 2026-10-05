"""Pytest suite verifying Dograh workflow engine migration."""

import uuid
import pytest
from app.providers.dograh import dograh_engine, load_kelly_workflow_definition


def test_dograh_workflow_schema():
    wf = load_kelly_workflow_definition()
    assert wf["name"] == "Kelly Assistant (Multilingual te-IN/hi-IN/en-IN)"
    assert wf["stt"]["provider"] == "sarvam"
    assert wf["stt"]["model"] == "saarika:v2.5"
    assert wf["tts"]["provider"] == "sarvam"
    assert wf["tts"]["model"] == "bulbul:v3-beta"
    assert "te-IN" in wf["tts"]["language_speakers"]
    
    nodes = {n["id"]: n for n in wf["workflow_definition"]["nodes"]}
    assert "start-call" in nodes
    assert "agent-conversation" in nodes
    assert "end-call" in nodes
    assert nodes["start-call"]["data"]["allow_interrupt"] is True
    assert nodes["agent-conversation"]["data"]["allow_interrupt"] is True

    tools = {t["id"]: t for t in wf["workflow_definition"]["tools"]}
    assert "book_appointment" in tools
    assert "send_whatsapp" in tools


@pytest.mark.asyncio
async def test_dograh_session_turn_and_tool_execution():
    call_id = uuid.uuid4()
    context = {
        "contact_name": "Suresh Babu",
        "phone_number": "+919876543210",
        "language": "te-IN",
        "business_identity": "Aaha Dental Care",
    }
    session = dograh_engine.create_session(call_id, initial_context=context)
    
    # 1. StartCall greeting
    greeting = session.get_greeting()
    assert "ఆహా డెంటల్ కేర్" in greeting
    
    # 2. Interruption / Barge-in check
    interruption = session.handle_user_utterance("ఆగండి, నాకు ఒక డౌట్ ఉంది")
    assert interruption.classification.value == "meaningful"
    assert interruption.stop_latency_ms == 120

    # 3. User turn triggering booking
    state = {"recent_turns": [{"speaker": "agent", "text": greeting}]}
    reply, tools_run, trace = await session.execute_turn(
        customer_text="రేపు ఉదయం 11 గంటలకు అపాయింట్‌మెంట్ బుక్ చేయండి",
        state=state,
    )
    
    assert trace.engine == "dograh"
    assert trace.workflow_id == "kelly_assistant"
    assert trace.current_node_id == "end-call"
    assert len(tools_run) == 2
    assert tools_run[0]["tool"] == "book_appointment"
    assert tools_run[0]["result"]["success"] is True
    assert tools_run[1]["tool"] == "send_whatsapp"
    assert tools_run[1]["result"]["success"] is True
    assert "అపాయింట్‌మెంట్ కన్ఫర్మ్ చేశాము" in reply


@pytest.mark.asyncio
async def test_dograh_session_decline_graceful_close():
    call_id = uuid.uuid4()
    context = {
        "contact_name": "Sunil",
        "phone_number": "+919876543210",
        "language": "te-IN",
        "business_identity": "Aaha Dental Care",
    }
    session = dograh_engine.create_session(call_id, initial_context=context)
    
    state = {"recent_turns": []}
    reply, tools_run, trace = await session.execute_turn(
        customer_text="నాకు వద్దు అండి, ఇంట్రెస్ట్ లేదు",
        state=state,
    )
    
    assert trace.engine == "dograh"
    assert trace.current_node_id == "end-call"
    assert len(tools_run) == 0  # No tools triggered on decline
    assert "ధన్యవాదాలు" in reply
