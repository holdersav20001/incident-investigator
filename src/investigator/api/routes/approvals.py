"""Approval queue API.

GET  /approvals/pending              — list incidents awaiting human review
POST /approvals/{incident_id}/approve — approve and transition to APPROVED
POST /approvals/{incident_id}/reject  — reject and transition to REJECTED
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.deps import get_repo

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ApprovalQueueItemResponse(BaseModel):
    incident_id: str
    status: str
    required_role: str
    reviewer: Optional[str] = None
    reviewer_note: Optional[str] = None
    created_at: str
    reviewed_at: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    reviewer: str
    reviewer_note: Optional[str] = None


class ApprovalDecisionResponse(BaseModel):
    incident_id: str
    status: str  # approved | rejected


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/approvals/pending", response_model=list[ApprovalQueueItemResponse], status_code=200)
def list_pending(repo: SqlIncidentRepository = Depends(get_repo)) -> list[ApprovalQueueItemResponse]:
    items = repo.list_pending_approvals()
    return [
        ApprovalQueueItemResponse(
            incident_id=item.incident_id,
            status=item.status,
            required_role=item.required_role,
            reviewer=item.reviewer,
            reviewer_note=item.reviewer_note,
            created_at=item.created_at.isoformat(),
            reviewed_at=item.reviewed_at.isoformat() if item.reviewed_at else None,
        )
        for item in items
    ]


@router.post(
    "/approvals/{incident_id}/approve",
    response_model=ApprovalDecisionResponse,
    status_code=200,
)
def approve(incident_id: UUID, body: ApprovalDecisionRequest, repo: SqlIncidentRepository = Depends(get_repo)) -> ApprovalDecisionResponse:
    try:
        repo.record_approval_decision(
            incident_id, approved=True, reviewer=body.reviewer, reviewer_note=body.reviewer_note
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pending approval for incident {incident_id}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return ApprovalDecisionResponse(incident_id=str(incident_id), status="approved")


@router.post(
    "/approvals/{incident_id}/reject",
    response_model=ApprovalDecisionResponse,
    status_code=200,
)
def reject(incident_id: UUID, body: ApprovalDecisionRequest, repo: SqlIncidentRepository = Depends(get_repo)) -> ApprovalDecisionResponse:
    try:
        repo.record_approval_decision(
            incident_id, approved=False, reviewer=body.reviewer, reviewer_note=body.reviewer_note
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pending approval for incident {incident_id}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return ApprovalDecisionResponse(incident_id=str(incident_id), status="rejected")
