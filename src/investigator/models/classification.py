"""ClassificationResult — output of the deterministic rules classifier."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ClassificationType(StrEnum):
    schema_mismatch = "schema_mismatch"
    timeout = "timeout"
    data_quality = "data_quality"
    auth = "auth"
    connectivity = "connectivity"
    unknown = "unknown"


class ClassificationResult(BaseModel):
    model_config = {"extra": "forbid"}

    type: ClassificationType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=1000)
