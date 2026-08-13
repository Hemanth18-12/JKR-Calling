from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling"
    redis_url: str = "redis://localhost:16379/0"
    voice_worker_base_url: str = "http://localhost:8100"
    internal_service_token: str = "change_me_dev_only_service_to_service_token"

    enable_live_calls: bool = False
    authorized_test_numbers: str = ""

    @property
    def authorized_test_numbers_list(self) -> list[str]:
        return [n.strip() for n in self.authorized_test_numbers.split(",") if n.strip()]


def get_settings() -> Settings:
    return Settings()


