"""Shared FastAPI dependencies — importable by route modules without circular imports."""

from __future__ import annotations

from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from investigator.repository.incident_repo import SqlIncidentRepository


def get_repo(request: Request) -> Generator[SqlIncidentRepository, None, None]:
    """Per-request repository dependency.

    If the app has a session_factory (production), creates a fresh session
    per request and closes it afterward.  If the app has a pre-built repo
    (tests), yields that directly.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is not None:
        session: Session = factory()
        try:
            yield SqlIncidentRepository(session)
        finally:
            session.close()
    else:
        # Test fallback: pre-built repo on app.state
        yield request.app.state.repo  # type: ignore[misc]
