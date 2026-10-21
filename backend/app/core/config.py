from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"
DEV_WEBHOOK_PASSWORD = "dev-only-webhook-password"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ARBA_", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://arba:arba@localhost:5432/arba"

    jwt_secret: str = DEV_JWT_SECRET
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: bool = False

    inbox_domain: str = "in.arba.co.il"
    cors_origins: list[str] = ["http://localhost:5173"]

    # File storage. "local" keeps files on disk and serves them through signed API URLs;
    # "s3" uses presigned S3 URLs so files never pass through the API.
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: Path = Path(".storage")
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    upload_url_minutes: int = 15
    max_upload_mb: int = 25

    # Filing suggestions. "auto" uses Claude when ANTHROPIC_API_KEY is set, else the rules engine.
    ai_provider: Literal["auto", "claude", "rules"] = "auto"
    ai_model: str = "claude-opus-5-5"
    ai_effort: Literal["low", "medium", "high"] = "low"

    # The mail provider calls the inbound webhook with these HTTP Basic credentials.
    inbound_webhook_user: str = "postmark"
    inbound_webhook_password: str = DEV_WEBHOOK_PASSWORD

    @model_validator(mode="after")
    def _require_real_secrets_outside_dev(self) -> "Settings":
        if self.env not in ("dev", "test"):
            if self.jwt_secret == DEV_JWT_SECRET:
                raise ValueError("ARBA_JWT_SECRET must be set outside dev")
            if self.inbound_webhook_password == DEV_WEBHOOK_PASSWORD:
                raise ValueError("ARBA_INBOUND_WEBHOOK_PASSWORD must be set outside dev")
            if self.storage_backend == "s3" and not self.s3_bucket:
                raise ValueError("ARBA_S3_BUCKET is required with the s3 storage backend")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
