from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.tools import service
from app.modules.tools.schemas import (
    AgentToolOut,
    AgentToolUpdate,
    ToolDefinitionOut,
    ToolDefinitionUpdate,
    ToolExecutionOut,
)

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolDefinitionOut])
async def list_definitions(
    auth: AuthContext = Depends(require_permission("tools:view")),
    db: AsyncSession = Depends(workspace_db_for("tools:view")),
) -> list[ToolDefinitionOut]:
    return await service.list_definitions(db, workspace_id=auth.workspace_id)


@router.patch("/{definition_id}", response_model=ToolDefinitionOut)
async def set_definition_enabled(
    definition_id: uuid.UUID,
    payload: ToolDefinitionUpdate,
    auth: AuthContext = Depends(require_permission("tools:edit")),
    db: AsyncSession = Depends(workspace_db_for("tools:edit")),
) -> ToolDefinitionOut:
    return await service.set_definition_enabled(db, workspace_id=auth.workspace_id, definition_id=definition_id, is_enabled=payload.is_enabled)


@router.get("/agent-versions/{agent_version_id}", response_model=list[AgentToolOut])
async def list_agent_tools(
    agent_version_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("tools:view")),
    db: AsyncSession = Depends(workspace_db_for("tools:view")),
) -> list[AgentToolOut]:
    return await service.list_agent_tools(db, workspace_id=auth.workspace_id, agent_version_id=agent_version_id)


@router.patch("/agent-versions/{agent_version_id}/{tool_definition_id}", response_model=AgentToolOut)
async def set_agent_tool_enabled(
    agent_version_id: uuid.UUID,
    tool_definition_id: uuid.UUID,
    payload: AgentToolUpdate,
    auth: AuthContext = Depends(require_permission("tools:edit")),
    db: AsyncSession = Depends(workspace_db_for("tools:edit")),
) -> AgentToolOut:
    agent_tool = await service.set_agent_tool_enabled(
        db, workspace_id=auth.workspace_id, agent_version_id=agent_version_id,
        tool_definition_id=tool_definition_id, enabled=payload.enabled,
    )
    definitions = await service.list_definitions(db, workspace_id=auth.workspace_id)
    definition = next(d for d in definitions if d.id == tool_definition_id)
    return AgentToolOut(tool_definition_id=agent_tool.tool_definition_id, name=definition.name, description=definition.description, enabled=agent_tool.enabled)


@router.get("/executions/by-call/{call_session_id}", response_model=list[ToolExecutionOut])
async def list_executions_for_call(
    call_session_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("tools:view_audit")),
    db: AsyncSession = Depends(workspace_db_for("tools:view_audit")),
) -> list[ToolExecutionOut]:
    return await service.list_executions_for_call(db, workspace_id=auth.workspace_id, call_session_id=call_session_id)
