"""Tests for PlanSimulator — deterministic safety checks on RemediationPlan."""

import pytest

from investigator.models.remediation import RemediationPlan, SimulationReport
from investigator.remediation.simulator import PlanSimulator


def _plan(*steps: dict) -> RemediationPlan:
    return RemediationPlan(
        plan=list(steps),
        rollback=[],
        expected_time_minutes=5,
    )


class TestPlanSimulator:
    def setup_method(self):
        self.sim = PlanSimulator()

    # -- Result type ----------------------------------------------------------

    def test_returns_simulation_report(self):
        plan = _plan({"step": "noop", "tool": "noop", "command": "noop"})
        result = self.sim.simulate(plan)
        assert isinstance(result, SimulationReport)

    # -- Safe plans -----------------------------------------------------------

    def test_select_only_sql_is_ok(self):
        plan = _plan({"step": "check rows", "tool": "sql", "command": "SELECT count(*) FROM orders"})
        report = self.sim.simulate(plan)
        assert report.ok is True

    def test_noop_tool_is_always_ok(self):
        plan = _plan({"step": "wait", "tool": "noop", "command": "noop"})
        report = self.sim.simulate(plan)
        assert report.ok is True

    def test_rerun_job_tool_is_ok(self):
        plan = _plan({"step": "re-run", "tool": "rerun_job", "command": "dag=foo"})
        report = self.sim.simulate(plan)
        assert report.ok is True

    def test_notify_tool_is_ok(self):
        plan = _plan({"step": "alert", "tool": "notify", "command": "channel=ops"})
        report = self.sim.simulate(plan)
        assert report.ok is True

    # -- Unsafe SQL -----------------------------------------------------------

    def test_sql_with_delete_is_not_ok(self):
        plan = _plan({"step": "purge", "tool": "sql", "command": "DELETE FROM orders WHERE id=1"})
        report = self.sim.simulate(plan)
        assert report.ok is False

    def test_sql_with_drop_is_not_ok(self):
        plan = _plan({"step": "drop table", "tool": "sql", "command": "DROP TABLE orders"})
        report = self.sim.simulate(plan)
        assert report.ok is False

    def test_sql_with_insert_is_not_ok(self):
        plan = _plan({"step": "insert", "tool": "sql", "command": "INSERT INTO t VALUES (1)"})
        report = self.sim.simulate(plan)
        assert report.ok is False

    def test_sql_with_update_is_not_ok(self):
        plan = _plan({"step": "update", "tool": "sql", "command": "UPDATE t SET col=1"})
        report = self.sim.simulate(plan)
        assert report.ok is False

    def test_sql_with_truncate_is_not_ok(self):
        plan = _plan({"step": "truncate", "tool": "sql", "command": "TRUNCATE TABLE orders"})
        report = self.sim.simulate(plan)
        assert report.ok is False

    # -- Checks structure -----------------------------------------------------

    def test_report_includes_named_checks(self):
        plan = _plan({"step": "check", "tool": "sql", "command": "SELECT 1"})
        report = self.sim.simulate(plan)
        names = {c.name for c in report.checks}
        assert "sql_is_select_only" in names

    def test_mixed_plan_fails_on_first_bad_step(self):
        plan = _plan(
            {"step": "ok step", "tool": "sql", "command": "SELECT 1"},
            {"step": "bad step", "tool": "sql", "command": "DELETE FROM t"},
        )
        report = self.sim.simulate(plan)
        assert report.ok is False

    def test_sql_with_select_star_is_ok(self):
        plan = _plan({"step": "count rows", "tool": "sql", "command": "SELECT * FROM audit_log LIMIT 100"})
        report = self.sim.simulate(plan)
        assert report.ok is True
