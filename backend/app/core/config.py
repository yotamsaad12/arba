from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"


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

    @model_validator(mode="after")
    def _require_real_secret_outside_dev(self) -> "Settings":
        if self.env not in ("dev", "test") and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("ARBA_JWT_SECRET must be set outside dev")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
