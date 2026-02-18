"""DiagnosisResult — structured LLM output, schema-validated."""

from typing import Optional

from pydantic import BaseModel, Field

from .evidence import EvidenceRef


class DiagnosisResult(BaseModel):
    model_config = {"extra": "forbid"}

    root_cause: str = Field(min_length=1, max_length=2000)
    evidence: list[EvidenceRef] = Field(max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)
    next_checks: list[str] = Field(
        default_factory=list,
        max_length=10,
    )
