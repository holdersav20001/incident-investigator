"""Feedback — outcome learning loop."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OutcomeType(StrEnum):
    fixed = "fixed"
    not_fixed = "not_fixed"
    unknown = "unknown"


class Feedback(BaseModel):
    model_config = {"extra": "forbid"}

    incident_id: UUID
    outcome: OutcomeType
    overrides: Optional[dict[str, Any]] = None
    reviewer_notes: Optional[str] = Field(default=None, max_length=4000)
    timestamp: datetime
