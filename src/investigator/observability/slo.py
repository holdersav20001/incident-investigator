"""SLO definitions and checker.

SLOs (Service Level Objectives) define the reliability targets for the
investigation pipeline. The checker evaluates current metrics against each
target and returns a list of SLOResult objects.

Standard SLOs:
  pipeline_success_rate  ≥ 0.95  (at most 5% of runs may error)
  simulation_safe_rate   ≥ 0.90  (at most 10% of plans may fail simulation)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from investigator.observability.metrics import MetricsRegistry


class SLOStatus(StrEnum):
    OK = "ok"
    BREACHED = "breached"


@dataclass(frozen=True)
class SLOResult:
    name: str
    target: float
    actual: float
    status: SLOStatus
    detail: str


@dataclass(frozen=True)
class SLODefinition:
    name: str
    target: float
    # Function that computes the current actual value from a MetricsRegistry
    compute: Callable[[MetricsRegistry], float]
    description: str


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _counter_value(reg: MetricsRegistry, name: str) -> int:
    c = reg._counters.get(name)
    if c is None:
        return 0
    return c.value()


def _pipeline_success_rate(reg: MetricsRegistry) -> float:
    runs = _counter_value(reg, "pipeline_runs_total")
    errors = _counter_value(reg, "pipeline_errors_total")
    if runs == 0:
        return 1.0  # no data → assume healthy
    return (runs - errors) / runs


def _simulation_safe_rate(reg: MetricsRegistry) -> float:
    runs = _counter_value(reg, "pipeline_runs_total")
    sim_failures = _counter_value(reg, "simulation_failures_total")
    if runs == 0:
        return 1.0
    return (runs - sim_failures) / runs


# ---------------------------------------------------------------------------
# Standard SLO set
# ---------------------------------------------------------------------------

STANDARD_SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        name="pipeline_success_rate",
        target=0.95,
        compute=_pipeline_success_rate,
        description="At least 95% of pipeline runs must complete without error",
    ),
    SLODefinition(
        name="simulation_safe_rate",
        target=0.90,
        compute=_simulation_safe_rate,
        description="At least 90% of remediation plans must pass the safety simulator",
    ),
)


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

class SLOChecker:
    """Evaluate a set of SLO definitions against a MetricsRegistry snapshot."""

    def __init__(self, slos: tuple[SLODefinition, ...] = STANDARD_SLOS) -> None:
        self._slos = slos

    def check(self, reg: MetricsRegistry) -> list[SLOResult]:
        results: list[SLOResult] = []
        for slo in self._slos:
            actual = slo.compute(reg)
            status = SLOStatus.OK if actual >= slo.target else SLOStatus.BREACHED
            results.append(
                SLOResult(
                    name=slo.name,
                    target=slo.target,
                    actual=round(actual, 4),
                    status=status,
                    detail=f"actual={actual:.4f} target={slo.target}",
                )
            )
        return results

    def all_ok(self, reg: MetricsRegistry) -> bool:
        return all(r.status == SLOStatus.OK for r in self.check(reg))
