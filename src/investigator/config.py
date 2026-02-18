"""Application settings — loaded from environment variables or .env file.

All settings have safe defaults for local development.  In production,
override via environment variables (no .env file shipped in the container).

Usage:
    from investigator.config import Settings
    s = Settings()          # reads env vars + .env if present
    print(s.DATABASE_URL)
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration backed by environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,   # env vars are case-sensitive on Linux
        extra="ignore",        # ignore unknown env vars so the app is forward-compatible
    )

    # ---- Database ----
    DATABASE_URL: str = "sqlite:///./incidents.db"

    # ---- Application ----
    APP_ENV: str = "development"     # development | staging | production
    LOG_LEVEL: str = "INFO"

    # ---- Evidence storage ----
    EVIDENCE_ROOT: str = "./evidence"

    # ---- LLM ----
    LLM_PROVIDER: str = "mock"       # "mock" | "anthropic" | "openrouter"
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-haiku-4-5-20251001"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini:free"

    # ---- Normalise log level so "debug" and "DEBUG" are both valid ----
    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        return v.upper()

    # ---- Convenience properties ----

    @property
    def is_postgres(self) -> bool:
        """True when DATABASE_URL targets PostgreSQL."""
        return self.DATABASE_URL.startswith(("postgresql://", "postgres://"))

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"
