"""FastAPI application factory.

`create_app` accepts optional pre-built repo and pipeline so tests can
inject in-memory SQLite-backed dependencies without patching globals.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.routes import approvals, events, feedback, health, investigate, observability

if TYPE_CHECKING:
    from investigator.observability.metrics import MetricsRegistry
    from investigator.workflow.pipeline import InvestigationPipeline


def _error_body(error: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": error,
        "message": message,
        "trace_id": str(uuid.uuid4()),
    }
    if details is not None:
        body["details"] = details
    return body


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

    # ------------------------------------------------------------------
    # Global error envelope — ensures all errors use the contracts.md format
    # ------------------------------------------------------------------

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                error=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                error="VALIDATION_ERROR",
                message="Request validation failed",
                details=exc.errors(),
            ),
        )

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(investigate.router)
    app.include_router(observability.router)
    app.include_router(approvals.router)
    app.include_router(feedback.router)

    return app
