"""Tests for RemediationPlan and SimulationReport models."""

import pytest
from pydantic import ValidationError

from investigator.models import (
    PlanStep,
    RollbackStep,
    RemediationPlan,
    SimCheck,
    SimulationReport,
)


VALID_PLAN_STEP = {
    "step": "Re-run extractor with updated schema mapping",
    "tool": "rerun_job",
    "command": "dag=cdc_orders task=extract",
}

VALID_ROLLBACK = {"step": "Revert mapping to previous version"}


class TestPlanStep:
    def test_valid(self) -> None:
        s = PlanStep.model_validate(VALID_PLAN_STEP)
        assert s.tool == "rerun_job"

    def test_invalid_tool(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(step="x", tool="bash", command="rm -rf /")

    def test_all_valid_tools(self) -> None:
        for tool in ("sql", "vector", "rest", "rerun_job", "notify", "noop"):
            PlanStep(step="x", tool=tool, command="x")


class TestRemediationPlan:
    def test_valid(self) -> None:
        plan = RemediationPlan(
            plan=[PlanStep.model_validate(VALID_PLAN_STEP)],
            rollback=[RollbackStep.model_validate(VALID_ROLLBACK)],
            expected_time_minutes=15,
        )
        assert plan.expected_time_minutes == 15

    def test_empty_plan_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RemediationPlan(plan=[], rollback=[], expected_time_minutes=10)

    def test_too_many_steps(self) -> None:
        steps = [PlanStep.model_validate(VALID_PLAN_STEP) for _ in range(13)]
        with pytest.raises(ValidationError):
            RemediationPlan(plan=steps, rollback=[], expected_time_minutes=10)

    def test_time_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RemediationPlan(
                plan=[PlanStep.model_validate(VALID_PLAN_STEP)],
                rollback=[],
                expected_time_minutes=0,
            )
        with pytest.raises(ValidationError):
            RemediationPlan(
                plan=[PlanStep.model_validate(VALID_PLAN_STEP)],
                rollback=[],
                expected_time_minutes=1441,
            )


class TestSimulationReport:
    def test_valid_ok(self) -> None:
        report = SimulationReport(
            ok=True,
            checks=[SimCheck(name="sql_is_select_only", ok=True)],
            notes=["No writes detected."],
        )
        assert report.ok is True

    def test_valid_not_ok(self) -> None:
        report = SimulationReport(
            ok=False,
            checks=[SimCheck(name="tables_allowlisted", ok=False)],
        )
        assert report.notes == []

    def test_too_many_checks(self) -> None:
        checks = [SimCheck(name=f"check_{i}", ok=True) for i in range(51)]
        with pytest.raises(ValidationError):
            SimulationReport(ok=True, checks=checks)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SimulationReport(ok=True, checks=[], bad="field")
