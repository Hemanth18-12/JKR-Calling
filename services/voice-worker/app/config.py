from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling"
    internal_service_token: str = "change_me_dev_only_service_to_service_token"
    openai_api_key: str = ""

    tts_provider: str = Field(
        default="mock",
        validation_alias=AliasChoices("TTS_PROVIDER", "TTS_PROVIDER_DEFAULT", "tts_provider"),
    )
    cartesia_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CARTESIA_API_KEY", "cartesia_api_key"),
    )
    cartesia_model: str = Field(
        default="sonic-3.6",
        validation_alias=AliasChoices("CARTESIA_MODEL", "cartesia_model"),
    )
    cartesia_voice_id: str = Field(
        default="db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
        validation_alias=AliasChoices("CARTESIA_VOICE_ID", "cartesia_voice_id"),
    )


@lru_cache
def get_settings() -> Settings:
    import os
    s = Settings()
    if s.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    return s

