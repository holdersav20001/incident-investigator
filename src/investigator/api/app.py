"""FastAPI application factory.

`create_app` accepts optional pre-built repo and pipeline so tests can
inject in-memory SQLite-backed dependencies without patching globals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import FastAPI

from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.routes import approvals, events, health, investigate, observability

if TYPE_CHECKING:
    from investigator.observability.metrics import MetricsRegistry
    from investigator.workflow.pipeline import InvestigationPipeline


def create_app(
    *,
    repo: Optional[SqlIncidentRepository] = None,
    pipeline: Optional["InvestigationPipeline"] = None,
    metrics: Optional["MetricsRegistry"] = None,
) -> FastAPI:
    app = FastAPI(title="Incident Investigator", version="0.1.0")

    # Attach dependencies to app state so routes can access via request.app.state
    if repo is not None:
        app.state.repo = repo
    if pipeline is not None:
        app.state.pipeline = pipeline
    if metrics is not None:
        app.state.metrics = metrics

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(investigate.router)
    app.include_router(observability.router)
    app.include_router(approvals.router)

    return app
