"""FastAPI application factory.

`create_app` accepts an optional pre-built repo so tests can inject
an in-memory SQLite-backed repo without patching globals.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.api.routes import events, health


def create_app(*, repo: Optional[SqlIncidentRepository] = None) -> FastAPI:
    app = FastAPI(title="Incident Investigator", version="0.1.0")

    # Attach the repo to app state so routes can access it via request.app.state
    if repo is not None:
        app.state.repo = repo

    app.include_router(health.router)
    app.include_router(events.router)

    return app
