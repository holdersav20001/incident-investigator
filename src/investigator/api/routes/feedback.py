"""Feedback API.

POST /incidents/{incident_id}/feedback — submit outcome feedback.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from investigator.models.feedback import OutcomeType
from investigator.repository.incident_repo import SqlIncidentRepository

router = APIRouter()


def _get_repo(request: Request) -> SqlIncidentRepository:
    return request.app.state.repo  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    outcome: OutcomeType
    overrides: Optional[dict[str, Any]] = None
    reviewer_notes: Optional[str] = Field(default=None, max_length=4000)
    timestamp: datetime


class FeedbackResponse(BaseModel):
    incident_id: str
    outcome: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post(
    "/incidents/{incident_id}/feedback",
    response_model=FeedbackResponse,
    status_code=201,
)
def submit_feedback(
    incident_id: UUID, body: FeedbackRequest, request: Request
) -> FeedbackResponse:
    repo = _get_repo(request)
    try:
        repo.create_feedback(
            incident_id,
            outcome=body.outcome,
            overrides=body.overrides,
            reviewer_notes=body.reviewer_notes,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )
    return FeedbackResponse(incident_id=str(incident_id), outcome=body.outcome)
