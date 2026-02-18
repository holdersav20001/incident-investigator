"""Tests for application settings loaded from environment variables.

All tests use monkeypatch to isolate env-var state — no real .env file required.
"""

from __future__ import annotations

import pytest

from investigator.config import Settings


class TestSettingsDefaults:
    def test_default_database_url(self):
        s = Settings()
        assert s.DATABASE_URL == "sqlite:///./incidents.db"

    def test_default_app_env(self):
        s = Settings()
        assert s.APP_ENV == "development"

    def test_default_log_level(self):
        s = Settings()
        assert s.LOG_LEVEL == "INFO"

    def test_default_evidence_root(self):
        s = Settings()
        assert s.EVIDENCE_ROOT == "./evidence"

    def test_default_anthropic_api_key_is_empty(self):
        s = Settings()
        assert s.ANTHROPIC_API_KEY == ""

    def test_default_llm_provider_is_mock(self):
        s = Settings()
        assert s.LLM_PROVIDER == "mock"

    def test_default_llm_model(self):
        s = Settings()
        assert "claude" in s.LLM_MODEL


class TestSettingsFromEnv:
    def test_database_url_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/incidents")
        s = Settings()
        assert s.DATABASE_URL == "postgresql://user:pass@db:5432/incidents"

    def test_app_env_override(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        s = Settings()
        assert s.APP_ENV == "production"

    def test_log_level_override(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.LOG_LEVEL == "DEBUG"

    def test_evidence_root_override(self, monkeypatch):
        monkeypatch.setenv("EVIDENCE_ROOT", "/data/evidence")
        s = Settings()
        assert s.EVIDENCE_ROOT == "/data/evidence"

    def test_anthropic_api_key_override(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        s = Settings()
        assert s.ANTHROPIC_API_KEY == "sk-ant-test-key"

    def test_llm_provider_override(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        s = Settings()
        assert s.LLM_PROVIDER == "anthropic"


class TestSettingsLogLevelNormalisation:
    def test_lowercase_normalised_to_uppercase(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")
        s = Settings()
        assert s.LOG_LEVEL == "DEBUG"

    def test_mixed_case_normalised(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "Warning")
        s = Settings()
        assert s.LOG_LEVEL == "WARNING"


class TestSettingsProperties:
    def test_is_postgres_false_for_sqlite(self):
        s = Settings()
        assert s.is_postgres is False

    def test_is_postgres_true_for_postgresql(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        s = Settings()
        assert s.is_postgres is True

    def test_is_postgres_true_for_postgres_shorthand(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://localhost/db")
        s = Settings()
        assert s.is_postgres is True

    def test_is_production_false_by_default(self):
        s = Settings()
        assert s.is_production is False

    def test_is_production_true_for_production_env(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        s = Settings()
        assert s.is_production is True

    def test_is_development_true_by_default(self):
        s = Settings()
        assert s.is_development is True

    def test_is_development_false_for_production(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        s = Settings()
        assert s.is_development is False
