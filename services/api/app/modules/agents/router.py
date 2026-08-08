from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.agents import service
from app.modules.agents.persona_templates import TEMPLATES
from app.modules.agents.schemas import (
    AgentCreate,
    AgentDetail,
    AgentOut,
    AgentUpdate,
    AgentVersionDetail,
    AgentVersionOut,
    AgentVersionUpdate,
    ConversationPolicyOut,
    ConversationPolicyUpdate,
    PersonaTemplateOut,
    PronunciationEntryCreate,
    PronunciationEntryOut,
    VoicePersonaOut,
    VoicePersonaUpdate,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/persona-templates", response_model=list[PersonaTemplateOut])
async def get_persona_templates(_auth=Depends(require_permission("agents:view"))) -> list[PersonaTemplateOut]:
    return [PersonaTemplateOut(key=key, label=t["label"]) for key, t in TEMPLATES.items()]


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: AgentCreate,
    auth: AuthContext = Depends(require_permission("agents:create")),
    db: AsyncSession = Depends(workspace_db_for("agents:create")),
) -> AgentOut:
    agent = await service.create_agent(
        db,
        workspace_id=auth.workspace_id,
        created_by=auth.user.id,
        name=payload.name,
        business_identity=payload.business_identity,
        description=payload.description,
        primary_language=payload.primary_language,
        persona_template=payload.persona_template,
    )
    return AgentOut.model_validate(agent)


@router.get("", response_model=list[AgentOut])
async def list_agents(
    auth: AuthContext = Depends(require_permission("agents:view")),
    db: AsyncSession = Depends(workspace_db_for("agents:view")),
) -> list[AgentOut]:
    agents = await service.list_agents(db, workspace_id=auth.workspace_id)
    return [AgentOut.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("agents:view")),
    db: AsyncSession = Depends(workspace_db_for("agents:view")),
) -> AgentDetail:
    agent, versions = await service.get_agent_with_versions(db, workspace_id=auth.workspace_id, agent_id=agent_id)
    return AgentDetail(**AgentOut.model_validate(agent).model_dump(), versions=[AgentVersionOut.model_validate(v) for v in versions])


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> AgentOut:
    agent = await service.update_agent(db, workspace_id=auth.workspace_id, agent_id=agent_id, **payload.model_dump(exclude_unset=True))
    return AgentOut.model_validate(agent)


@router.post("/{agent_id}/versions", response_model=AgentVersionOut, status_code=201)
async def create_version(
    agent_id: uuid.UUID,
    clone_from_version_id: uuid.UUID | None = None,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> AgentVersionOut:
    version = await service.create_version(
        db, workspace_id=auth.workspace_id, agent_id=agent_id, clone_from_version_id=clone_from_version_id
    )
    return AgentVersionOut.model_validate(version)


@router.get("/{agent_id}/versions/{version_id}", response_model=AgentVersionDetail)
async def get_version(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("agents:view")),
    db: AsyncSession = Depends(workspace_db_for("agents:view")),
) -> AgentVersionDetail:
    version, voice, policy, pronunciation = await service.get_version_detail(
        db, workspace_id=auth.workspace_id, agent_id=agent_id, version_id=version_id
    )
    return AgentVersionDetail(
        **AgentVersionOut.model_validate(version).model_dump(),
        voice_persona=VoicePersonaOut.model_validate(voice) if voice else None,
        conversation_policy=ConversationPolicyOut.model_validate(policy) if policy else None,
        pronunciation_entries=[PronunciationEntryOut.model_validate(p) for p in pronunciation],
    )


@router.patch("/{agent_id}/versions/{version_id}", response_model=AgentVersionOut)
async def update_version(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AgentVersionUpdate,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> AgentVersionOut:
    version = await service.update_version(
        db, workspace_id=auth.workspace_id, agent_id=agent_id, version_id=version_id, **payload.model_dump(exclude_unset=True)
    )
    return AgentVersionOut.model_validate(version)


@router.patch("/{agent_id}/versions/{version_id}/voice", response_model=VoicePersonaOut)
async def update_voice(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: VoicePersonaUpdate,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> VoicePersonaOut:
    voice = await service.update_voice_persona(
        db, workspace_id=auth.workspace_id, agent_id=agent_id, version_id=version_id, **payload.model_dump(exclude_unset=True)
    )
    return VoicePersonaOut.model_validate(voice)


@router.patch("/{agent_id}/versions/{version_id}/policy", response_model=ConversationPolicyOut)
async def update_policy(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: ConversationPolicyUpdate,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> ConversationPolicyOut:
    policy = await service.update_conversation_policy(
        db, workspace_id=auth.workspace_id, agent_id=agent_id, version_id=version_id, **payload.model_dump(exclude_unset=True)
    )
    return ConversationPolicyOut.model_validate(policy)


@router.post("/{agent_id}/versions/{version_id}/pronunciation", response_model=PronunciationEntryOut, status_code=201)
async def add_pronunciation(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: PronunciationEntryCreate,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> PronunciationEntryOut:
    entry = await service.add_pronunciation_entry(
        db,
        workspace_id=auth.workspace_id,
        agent_id=agent_id,
        version_id=version_id,
        term=payload.term,
        pronunciation=payload.pronunciation,
        language=payload.language,
    )
    return PronunciationEntryOut.model_validate(entry)


@router.delete("/{agent_id}/versions/{version_id}/pronunciation/{entry_id}", status_code=204)
async def delete_pronunciation(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    entry_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("agents:edit")),
    db: AsyncSession = Depends(workspace_db_for("agents:edit")),
) -> None:
    await service.delete_pronunciation_entry(
        db, workspace_id=auth.workspace_id, agent_id=agent_id, version_id=version_id, entry_id=entry_id
    )


@router.post("/{agent_id}/versions/{version_id}/publish", response_model=AgentVersionOut)
async def publish_version(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("agents:publish")),
    db: AsyncSession = Depends(workspace_db_for("agents:publish")),
) -> AgentVersionOut:
    version = await service.publish_version(db, workspace_id=auth.workspace_id, agent_id=agent_id, version_id=version_id)
    return AgentVersionOut.model_validate(version)
