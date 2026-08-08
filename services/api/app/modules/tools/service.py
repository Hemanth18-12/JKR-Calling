"""Tool definition catalog + per-agent-version enablement. Actual tool
*execution* happens in `jkr_db.tools_engine` from within a live call
(services/voice-worker) or the post-call follow-up dispatcher
(services/intelligence-worker) — this module only manages which tools exist
and are switched on, plus read access to the resulting audit trail."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from jkr_db.models.agents import AgentTool, ToolDefinition
from jkr_db.models.tools import ToolExecution
from jkr_db.tools_engine import REAL_SIDE_EFFECT_TOOLS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tools.schemas import AgentToolOut, ToolDefinitionOut, ToolExecutionOut

# (name, description, required_permission, timeout_seconds, confirmation_required)
# required_permission documents which workspace permission a human reviewing
# this tool's use should hold — spec §17. confirmation_required flags tools
# that commit the business to something (booking/cancelling) vs. read-only
# or purely informational ones.
TOOL_CATALOG: list[tuple[str, str, str, int, bool]] = [
    ("check_calendar_slots", "Look up available appointment slots", "tools:view", 5, False),
    ("book_appointment", "Book a new appointment for the contact", "contacts:edit", 10, True),
    ("reschedule_appointment", "Move an existing appointment to a new time", "contacts:edit", 10, True),
    ("cancel_appointment", "Cancel an existing appointment", "contacts:edit", 10, True),
    ("create_crm_lead", "Create a lead record in the connected CRM", "contacts:edit", 10, False),
    ("update_crm_stage", "Move a CRM lead to a new pipeline stage", "contacts:edit", 10, False),
    ("create_human_callback", "Hand off to a human team member", "calls:transfer", 10, False),
    ("send_whatsapp", "Send a WhatsApp message to the contact", "contacts:edit", 10, False),
    ("send_sms", "Send an SMS to the contact", "contacts:edit", 10, False),
    ("send_email", "Send an email to the contact", "contacts:edit", 10, False),
]


async def seed_default_tool_definitions(db: AsyncSession, *, workspace_id: uuid.UUID) -> None:
    """Every workspace gets the full tool catalog, enabled by default —
    mirrors `providers_service.seed_default_accounts`. Called once at
    workspace creation."""
    for name, description, required_permission, timeout_seconds, confirmation_required in TOOL_CATALOG:
        db.add(
            ToolDefinition(
                workspace_id=workspace_id, name=name, description=description,
                required_permission=required_permission, timeout_seconds=timeout_seconds,
                confirmation_required=confirmation_required, is_enabled=True,
            )
        )
    await db.flush()


def _out(definition: ToolDefinition) -> ToolDefinitionOut:
    return ToolDefinitionOut(
        id=definition.id, name=definition.name, description=definition.description,
        required_permission=definition.required_permission, timeout_seconds=definition.timeout_seconds,
        confirmation_required=definition.confirmation_required, is_enabled=definition.is_enabled,
        has_real_side_effect=definition.name in REAL_SIDE_EFFECT_TOOLS,
    )


async def list_definitions(db: AsyncSession, *, workspace_id: uuid.UUID):
    result = await db.execute(select(ToolDefinition).where(ToolDefinition.workspace_id == workspace_id).order_by(ToolDefinition.name))
    return [_out(d) for d in result.scalars().all()]


async def set_definition_enabled(db: AsyncSession, *, workspace_id: uuid.UUID, definition_id: uuid.UUID, is_enabled: bool):
    result = await db.execute(select(ToolDefinition).where(ToolDefinition.id == definition_id, ToolDefinition.workspace_id == workspace_id))
    definition = result.scalar_one_or_none()
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tool definition not found")
    definition.is_enabled = is_enabled
    await db.flush()
    return _out(definition)


async def seed_default_agent_tools(db: AsyncSession, *, workspace_id: uuid.UUID, agent_version_id: uuid.UUID) -> None:
    """Every new agent version starts with every workspace tool enabled —
    called from `agents.service.create_agent`/`create_version`. Without this,
    a fresh version has no `AgentTool` rows at all and `list_agent_tools`
    defaults every tool to disabled, which would silently break the spec §33
    demo flow's book_appointment beat on any newly created agent."""
    definitions_result = await db.execute(select(ToolDefinition.id).where(ToolDefinition.workspace_id == workspace_id))
    for definition_id in definitions_result.scalars().all():
        db.add(AgentTool(workspace_id=workspace_id, agent_version_id=agent_version_id, tool_definition_id=definition_id, enabled=True))
    await db.flush()


async def list_agent_tools(db: AsyncSession, *, workspace_id: uuid.UUID, agent_version_id: uuid.UUID):
    definitions_result = await db.execute(select(ToolDefinition).where(ToolDefinition.workspace_id == workspace_id).order_by(ToolDefinition.name))
    definitions = list(definitions_result.scalars().all())

    agent_tools_result = await db.execute(
        select(AgentTool).where(AgentTool.workspace_id == workspace_id, AgentTool.agent_version_id == agent_version_id)
    )
    enabled_by_definition_id = {at.tool_definition_id: at.enabled for at in agent_tools_result.scalars().all()}

    return [
        AgentToolOut(
            tool_definition_id=d.id, name=d.name, description=d.description,
            enabled=enabled_by_definition_id.get(d.id, False),
        )
        for d in definitions
    ]


async def set_agent_tool_enabled(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_version_id: uuid.UUID, tool_definition_id: uuid.UUID, enabled: bool
):
    result = await db.execute(
        select(AgentTool).where(
            AgentTool.workspace_id == workspace_id, AgentTool.agent_version_id == agent_version_id,
            AgentTool.tool_definition_id == tool_definition_id,
        )
    )
    agent_tool = result.scalar_one_or_none()
    if agent_tool is None:
        agent_tool = AgentTool(
            workspace_id=workspace_id, agent_version_id=agent_version_id, tool_definition_id=tool_definition_id, enabled=enabled,
        )
        db.add(agent_tool)
    else:
        agent_tool.enabled = enabled
    await db.flush()
    return agent_tool


async def list_executions_for_call(db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID):
    result = await db.execute(
        select(ToolExecution, ToolDefinition.name)
        .join(ToolDefinition, ToolDefinition.id == ToolExecution.tool_definition_id)
        .where(ToolExecution.workspace_id == workspace_id, ToolExecution.call_session_id == call_session_id)
        .order_by(ToolExecution.started_at)
    )
    return [
        ToolExecutionOut(
            id=e.id, tool_definition_id=e.tool_definition_id, tool_name=name, status=e.status, input=e.input,
            output=e.output, error=e.error, started_at=e.started_at, completed_at=e.completed_at,
        )
        for e, name in result.all()
    ]
