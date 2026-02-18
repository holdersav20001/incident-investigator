"""Tests for SLO definitions and the SLO checker."""

import pytest

from investigator.observability.metrics import MetricsRegistry
from investigator.observability.slo import SLOChecker, SLOResult, SLOStatus, STANDARD_SLOS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reg_with_runs(runs: int, errors: int, sim_failures: int = 0) -> MetricsRegistry:
    reg = MetricsRegistry()
    reg.counter("pipeline_runs_total").inc(runs)
    reg.counter("pipeline_errors_total").inc(errors)
    reg.counter("simulation_failures_total").inc(sim_failures)
    return reg


# ---------------------------------------------------------------------------
# SLOResult
# ---------------------------------------------------------------------------

class TestSLOResult:
    def test_fields(self):
        r = SLOResult(
            name="pipeline_success_rate",
            target=0.95,
            actual=0.98,
            status=SLOStatus.OK,
            detail="2/100 errors",
        )
        assert r.name == "pipeline_success_rate"
        assert r.status == SLOStatus.OK

    def test_breached_status(self):
        r = SLOResult(
            name="pipeline_success_rate",
            target=0.95,
            actual=0.90,
            status=SLOStatus.BREACHED,
            detail="10/100 errors",
        )
        assert r.status == SLOStatus.BREACHED


# ---------------------------------------------------------------------------
# SLOChecker — pipeline_success_rate
# ---------------------------------------------------------------------------

class TestPipelineSuccessRateSLO:
    def test_100_percent_success_is_ok(self):
        reg = _reg_with_runs(runs=50, errors=0)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "pipeline_success_rate")
        assert slo.status == SLOStatus.OK

    def test_96_percent_success_is_ok(self):
        reg = _reg_with_runs(runs=100, errors=4)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "pipeline_success_rate")
        assert slo.status == SLOStatus.OK

    def test_90_percent_success_is_breached(self):
        reg = _reg_with_runs(runs=100, errors=10)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "pipeline_success_rate")
        assert slo.status == SLOStatus.BREACHED

    def test_no_runs_is_ok(self):
        reg = MetricsRegistry()  # no counters set
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "pipeline_success_rate")
        assert slo.status == SLOStatus.OK

    def test_actual_rate_is_computed(self):
        reg = _reg_with_runs(runs=100, errors=3)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "pipeline_success_rate")
        assert slo.actual == pytest.approx(0.97)


# ---------------------------------------------------------------------------
# SLOChecker — simulation_safe_rate
# ---------------------------------------------------------------------------

class TestSimulationSafeRateSLO:
    def test_zero_failures_is_ok(self):
        reg = _reg_with_runs(runs=20, errors=0, sim_failures=0)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "simulation_safe_rate")
        assert slo.status == SLOStatus.OK

    def test_many_sim_failures_breached(self):
        reg = _reg_with_runs(runs=100, errors=0, sim_failures=20)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        slo = next(r for r in results if r.name == "simulation_safe_rate")
        assert slo.status == SLOStatus.BREACHED


# ---------------------------------------------------------------------------
# SLOChecker — overall
# ---------------------------------------------------------------------------

class TestSLOCheckerOverall:
    def test_returns_result_for_each_slo(self):
        reg = MetricsRegistry()
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        assert len(results) == len(STANDARD_SLOS)

    def test_all_ok_when_healthy(self):
        reg = _reg_with_runs(runs=100, errors=2, sim_failures=1)
        checker = SLOChecker(STANDARD_SLOS)
        results = checker.check(reg)
        assert all(r.status == SLOStatus.OK for r in results)

    def test_overall_ok_true_when_all_pass(self):
        reg = _reg_with_runs(runs=100, errors=2)
        checker = SLOChecker(STANDARD_SLOS)
        assert checker.all_ok(reg) is True

    def test_overall_ok_false_when_any_breached(self):
        reg = _reg_with_runs(runs=100, errors=10)
        checker = SLOChecker(STANDARD_SLOS)
        assert checker.all_ok(reg) is False
