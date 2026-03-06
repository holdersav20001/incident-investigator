"""POST /incidents/{id}/investigate — trigger the investigation pipeline.
GET  /incidents/{id}           — read incident record.
GET  /incidents                — list incidents with optional status filter and pagination.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from typing import Any, Optional

from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.state.machine import IncidentStatus
from investigator.workflow.pipeline import InvestigationPipeline
from investigator.api.deps import get_repo

router = APIRouter()


def _get_pipeline(request: Request, repo: SqlIncidentRepository) -> InvestigationPipeline:
    """Build a pipeline using the per-request repo.

    If app.state has a pre-built pipeline (tests), return that.
    Otherwise, assemble from stored components with the per-request repo.
    """
    pre_built = getattr(request.app.state, "pipeline", None)
    if pre_built is not None:
        return pre_built
    components = request.app.state.pipeline_components
    return InvestigationPipeline(repo=repo, **components)


def _get_metrics(request: Request):  # type: ignore[return]
    return getattr(request.app.state, "metrics", None)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class InvestigateResponse(BaseModel):
    incident_id: str
    final_status: str
    error: Optional[str] = None


class IncidentResponse(BaseModel):
    incident_id: str
    status: str
    classification: Optional[Any] = None
    diagnosis: Optional[Any] = None
    remediation: Optional[Any] = None
    simulation: Optional[Any] = None
    risk: Optional[Any] = None
    approval_status: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/incidents/{incident_id}/investigate",
    response_model=InvestigateResponse,
    status_code=200,
)
def investigate(incident_id: UUID, request: Request, repo: SqlIncidentRepository = Depends(get_repo)) -> InvestigateResponse:
    pipeline = _get_pipeline(request, repo)
    metrics = _get_metrics(request)
    try:
        result = pipeline.run(incident_id=incident_id, metrics=metrics)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )
    return InvestigateResponse(
        incident_id=str(result.incident_id),
        final_status=result.final_status,
        error=result.error,
    )


class IncidentListItem(BaseModel):
    incident_id: str
    status: str
    environment: str
    job_name: str
    created_at: str
    updated_at: str


@router.get("/incidents", response_model=list[IncidentListItem], status_code=200)
def list_incidents(
    repo: SqlIncidentRepository = Depends(get_repo),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[IncidentListItem]:
    try:
        inc_status = IncidentStatus(status) if status else None
    except ValueError:
        valid = [s.value for s in IncidentStatus]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status filter: {status}. Valid values: {valid}",
        )
    rows = repo.list_incidents(status=inc_status, limit=limit, offset=offset)
    return [
        IncidentListItem(
            incident_id=row.incident_id,
            status=row.status,
            environment=row.environment,
            job_name=row.job_name,
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
        )
        for row in rows
    ]


@router.get("/incidents/{incident_id}", response_model=IncidentResponse, status_code=200)
def get_incident(incident_id: UUID, repo: SqlIncidentRepository = Depends(get_repo)) -> IncidentResponse:
    row = repo.get_incident(incident_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )
    return IncidentResponse(
        incident_id=row.incident_id,
        status=row.status,
        classification=row.classification,
        diagnosis=row.diagnosis,
        remediation=row.remediation,
        simulation=row.simulation,
        risk=row.risk,
        approval_status=row.approval_status,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )
