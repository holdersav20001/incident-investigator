"""API error response envelope."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    model_config = {"extra": "forbid"}

    error: str
    message: str
    trace_id: str = Field(min_length=8, max_length=128)
    details: Optional[dict[str, Any]] = None
