from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.models.agents import (
    Agent,
    AgentTool,
    AgentVersion,
    ConversationPolicy,
    PronunciationEntry,
    VoicePersona,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.persona_templates import DEFAULT_TEMPLATE, TEMPLATES
from app.modules.tools import service as tools_service


async def _get_agent_or_404(db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


async def _get_version_or_404(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID
) -> AgentVersion:
    result = await db.execute(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent_id,
            AgentVersion.workspace_id == workspace_id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent version not found")
    return version


async def create_agent(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    name: str,
    business_identity: str,
    description: str | None,
    primary_language: str,
    persona_template: str,
) -> Agent:
    template = TEMPLATES.get(persona_template, TEMPLATES[DEFAULT_TEMPLATE])

    agent = Agent(
        workspace_id=workspace_id,
        name=name,
        business_identity=business_identity,
        description=description,
        primary_language=primary_language,
        persona_template=persona_template,
    )
    db.add(agent)
    await db.flush()

    def fill(text: str) -> str:
        # {business} is static per-agent, filled in now. {name} stays a
        # literal placeholder in the stored text — it's the contact's name,
        # known only per-call, and voice-worker (Phase 3) substitutes it at
        # call time. A plain .replace (not str.format) so the un-filled
        # {name} token survives rather than raising KeyError.
        return text.replace("{business}", business_identity)

    version = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent.id,
        version_number=1,
        status="draft",
        primary_objective=template["primary_objective"],
        ai_disclosure_text=fill(template["ai_disclosure_text"]),
        greeting_text=fill(template["greeting_text"]),
        closing_text=template["closing_text"],
        personality=template["personality"],
        formality=template["formality"],
        energy=template["energy"],
        response_length=template["response_length"],
        supported_languages=[primary_language],
        created_by=created_by,
    )
    db.add(version)
    await db.flush()

    db.add(VoicePersona(workspace_id=workspace_id, agent_version_id=version.id, language=primary_language))
    db.add(ConversationPolicy(workspace_id=workspace_id, agent_version_id=version.id))
    await db.flush()
    await tools_service.seed_default_agent_tools(db, workspace_id=workspace_id, agent_version_id=version.id)

    return agent


async def list_agents(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Agent]:
    result = await db.execute(select(Agent).where(Agent.workspace_id == workspace_id).order_by(Agent.name))
    return list(result.scalars().all())


async def get_agent_with_versions(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID
) -> tuple[Agent, list[AgentVersion]]:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)
    versions_result = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id, AgentVersion.workspace_id == workspace_id)
        .order_by(AgentVersion.version_number.desc())
    )
    return agent, list(versions_result.scalars().all())


async def update_agent(db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, **fields) -> Agent:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)
    for key, value in fields.items():
        if value is not None:
            setattr(agent, key, value)
    await db.flush()
    return agent


async def create_version(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, clone_from_version_id: uuid.UUID | None
) -> AgentVersion:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)

    max_result = await db.execute(
        select(AgentVersion.version_number)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version_number.desc())
        .limit(1)
    )
    max_version = max_result.scalar_one_or_none() or 0

    source: AgentVersion | None = None
    if clone_from_version_id is not None:
        source = await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=clone_from_version_id)
    else:
        latest_result = await db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version_number.desc())
            .limit(1)
        )
        source = latest_result.scalar_one_or_none()

    new_version = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent.id,
        version_number=max_version + 1,
        status="draft",
        primary_objective=source.primary_objective if source else "qualify_lead",
        ai_disclosure_text=source.ai_disclosure_text if source else "",
        greeting_text=source.greeting_text if source else "",
        closing_text=source.closing_text if source else "",
        personality=source.personality if source else "warm_receptionist",
        formality=source.formality if source else "balanced",
        energy=source.energy if source else "medium",
        response_length=source.response_length if source else "short",
        use_honorifics=source.use_honorifics if source else True,
        supported_languages=list(source.supported_languages) if source else [agent.primary_language],
        code_switching_behavior=source.code_switching_behavior if source else "adaptive",
        restricted_phrases=list(source.restricted_phrases) if source else [],
        escalation_policy=dict(source.escalation_policy) if source else {},
    )
    db.add(new_version)
    await db.flush()

    if source:
        src_voice = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == source.id))
        voice = src_voice.scalar_one_or_none()
        db.add(
            VoicePersona(
                workspace_id=workspace_id,
                agent_version_id=new_version.id,
                provider=voice.provider if voice else "mock",
                voice_id=voice.voice_id if voice else "mock-warm-female-te",
                gender_presentation=voice.gender_presentation if voice else "female",
                language=voice.language if voice else agent.primary_language,
                speaking_speed=voice.speaking_speed if voice else 1.0,
                stability=voice.stability if voice else 0.6,
                expressiveness=voice.expressiveness if voice else 0.6,
                fallback_voice_id=voice.fallback_voice_id if voice else None,
            )
        )
        src_policy = await db.execute(select(ConversationPolicy).where(ConversationPolicy.agent_version_id == source.id))
        policy = src_policy.scalar_one_or_none()
        if policy:
            db.add(
                ConversationPolicy(
                    workspace_id=workspace_id,
                    agent_version_id=new_version.id,
                    interruption_enabled=policy.interruption_enabled,
                    min_interruption_ms=policy.min_interruption_ms,
                    accidental_interruption_phrases=list(policy.accidental_interruption_phrases),
                    silence_timeout_ms=policy.silence_timeout_ms,
                    max_monologue_ms=policy.max_monologue_ms,
                    max_response_sentences=policy.max_response_sentences,
                    confirmation_behavior=policy.confirmation_behavior,
                    clarification_behavior=policy.clarification_behavior,
                    background_noise_tolerance=policy.background_noise_tolerance,
                    human_transfer_enabled=policy.human_transfer_enabled,
                    call_later_enabled=policy.call_later_enabled,
                    wrong_number_behavior=policy.wrong_number_behavior,
                    do_not_call_behavior=policy.do_not_call_behavior,
                )
            )
        else:
            db.add(ConversationPolicy(workspace_id=workspace_id, agent_version_id=new_version.id))
    else:
        db.add(VoicePersona(workspace_id=workspace_id, agent_version_id=new_version.id, language=agent.primary_language))
        db.add(ConversationPolicy(workspace_id=workspace_id, agent_version_id=new_version.id))

    if source:
        src_tools = await db.execute(select(AgentTool).where(AgentTool.agent_version_id == source.id))
        for src_tool in src_tools.scalars().all():
            db.add(
                AgentTool(
                    workspace_id=workspace_id, agent_version_id=new_version.id,
                    tool_definition_id=src_tool.tool_definition_id, enabled=src_tool.enabled,
                )
            )
        await db.flush()
    else:
        await tools_service.seed_default_agent_tools(db, workspace_id=workspace_id, agent_version_id=new_version.id)

    await db.flush()
    return new_version


