from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.models.providers import ProviderAccount, ProviderCredential, ProviderHealth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.security import encrypt_secret

# Provider catalog — spec §10.2. `configured_env_vars` is informational only
# (surfaced in the UI so an operator knows what to set in .env); the actual
# adapters live in services/voice-worker (Phase 3) and check these same vars.
CATALOG: list[dict] = [
    {"kind": "telephony", "name": "mock", "label": "Mock Telephony", "requires_credentials": False, "configured_env_vars": []},
    {"kind": "telephony", "name": "twilio", "label": "Twilio", "requires_credentials": True, "configured_env_vars": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]},
    {"kind": "telephony", "name": "sip_trunk", "label": "SIP Trunk", "requires_credentials": True, "configured_env_vars": ["SIP_TRUNK_HOST", "SIP_TRUNK_USERNAME", "SIP_TRUNK_PASSWORD"]},
    {"kind": "telephony", "name": "exotel", "label": "Exotel (planned)", "requires_credentials": True, "configured_env_vars": ["EXOTEL_API_KEY"]},
    {"kind": "telephony", "name": "plivo", "label": "Plivo (planned)", "requires_credentials": True, "configured_env_vars": ["PLIVO_AUTH_ID"]},
    {"kind": "telephony", "name": "telnyx", "label": "Telnyx (planned)", "requires_credentials": True, "configured_env_vars": ["TELNYX_API_KEY"]},
    {"kind": "stt", "name": "mock", "label": "Mock STT", "requires_credentials": False, "configured_env_vars": []},
    {"kind": "stt", "name": "deepgram", "label": "Deepgram", "requires_credentials": True, "configured_env_vars": ["DEEPGRAM_API_KEY"]},
    {"kind": "stt", "name": "sarvam_stt", "label": "Sarvam", "requires_credentials": True, "configured_env_vars": ["SARVAM_API_KEY"]},
    {"kind": "stt", "name": "google_stt", "label": "Google STT", "requires_credentials": True, "configured_env_vars": ["GOOGLE_STT_CREDENTIALS_JSON"]},
    {"kind": "llm", "name": "mock", "label": "Mock LLM (rule-driven)", "requires_credentials": False, "configured_env_vars": []},
    {"kind": "llm", "name": "openai", "label": "OpenAI", "requires_credentials": True, "configured_env_vars": ["OPENAI_API_KEY"]},
    {"kind": "llm", "name": "anthropic", "label": "Anthropic", "requires_credentials": True, "configured_env_vars": ["ANTHROPIC_API_KEY"]},
    {"kind": "llm", "name": "google_llm", "label": "Google", "requires_credentials": True, "configured_env_vars": ["GOOGLE_LLM_API_KEY"]},
    {"kind": "llm", "name": "local_llm", "label": "OpenAI-compatible local endpoint", "requires_credentials": False, "configured_env_vars": ["LOCAL_LLM_BASE_URL"]},
    {"kind": "tts", "name": "mock", "label": "Mock TTS", "requires_credentials": False, "configured_env_vars": []},
    {"kind": "tts", "name": "elevenlabs", "label": "ElevenLabs", "requires_credentials": True, "configured_env_vars": ["ELEVENLABS_API_KEY"]},
    {"kind": "tts", "name": "cartesia", "label": "Cartesia", "requires_credentials": True, "configured_env_vars": ["CARTESIA_API_KEY"]},
    {"kind": "tts", "name": "sarvam_tts", "label": "Sarvam", "requires_credentials": True, "configured_env_vars": ["SARVAM_TTS_API_KEY"]},
    {"kind": "tts", "name": "openai_tts", "label": "OpenAI TTS", "requires_credentials": True, "configured_env_vars": ["OPENAI_TTS_API_KEY"]},
]

DEFAULT_KIND_DISPLAY = {
    "telephony": "Mock Telephony (default)",
    "stt": "Mock STT (default)",
    "llm": "Mock LLM (default)",
    "tts": "Mock TTS (default)",
}


