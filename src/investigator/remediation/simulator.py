"""PlanSimulator — deterministic safety checks on a RemediationPlan.

The simulator validates that a proposed plan is safe to review before it
reaches an approver. It never executes any commands; it only inspects them.

Safety checks performed:
  sql_is_select_only — SQL tool steps may only use SELECT statements
"""

import re

from investigator.models.remediation import RemediationPlan, SimCheck, SimulationReport

# Patterns that indicate writes/DDL — none of these are allowed in SQL steps.
_SQL_FORBIDDEN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|UPSERT)\b",
    re.IGNORECASE,
)


def _check_sql_is_select_only(plan: RemediationPlan) -> SimCheck:
    for step in plan.plan:
        if step.tool == "sql" and _SQL_FORBIDDEN.match(step.command):
            return SimCheck(
                name="sql_is_select_only",
                ok=False,
                value=f"Forbidden SQL in step: {step.step!r}",
            )
    return SimCheck(name="sql_is_select_only", ok=True)


class PlanSimulator:
    """Run deterministic safety checks against a RemediationPlan.

    All checks are fast, local, and have no side effects.
    A SimulationReport with ok=False must block approval.
    """

    def simulate(self, plan: RemediationPlan) -> SimulationReport:
        checks = [
            _check_sql_is_select_only(plan),
        ]
        overall_ok = all(c.ok for c in checks)
        notes = []
        if overall_ok:
            notes.append("All checks passed. Safe to review.")
        else:
            failed = [c.name for c in checks if not c.ok]
            notes.append(f"Failed checks: {', '.join(failed)}. Human review required.")

        return SimulationReport(ok=overall_ok, checks=checks, notes=notes)
