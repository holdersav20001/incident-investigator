"""RemediationPlan and SimulationReport models."""

from enum import StrEnum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class PlanTool(StrEnum):
    sql = "sql"
    vector = "vector"
    rest = "rest"
    rerun_job = "rerun_job"
    notify = "notify"
    noop = "noop"


class PlanStep(BaseModel):
    model_config = {"extra": "forbid"}

    step: str = Field(min_length=1, max_length=1000)
    tool: PlanTool
    command: str = Field(min_length=1, max_length=4000)


class RollbackStep(BaseModel):
    model_config = {"extra": "forbid"}

    step: str = Field(min_length=1, max_length=1000)


class RemediationPlan(BaseModel):
    model_config = {"extra": "forbid"}

    plan: list[PlanStep] = Field(min_length=1, max_length=12)
    rollback: list[RollbackStep] = Field(max_length=8)
    expected_time_minutes: int = Field(ge=1, le=1440)


class SimCheck(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(max_length=200)
    ok: bool
    value: Optional[Union[str, int, float, bool]] = None


class SimulationReport(BaseModel):
    model_config = {"extra": "forbid"}

    ok: bool
    checks: list[SimCheck] = Field(max_length=50)
    notes: list[str] = Field(default_factory=list, max_length=20)
