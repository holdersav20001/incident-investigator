"""Shared fixtures for integration tests.

All integration tests require Docker.  When Docker is unavailable the entire
integration suite is automatically skipped — no manual -m flag needed.

Usage:
    pytest -m integration           # run only integration tests
    pytest -m "not integration"     # skip integration tests (default addopts)
    pytest tests/integration/       # run all integration tests directly
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Docker / testcontainers availability guard
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


_SKIP_REASON = "Docker is not available — skipping integration tests"

# Session-scoped: one Postgres container shared across all integration tests
# (faster than starting a new container per test)

@pytest.fixture(scope="session")
def postgres_container():
    """Start a Postgres 16 container and yield its connection URL."""
    if not _docker_available():
        pytest.skip(_SKIP_REASON)

    from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="incidents_test",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def postgres_url(postgres_container) -> str:
    """SQLAlchemy-compatible connection URL for the running test container."""
    # testcontainers returns a psycopg2 URL (postgresql+psycopg2://...)
    # SQLAlchemy accepts postgresql:// or postgresql+psycopg2://
    url = postgres_container.get_connection_url()
    # Normalise to the dialect SQLAlchemy knows
    return url.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture(scope="session")
def pg_engine(postgres_url):
    """SQLAlchemy engine connected to the test Postgres container."""
    from sqlalchemy import create_engine  # noqa: PLC0415
    from investigator.db.models import Base  # noqa: PLC0415

    engine = create_engine(postgres_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def pg_session(pg_engine):
    """Fresh SQLAlchemy session per test; rolls back after each test."""
    from sqlalchemy.orm import Session  # noqa: PLC0415

    with Session(pg_engine) as session:
        yield session
        session.rollback()