async def seed_default_accounts(db: AsyncSession, *, workspace_id: uuid.UUID) -> None:
    """Every workspace gets one mock provider account per kind, marked
    default, healthy from the start — see docs/DECISIONS/0003-safety-gate-independent-of-dry-run.md.
    Called once at workspace creation."""
    now = datetime.now(UTC)
    for kind, display_name in DEFAULT_KIND_DISPLAY.items():
        account = ProviderAccount(
            workspace_id=workspace_id,
            kind=kind,
            name="mock",
            display_name=display_name,
            is_default=True,
            priority=0,
            status="healthy",
        )
        db.add(account)
        await db.flush()
        db.add(
            ProviderHealth(
                workspace_id=workspace_id,
                provider_account_id=account.id,
                status="healthy",
                latency_p50_ms=0,
                latency_p95_ms=0,
                error_rate=0.0,
                checked_at=now,
                details={"note": "mock provider — always healthy"},
            )
        )


async def list_accounts(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[ProviderAccount]:
    result = await db.execute(
        select(ProviderAccount).where(ProviderAccount.workspace_id == workspace_id).order_by(ProviderAccount.kind, ProviderAccount.priority)
    )
    return list(result.scalars().all())


async def create_account(
    db: AsyncSession, *, workspace_id: uuid.UUID, settings: Settings, payload
) -> ProviderAccount:
    account = ProviderAccount(
        workspace_id=workspace_id,
        kind=payload.kind,
        name=payload.name,
        display_name=payload.display_name,
        is_default=payload.is_default,
        priority=payload.priority,
        region=payload.region,
        status="unknown" if payload.name != "mock" else "healthy",
        config=payload.config,
    )
    db.add(account)
    await db.flush()

    if payload.secret:
        db.add(
            ProviderCredential(
                workspace_id=workspace_id,
                provider_account_id=account.id,
                encrypted_secret=encrypt_secret(payload.secret, settings.credentials_encryption_key),
            )
        )
        await db.flush()

    return account


async def update_account(
    db: AsyncSession, *, workspace_id: uuid.UUID, account_id: uuid.UUID, settings: Settings, payload
) -> ProviderAccount:
    result = await db.execute(
        select(ProviderAccount).where(ProviderAccount.id == account_id, ProviderAccount.workspace_id == workspace_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider account not found")

    if payload.display_name is not None:
        account.display_name = payload.display_name
    if payload.is_default is not None:
        account.is_default = payload.is_default
    if payload.priority is not None:
        account.priority = payload.priority
    if payload.config is not None:
        account.config = payload.config

    if payload.secret:
        existing_cred = await db.execute(
            select(ProviderCredential).where(ProviderCredential.provider_account_id == account.id)
        )
        cred = existing_cred.scalar_one_or_none()
        encrypted = encrypt_secret(payload.secret, settings.credentials_encryption_key)
        if cred is None:
            db.add(
                ProviderCredential(
                    workspace_id=workspace_id, provider_account_id=account.id, encrypted_secret=encrypted
                )
            )
        else:
            cred.encrypted_secret = encrypted
            cred.rotated_at = datetime.now(UTC)

    await db.flush()
    return account


async def health_check(db: AsyncSession, *, workspace_id: uuid.UUID, account_id: uuid.UUID) -> ProviderHealth:
    """Mock providers report synthetic-but-honest health (always up, ~0
    latency, flagged as such). Real providers without credentials report
    down; this pass doesn't make live calls out to real provider APIs to
    check health (that's Phase 3 territory once the adapters exist)."""
    result = await db.execute(
        select(ProviderAccount).where(ProviderAccount.id == account_id, ProviderAccount.workspace_id == workspace_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider account not found")

    now = datetime.now(UTC)
    if account.name == "mock":
        new_status, p50, p95, err = "healthy", 5, 15, 0.0
    else:
        cred = await db.execute(
            select(ProviderCredential).where(ProviderCredential.provider_account_id == account.id)
        )
        has_cred = cred.scalar_one_or_none() is not None
        new_status = "unknown" if not has_cred else "unknown"
        p50 = p95 = err = None

    account.status = new_status
    record = ProviderHealth(
        workspace_id=workspace_id,
        provider_account_id=account.id,
        status=new_status,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        error_rate=err,
        checked_at=now,
        details={"checked_via": "manual"},
    )
    db.add(record)
    await db.flush()
    return record
