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

from app.modules.agents.persona_templates import DEFAULT_TEMPLATE, TEMPLATES, get_template_content
from app.modules.agents.safety import validate_and_sanitize_persona_field
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

    persona_texts = get_template_content(
        persona_template,
        primary_language,
        business_identity,
        description or "",
    )

    version = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent.id,
        version_number=1,
        status="draft",
        primary_objective=template["primary_objective"],
        ai_disclosure_text=persona_texts["ai_disclosure_text"],
        greeting_text=persona_texts["greeting_text"],
        closing_text=persona_texts["closing_text"],
        personality=template["personality"],
        formality=template["formality"],
        energy=template["energy"],
        response_length=template["response_length"],
        supported_languages=[primary_language],
        created_by=created_by,
    )
    db.add(version)
    await db.flush()

    # Select speaker matching language
    lang_lower = primary_language.lower()
    if "te" in lang_lower:
        default_voice = "priya"
    elif "hi" in lang_lower:
        default_voice = "meera"
    else:
        default_voice = "aravind"

    db.add(VoicePersona(
        workspace_id=workspace_id,
        agent_version_id=version.id,
        language=primary_language,
        voice_id=default_voice,
    ))
    db.add(ConversationPolicy(workspace_id=workspace_id, agent_version_id=version.id))
    await db.flush()
    await tools_service.seed_default_agent_tools(db, workspace_id=workspace_id, agent_version_id=version.id)

    return agent


async def list_agents(db: AsyncSession, *, workspace_id: uuid.UUID, include_archived: bool = False) -> list[Agent]:
    query = select(Agent).where(Agent.workspace_id == workspace_id)
    if not include_archived:
        query = query.where(Agent.status != "archived")
    query = query.order_by(Agent.name)
    result = await db.execute(query)
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


async def update_agent(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID, regenerate_persona_flag: bool = False, **fields
) -> Agent:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)
    old_biz = agent.business_identity
    old_lang = agent.primary_language

    for key, value in fields.items():
        if value is not None and hasattr(agent, key):
            setattr(agent, key, value)
    await db.flush()

    if regenerate_persona_flag or (
        (agent.business_identity != old_biz or agent.primary_language != old_lang)
        and regenerate_persona_flag
    ):
        await regenerate_persona(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
            language=agent.primary_language,
            template_key=agent.persona_template,
        )

    return agent


async def delete_agent(db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID) -> dict[str, str]:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)

    # 1. Block if used by an active campaign
    from jkr_db.models.campaigns import Campaign
    active_camp_res = await db.execute(
        select(Campaign).where(
            Campaign.workspace_id == workspace_id,
            Campaign.agent_id == agent_id,
            Campaign.status.in_(["running", "scheduled", "in_progress", "active"]),
        )
    )
    active_camp = active_camp_res.scalar_one_or_none()
    if active_camp is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot delete agent '{agent.name}': currently assigned to active campaign '{active_camp.name}'. Pause or cancel the campaign first.",
        )

    # 2. Check if agent has call history or past campaigns (foreign key RESTRICT on call_sessions & campaigns)
    from jkr_db.models.calls import CallSession
    call_res = await db.execute(select(CallSession.id).where(CallSession.agent_id == agent_id).limit(1))
    has_calls = call_res.scalar_one_or_none() is not None

    camp_res = await db.execute(select(Campaign.id).where(Campaign.agent_id == agent_id).limit(1))
    has_campaigns = camp_res.scalar_one_or_none() is not None

    if has_calls or has_campaigns:
        # Safe soft-delete / archive to preserve analytics and foreign keys
        agent.status = "archived"
        await db.flush()
        return {
            "status": "ok",
            "action": "archived",
            "message": f"Agent '{agent.name}' has call history and has been safely archived.",
        }
    else:
        # Hard delete if clean
        await db.delete(agent)
        await db.flush()
        return {
            "status": "ok",
            "action": "deleted",
            "message": f"Agent '{agent.name}' deleted successfully.",
        }


async def regenerate_persona(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    language: str | None = None,
    template_key: str | None = None,
) -> AgentVersion:
    agent = await _get_agent_or_404(db, workspace_id=workspace_id, agent_id=agent_id)
    target_lang = language or agent.primary_language
    target_tpl = template_key or agent.persona_template or DEFAULT_TEMPLATE

    if version_id:
        version = await _get_version_or_404(db, workspace_id=workspace_id, agent_id=agent_id, version_id=version_id)
    else:
        latest_res = await db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id, AgentVersion.workspace_id == workspace_id)
            .order_by(AgentVersion.version_number.desc())
            .limit(1)
        )
        version = latest_res.scalar_one_or_none()
        if version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No version found for agent")

    # If the version is published (locked), clone to a new draft version
    if version.status == "published":
        version = await create_version(db, workspace_id=workspace_id, agent_id=agent_id, clone_from_version_id=version.id)

    texts = get_template_content(
        target_tpl,
        target_lang,
        agent.business_identity,
        agent.description or "",
    )

    version.ai_disclosure_text = texts["ai_disclosure_text"]
    version.greeting_text = texts["greeting_text"]
    version.closing_text = texts["closing_text"]
    version.supported_languages = [target_lang]

    # Update agent primary language if changed
    if agent.primary_language != target_lang:
        agent.primary_language = target_lang

    # Update voice persona language & voice
    voice_res = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == version.id))
    voice = voice_res.scalar_one_or_none()
    if voice:
        voice.language = target_lang
        lang_lower = target_lang.lower()
        if "te" in lang_lower:
            voice.voice_id = "priya"
        elif "hi" in lang_lower:
            voice.voice_id = "meera"
        else:
            voice.voice_id = "aravind"

    await db.flush()
    return version


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
    persona_text_fields = {"greeting_text", "ai_disclosure_text", "closing_text"}
    for key, value in fields.items():
        if value is not None:
            if key in persona_text_fields and isinstance(value, str):
                value = validate_and_sanitize_persona_field(value, key.replace("_", " ").capitalize())
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

    for field_key, field_name, val in [
        ("ai_disclosure_text", "AI disclosure", version.ai_disclosure_text),
        ("greeting_text", "Greeting", version.greeting_text),
        ("closing_text", "Closing", version.closing_text),
    ]:
        if val:
            try:
                validate_and_sanitize_persona_field(val, field_name)
            except HTTPException as e:
                errors[field_key] = str(e.detail)

    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": "Cannot publish", "fields": errors})

    version.status = "published"
    version.published_at = datetime.now(UTC)
    agent.published_version_id = version.id
    agent.status = "active"
    await db.flush()
    return version
