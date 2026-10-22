import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"
DEV_WEBHOOK_PASSWORD = "dev-only-webhook-password"
DEV_WHATSAPP_SECRET = "dev-only-whatsapp-app-secret"


class Settings(BaseSettings):
    # Tests must not pick up someone's local .env (real SMTP, allow-lists, keys).
    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("ARBA_ENV") == "test" else ".env",
        env_prefix="ARBA_",
        extra="ignore",
    )

    env: str = "dev"
    # Vercel's Postgres (Neon) integration provides DATABASE_URL; ARBA_DATABASE_URL wins.
    database_url: str = Field(
        default="postgresql+asyncpg://arba:arba@localhost:5432/arba",
        validation_alias=AliasChoices("ARBA_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"),
    )

    jwt_secret: str = DEV_JWT_SECRET
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: bool = False

    inbox_domain: str = "in.arba.co.il"
    cors_origins: list[str] = ["http://localhost:5173"]

    # File storage. "local" keeps files on disk and serves them through signed API URLs;
    # "s3" uses presigned S3 URLs so files never pass through the API.
    # "database" keeps files in Postgres, for hosts without a persistent disk (Vercel).
    storage_backend: Literal["local", "s3", "database"] = "local"
    # A direct (unpooled) connection for migrations; Neon on Vercel provides one.
    database_url_direct: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ARBA_DATABASE_URL_DIRECT", "DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING"
        ),
    )
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

    # Links in notifications point here.
    app_url: str = "http://localhost:5180"
    timezone: str = "Asia/Jerusalem"

    # Outgoing email. In dev, SMTP goes to Mailpit (http://localhost:8025).
    email_backend: Literal["smtp", "console"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    email_from: str = "Arba <updates@arba.co.il>"
    # Dev safety net with a real mail server: only these addresses get mail; others are skipped.
    email_allowed_recipients: list[str] | None = None

    # WhatsApp. "simulator" keeps messages in the database and shows them on /dev/whatsapp;
    # "cloud" sends through Meta's WhatsApp Cloud API.
    whatsapp_provider: Literal["simulator", "cloud", "disabled"] = "simulator"
    whatsapp_api_version: str = "v23.0"
    whatsapp_phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None
    whatsapp_access_token: str | None = None
    # Signs webhook calls (X-Hub-Signature-256); Meta app secret in production.
    whatsapp_app_secret: str = DEV_WHATSAPP_SECRET
    # Echoed back when Meta verifies the webhook URL.
    whatsapp_verify_token: str = "dev-only-verify-token"
    whatsapp_language: str = "he"

    # Importing an existing project's mail. "auto" uses Gmail when a Google OAuth client is
    # configured, otherwise the simulator (dev and test only).
    mailbox_provider: Literal["auto", "gmail", "simulator", "disabled"] = "auto"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Mailbox scans stop after this many messages.
    mailbox_scan_limit: int = 300

    # Runs the notification worker inside the API process. Turn off when a separate
    # `python -m app.worker` runs (production).
    run_worker_in_api: bool = True

    # Serverless hosting (Vercel): no long-running worker, no disk; the API migrates and
    # seeds itself on first use, sends urgent notifications right away, and a cron call
    # (/api/v1/cron/tick, with this secret) does the periodic work.
    serverless: bool = Field(
        default=False, validation_alias=AliasChoices("ARBA_SERVERLESS", "VERCEL")
    )
    cron_secret: str | None = Field(
        default=None, validation_alias=AliasChoices("CRON_SECRET", "ARBA_CRON_SECRET")
    )

    # The mail provider calls the inbound webhook with these HTTP Basic credentials.
    inbound_webhook_user: str = "postmark"
    inbound_webhook_password: str = DEV_WEBHOOK_PASSWORD

    @model_validator(mode="after")
    def _serverless_defaults(self) -> "Settings":
        if not self.serverless:
            return self
        explicit = self.model_fields_set
        if "storage_backend" not in explicit:
            self.storage_backend = "database"
        if "run_worker_in_api" not in explicit:
            self.run_worker_in_api = False
        if "cookie_secure" not in explicit:
            self.cookie_secure = True
        if "whatsapp_provider" not in explicit:
            self.whatsapp_provider = "disabled"
        production_host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        if "app_url" not in explicit and production_host:
            self.app_url = f"https://{production_host}"
        return self

    @model_validator(mode="after")
    def _async_database_driver(self) -> "Settings":
        # Hosts (Railway, Heroku-style) hand out postgres:// URLs; SQLAlchemy needs asyncpg.
        def asyncpg(url: str) -> str:
            for prefix in ("postgres://", "postgresql://"):
                if url.startswith(prefix):
                    return "postgresql+asyncpg://" + url[len(prefix) :]
            return url

        self.database_url = asyncpg(self.database_url)
        if self.database_url_direct:
            self.database_url_direct = asyncpg(self.database_url_direct)
        return self

    @model_validator(mode="after")
    def _require_real_secrets_outside_dev(self) -> "Settings":
        if self.env not in ("dev", "test"):
            if self.jwt_secret == DEV_JWT_SECRET:
                raise ValueError("ARBA_JWT_SECRET must be set outside dev")
            if self.inbound_webhook_password == DEV_WEBHOOK_PASSWORD:
                raise ValueError("ARBA_INBOUND_WEBHOOK_PASSWORD must be set outside dev")
            if self.whatsapp_provider == "cloud" and (
                self.whatsapp_app_secret == DEV_WHATSAPP_SECRET
                or not self.whatsapp_access_token
                or not self.whatsapp_phone_number_id
            ):
                raise ValueError("WhatsApp cloud needs a token, phone number id and app secret")
            if self.storage_backend == "s3" and not self.s3_bucket:
                raise ValueError("ARBA_S3_BUCKET is required with the s3 storage backend")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
