"""Validate Docker deployment configuration files.

These tests parse Dockerfile and docker-compose.yml and assert that the
expected structure is present.  They run without Docker installed — we
validate the configuration text, not Docker runtime behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE_FILE = ROOT / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"


# ---------------------------------------------------------------------------
# Dockerfile tests
# ---------------------------------------------------------------------------

class TestDockerfile:
    @pytest.fixture(scope="class")
    def dockerfile_text(self) -> str:
        assert DOCKERFILE.exists(), "Dockerfile must exist at project root"
        return DOCKERFILE.read_text(encoding="utf-8")

    def test_dockerfile_exists(self):
        assert DOCKERFILE.exists()

    def test_uses_python_base_image(self, dockerfile_text):
        assert "FROM python" in dockerfile_text

    def test_exposes_port_8000(self, dockerfile_text):
        assert "EXPOSE 8000" in dockerfile_text

    def test_copies_source_code(self, dockerfile_text):
        assert "COPY" in dockerfile_text and "src" in dockerfile_text

    def test_installs_dependencies(self, dockerfile_text):
        assert "pip install" in dockerfile_text

    def test_has_entrypoint_or_cmd(self, dockerfile_text):
        assert "CMD" in dockerfile_text or "ENTRYPOINT" in dockerfile_text

    def test_runs_as_non_root_user(self, dockerfile_text):
        # Security best practice — container should not run as root
        assert "USER" in dockerfile_text

    def test_uses_multi_stage_build(self, dockerfile_text):
        # Multi-stage: at least two FROM instructions
        from_count = sum(1 for line in dockerfile_text.splitlines() if line.startswith("FROM"))
        assert from_count >= 2, "Dockerfile should use multi-stage build (2+ FROM instructions)"


# ---------------------------------------------------------------------------
# docker-compose.yml tests
# ---------------------------------------------------------------------------

class TestDockerCompose:
    @pytest.fixture(scope="class")
    def compose(self) -> dict:
        assert COMPOSE_FILE.exists(), "docker-compose.yml must exist at project root"
        return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    def test_compose_file_exists(self):
        assert COMPOSE_FILE.exists()

    def test_compose_has_services(self, compose):
        assert "services" in compose

    def test_api_service_defined(self, compose):
        assert "api" in compose["services"]

    def test_db_service_defined(self, compose):
        services = compose["services"]
        db_services = {"db", "postgres", "postgresql"}
        assert db_services & set(services), f"Expected a DB service in {list(services)}"

    def test_api_service_has_build_or_image(self, compose):
        api = compose["services"]["api"]
        assert "build" in api or "image" in api

    def test_api_service_exposes_port_8000(self, compose):
        api = compose["services"]["api"]
        ports = api.get("ports", [])
        assert any("8000" in str(p) for p in ports), f"Port 8000 not found in {ports}"

    def test_api_depends_on_db(self, compose):
        api = compose["services"]["api"]
        depends = api.get("depends_on", {})
        if isinstance(depends, list):
            depends_set = set(depends)
        else:
            depends_set = set(depends.keys())
        db_services = {"db", "postgres", "postgresql"}
        assert depends_set & db_services, f"api should depend on DB, got: {depends_set}"

    def test_api_uses_env_file_or_environment(self, compose):
        api = compose["services"]["api"]
        assert "env_file" in api or "environment" in api

    def test_compose_has_named_volume_or_bind_mount_for_db(self, compose):
        db_key = next(
            (k for k in compose["services"] if k in ("db", "postgres", "postgresql")), None
        )
        assert db_key is not None
        db_service = compose["services"][db_key]
        # either volumes on the service or top-level volumes section
        has_volumes = "volumes" in db_service or "volumes" in compose
        assert has_volumes, "DB service should have persistent storage"


# ---------------------------------------------------------------------------
# .env.example tests
# ---------------------------------------------------------------------------

class TestEnvExample:
    @pytest.fixture(scope="class")
    def env_lines(self) -> list[str]:
        assert ENV_EXAMPLE.exists(), ".env.example must exist at project root"
        return ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    def test_env_example_exists(self):
        assert ENV_EXAMPLE.exists()

    def test_contains_database_url(self, env_lines):
        assert any("DATABASE_URL" in line for line in env_lines)

    def test_contains_app_env(self, env_lines):
        assert any("APP_ENV" in line for line in env_lines)

    def test_contains_anthropic_api_key(self, env_lines):
        assert any("ANTHROPIC_API_KEY" in line for line in env_lines)

    def test_contains_llm_provider(self, env_lines):
        assert any("LLM_PROVIDER" in line for line in env_lines)

    def test_no_real_secrets_in_example(self, env_lines):
        # The example file must not contain real-looking API keys
        for line in env_lines:
            if "ANTHROPIC_API_KEY" in line and "=" in line:
                value = line.split("=", 1)[1].strip()
                # A real Anthropic key starts with "sk-ant-"
                assert not value.startswith("sk-ant-"), (
                    f"Real API key found in .env.example: {line}"
                )
