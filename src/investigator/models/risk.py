"""RiskAssessment — deterministic scoring output."""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApprovalRecommendation(StrEnum):
    auto_approve = "auto_approve"
    human_review = "human_review"
    reject = "reject"


class RiskAssessment(BaseModel):
    model_config = {"extra": "forbid"}

    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    recommendation: ApprovalRecommendation
    rationale: Optional[str] = Field(default=None, max_length=2000)
    blast_radius: list[str] = Field(default_factory=list, max_length=200)
