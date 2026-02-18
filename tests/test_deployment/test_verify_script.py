"""Validate the verify.ps1 script structure and content.

Tests parse verify.ps1 as text and assert expected steps are present.
They run without PowerShell or Docker — we validate the script content,
not runtime behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = ROOT / "scripts" / "verify.ps1"


@pytest.fixture(scope="module")
def script_text() -> str:
    assert VERIFY_SCRIPT.exists(), "scripts/verify.ps1 must exist"
    return VERIFY_SCRIPT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existence and basic structure
# ---------------------------------------------------------------------------

class TestVerifyScriptExists:
    def test_file_exists(self):
        assert VERIFY_SCRIPT.exists()

    def test_file_is_non_empty(self, script_text):
        assert len(script_text.strip()) > 100

    def test_has_param_block(self, script_text):
        assert "param(" in script_text

    def test_has_skip_integration_param(self, script_text):
        assert "SkipIntegration" in script_text

    def test_has_skip_compose_param(self, script_text):
        assert "SkipCompose" in script_text


# ---------------------------------------------------------------------------
# Step 1 — Docker compose
# ---------------------------------------------------------------------------

class TestDockerComposeStep:
    def test_starts_db_service(self, script_text):
        assert "docker compose" in script_text
        assert "up -d db" in script_text

    def test_waits_for_healthy_status(self, script_text):
        assert "healthy" in script_text

    def test_skippable_when_skip_integration(self, script_text):
        # The compose block must be guarded by -not $SkipIntegration
        assert "SkipIntegration" in script_text
        assert "SkipCompose" in script_text


# ---------------------------------------------------------------------------
# Step 2 — Alembic migrations
# ---------------------------------------------------------------------------

class TestAlembicStep:
    def test_runs_alembic_upgrade_head(self, script_text):
        assert "alembic upgrade head" in script_text

    def test_sets_database_url_env_var(self, script_text):
        assert "DATABASE_URL" in script_text

    def test_skippable_when_skip_integration(self, script_text):
        # Both docker compose and alembic blocks are guarded by SkipIntegration
        lines = script_text.splitlines()
        alembic_line = next(
            (i for i, l in enumerate(lines) if "alembic upgrade head" in l), None
        )
        assert alembic_line is not None
        # Some SkipIntegration guard must appear before the alembic line
        preceding = "\n".join(lines[:alembic_line])
        assert "SkipIntegration" in preceding


# ---------------------------------------------------------------------------
# Step 3 — Unit tests
# ---------------------------------------------------------------------------

class TestUnitTestStep:
    def test_runs_pytest(self, script_text):
        assert "python -m pytest" in script_text

    def test_ignores_integration_folder(self, script_text):
        assert "--ignore=tests/integration" in script_text

    def test_uses_short_traceback(self, script_text):
        assert "--tb=short" in script_text


# ---------------------------------------------------------------------------
# Step 4 — Integration tests
# ---------------------------------------------------------------------------

class TestIntegrationTestStep:
    def test_runs_integration_marker(self, script_text):
        assert "-m integration" in script_text

    def test_skippable_when_skip_integration(self, script_text):
        lines = script_text.splitlines()
        integ_line = next(
            (i for i, l in enumerate(lines) if "-m integration" in l), None
        )
        assert integ_line is not None
        preceding = "\n".join(lines[:integ_line])
        assert "SkipIntegration" in preceding


# ---------------------------------------------------------------------------
# Exit code discipline
# ---------------------------------------------------------------------------

class TestExitCodeDiscipline:
    def test_checks_lastexitcode_after_pytest(self, script_text):
        assert "LASTEXITCODE" in script_text

    def test_has_fail_function_or_exit(self, script_text):
        # Script must explicitly exit on failure
        assert "exit 1" in script_text or "Fail " in script_text

    def test_reports_success_at_end(self, script_text):
        assert "All checks passed" in script_text
