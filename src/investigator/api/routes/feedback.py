"""Feedback API.

POST /incidents/{incident_id}/feedback — submit outcome feedback.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from investigator.models.feedback import OutcomeType
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.deps import get_repo

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    outcome: OutcomeType
    overrides: Optional[dict[str, Any]] = None
    reviewer_notes: Optional[str] = Field(default=None, max_length=4000)


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
    incident_id: UUID, body: FeedbackRequest, repo: SqlIncidentRepository = Depends(get_repo)
) -> FeedbackResponse:
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
