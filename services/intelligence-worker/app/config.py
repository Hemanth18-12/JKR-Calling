from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling"
    redis_url: str = "redis://localhost:16379/0"
    credentials_encryption_key: str = "change_me_dev_only_fernet_key_44_bytes_base64"


@lru_cache
def get_settings() -> Settings:
    return Settings()
