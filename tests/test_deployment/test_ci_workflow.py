"""Validate GitHub Actions CI workflow configuration.

Parses .github/workflows/ci.yml as YAML and asserts the expected structure:
- Correct triggers (push, pull_request)
- Required jobs (test, lint)
- Correct Python setup and test commands
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def ci_config() -> dict:
    assert CI_WORKFLOW.exists(), f"CI workflow not found: {CI_WORKFLOW}"
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


class TestCIWorkflowExists:
    def test_ci_workflow_file_exists(self):
        assert CI_WORKFLOW.exists()

    def test_ci_workflow_is_valid_yaml(self, ci_config):
        assert isinstance(ci_config, dict)


class TestCITriggers:
    def test_triggers_on_push(self, ci_config):
        on = ci_config.get("on") or ci_config.get(True)  # YAML parses 'on' as True
        assert on is not None, "Workflow must have 'on' triggers"
        if isinstance(on, dict):
            assert "push" in on, "Workflow should trigger on push"
        # If on is a list or string it may be simpler
        elif isinstance(on, list):
            assert "push" in on

    def test_triggers_on_pull_request(self, ci_config):
        on = ci_config.get("on") or ci_config.get(True)
        if isinstance(on, dict):
            assert "pull_request" in on, "Workflow should trigger on pull_request"

    def test_has_jobs_section(self, ci_config):
        assert "jobs" in ci_config


class TestCIJobs:
    def test_has_test_job(self, ci_config):
        jobs = ci_config.get("jobs", {})
        assert "test" in jobs, f"Expected 'test' job in jobs: {list(jobs)}"

    def test_has_lint_job(self, ci_config):
        jobs = ci_config.get("jobs", {})
        assert "lint" in jobs, f"Expected 'lint' job in jobs: {list(jobs)}"

    def test_test_job_runs_on_ubuntu(self, ci_config):
        test_job = ci_config["jobs"]["test"]
        runs_on = test_job.get("runs-on", "")
        assert "ubuntu" in str(runs_on), f"test job should run on ubuntu, got: {runs_on}"

    def test_test_job_uses_python(self, ci_config):
        test_job = ci_config["jobs"]["test"]
        steps = test_job.get("steps", [])
        step_text = str(steps).lower()
        assert "python" in step_text, "test job should set up Python"

    def test_test_job_runs_pytest(self, ci_config):
        test_job = ci_config["jobs"]["test"]
        steps = test_job.get("steps", [])
        step_text = str(steps)
        assert "pytest" in step_text, "test job should run pytest"

    def test_lint_job_runs_ruff(self, ci_config):
        lint_job = ci_config["jobs"]["lint"]
        steps = lint_job.get("steps", [])
        step_text = str(steps)
        assert "ruff" in step_text, "lint job should run ruff"