async def get_version_detail(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID
) -> tuple[AgentVersion, VoicePersona | None, ConversationPolicy | None, list[PronunciationEntry]]:
    version = await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    voice_result = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == version.id))
    policy_result = await db.execute(select(ConversationPolicy).where(ConversationPolicy.agent_version_id == version.id))
    pronunciation_result = await db.execute(
        select(PronunciationEntry).where(PronunciationEntry.agent_version_id == version.id).order_by(PronunciationEntry.term)
    )
    return (
        version,
        voice_result.scalar_one_or_none(),
        policy_result.scalar_one_or_none(),
        list(pronunciation_result.scalars().all()),
    )


async def update_version(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, **fields
) -> AgentVersion:
    version = await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    if version.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Published versions are immutable — create a new version to edit")
    for key, value in fields.items():
        if value is not None:
            setattr(version, key, value)
    await db.flush()
    return version


async def update_voice_persona(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, **fields
) -> VoicePersona:
    await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    result = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == version_id))
    voice = result.scalar_one_or_none()
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice persona not found")
    for key, value in fields.items():
        if value is not None:
            setattr(voice, key, value)
    await db.flush()
    return voice


async def update_conversation_policy(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, **fields
) -> ConversationPolicy:
    await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    result = await db.execute(select(ConversationPolicy).where(ConversationPolicy.agent_version_id == version_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation policy not found")
    for key, value in fields.items():
        if value is not None:
            setattr(policy, key, value)
    await db.flush()
    return policy


async def add_pronunciation_entry(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, term: str, pronunciation: str, language: str
) -> PronunciationEntry:
    await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    entry = PronunciationEntry(
        workspace_id=workspace_id, agent_version_id=version_id, term=term, pronunciation=pronunciation, language=language
    )
    db.add(entry)
    await db.flush()
    return entry


async def delete_pronunciation_entry(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, entry_id: uuid.UUID
) -> None:
    await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    result = await db.execute(
        select(PronunciationEntry).where(PronunciationEntry.id == entry_id, PronunciationEntry.agent_version_id == version_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pronunciation entry not found")
    await db.delete(entry)
    await db.flush()


def _has_ai_disclosure(text: str) -> bool:
    """Deliberately permissive substring check, not a strict NLP classifier —
    this is a pre-publish safety NET (docs/SECURITY_AND_COMPLIANCE.md §4), not
    the only check: the post-call quality evaluator (Phase 4) re-checks
    disclosure against the actual transcript, which is the check that matters
    once real calls happen. Requiring a \\b-bounded regex match would miss
    real examples like "AIసహాయకురాలిని" where Telugu characters immediately
    follow "AI" with no space (both sides count as Unicode "word" characters,
    so \\b would not match there)."""
    return "ai" in text.lower()


async def publish_version(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID
) -> AgentVersion:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)
    version = await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)

    errors: dict[str, str] = {}
    if not version.ai_disclosure_text.strip():
        errors["ai_disclosure_text"] = "AI disclosure is required before publishing"
    elif not _has_ai_disclosure(version.ai_disclosure_text):
        errors["ai_disclosure_text"] = "Disclosure text must clearly state this is an AI (spec §3.2 / §28)"
    if not version.greeting_text.strip():
        errors["greeting_text"] = "Greeting is required"
    if not version.closing_text.strip():
        errors["closing_text"] = "Closing is required"

    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": "Cannot publish", "fields": errors})

    version.status = "published"
    version.published_at = datetime.now(UTC)
    agent.published_version_id = version.id
    agent.status = "active"
    await db.flush()
    return version
