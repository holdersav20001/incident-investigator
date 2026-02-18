"""ApprovalQueueItem — human approval workflow."""

from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalQueueItem(BaseModel):
    model_config = {"extra": "forbid"}

    incident_id: UUID
    status: ApprovalStatus
    required_role: str = Field(max_length=200)
    reviewer: Optional[str] = Field(default=None, max_length=200)
    reviewer_note: Optional[str] = Field(default=None, max_length=2000)
    created_at: datetime
    reviewed_at: Optional[datetime] = None
