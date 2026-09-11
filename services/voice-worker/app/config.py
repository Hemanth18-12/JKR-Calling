from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling"
    internal_service_token: str = "change_me_dev_only_service_to_service_token"
    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    import os
    s = Settings()
    if s.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    return s

