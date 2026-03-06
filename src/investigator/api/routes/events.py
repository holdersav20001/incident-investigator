"""POST /events/ingest — receive a new incident event."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from investigator.models import IncidentEvent
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.deps import get_repo

router = APIRouter()


class IngestResponse(BaseModel):
    incident_id: str
    status: str


@router.post("/events/ingest", response_model=IngestResponse, status_code=201)
def ingest_event(event: IncidentEvent, repo: SqlIncidentRepository = Depends(get_repo)) -> IngestResponse:
    try:
        repo.create_incident(event)
    except Exception as exc:
        # Duplicate primary key from the DB surfaces here
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "primary key" in exc_str:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Incident {event.incident_id} already exists",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist incident",
        ) from exc

    return IngestResponse(incident_id=str(event.incident_id), status="RECEIVED")
