from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    voice_worker_base_url: str = "http://localhost:8100"

    database_url: str = "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling"
    redis_url: str = "redis://localhost:16379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "jkr_minio"
    s3_secret_access_key: str = "jkr_minio_local_dev"
    s3_bucket_recordings: str = "jkr-recordings"
    s3_bucket_documents: str = "jkr-documents"
    s3_bucket_exports: str = "jkr-exports"
    s3_region: str = "ap-south-1"
    s3_force_path_style: bool = True

    session_secret: str = "change_me_dev_only_session_secret"
    csrf_secret: str = "change_me_dev_only_csrf_secret"
    credentials_encryption_key: str = "change_me_dev_only_fernet_key_44_bytes_base64"
    internal_service_token: str = "change_me_dev_only_service_to_service_token"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:3000/auth/oauth/google/callback"

    enable_live_calls: bool = False
    authorized_test_numbers: str = ""

    # --- Live real-call test path (app/modules/live_call) — additive, off by
    # default; see docs comment in .env.example. ---
    public_webhook_base_url: str = ""  # e.g. an ngrok https URL; falls back to api_base_url
    llm_provider_default: str = "mock"
    openai_api_key: str = ""
    telephony_provider_default: str = "mock"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    sarvam_tts_api_key: str = ""
    sarvam_api_key: str = ""

    session_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days
    session_cookie_name: str = "jkr_session"

    default_workspace_daily_budget_paise: int = 500_000
    default_workspace_monthly_budget_paise: int = 10_000_000

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def authorized_test_numbers_list(self) -> list[str]:
        return [n.strip() for n in self.authorized_test_numbers.split(",") if n.strip()]

    @property
    def effective_public_webhook_base_url(self) -> str:
        return self.public_webhook_base_url or self.api_base_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
