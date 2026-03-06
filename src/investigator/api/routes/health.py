"""Health check endpoint — enhanced with DB ping and SLO summary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from investigator.observability.slo import SLOChecker, STANDARD_SLOS
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.deps import get_repo

router = APIRouter()


def _get_metrics(request: Request):  # type: ignore[return]
    return getattr(request.app.state, "metrics", None)


class SLOSummary(BaseModel):
    name: str
    target: float
    actual: float
    status: str


class HealthResponse(BaseModel):
    status: str
    db: str = "unknown"
    slos: list[SLOSummary] = []


@router.get("/health", response_model=HealthResponse, status_code=200)
def health_check(request: Request, repo: SqlIncidentRepository = Depends(get_repo)) -> HealthResponse:
    # DB ping
    db_status = "ok"
    try:
        repo._session.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"

    # SLO evaluation
    metrics = _get_metrics(request)
    checker = SLOChecker(STANDARD_SLOS)
    slo_results = checker.check(metrics) if metrics else []
    slos = [
        SLOSummary(name=r.name, target=r.target, actual=r.actual, status=r.status)
        for r in slo_results
    ]

    all_ok = db_status == "ok" and all(s.status == "ok" for s in slos)
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        db=db_status,
        slos=slos,
    )
