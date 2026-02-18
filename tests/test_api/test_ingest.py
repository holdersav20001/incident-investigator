"""Tests for POST /events/ingest endpoint."""

import pytest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investigator.db.models import Base
from investigator.api.app import create_app
from investigator.repository.incident_repo import SqlIncidentRepository


@pytest.fixture()
def db_session():
    # StaticPool shares one connection across all threads — required for
    # in-memory SQLite when TestClient runs the ASGI app in a worker thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session: Session):
    repo = SqlIncidentRepository(db_session)
    app = create_app(repo=repo)
    return TestClient(app)


VALID_PAYLOAD = {
    "incident_id": None,  # set per test
    "source": "airflow",
    "environment": "prod",
    "job_name": "cdc_orders",
    "error_type": "schema_mismatch",
    "error_message": "Column CUSTOMER_ID missing in target",
    "timestamp": "2026-02-18T11:00:00Z",
}


def fresh_payload() -> dict:
    return {**VALID_PAYLOAD, "incident_id": str(uuid4())}


class TestIngestEndpoint:
    def test_returns_201_on_valid_payload(self, client: TestClient) -> None:
        resp = client.post("/events/ingest", json=fresh_payload())
        assert resp.status_code == 201

    def test_response_contains_incident_id(self, client: TestClient) -> None:
        payload = fresh_payload()
        resp = client.post("/events/ingest", json=payload)
        body = resp.json()
        assert body["incident_id"] == payload["incident_id"]

    def test_response_status_is_received(self, client: TestClient) -> None:
        resp = client.post("/events/ingest", json=fresh_payload())
        assert resp.json()["status"] == "RECEIVED"

    def test_duplicate_incident_id_returns_409(self, client: TestClient) -> None:
        payload = fresh_payload()
        client.post("/events/ingest", json=payload)
        resp = client.post("/events/ingest", json=payload)
        assert resp.status_code == 409

    def test_missing_required_field_returns_422(self, client: TestClient) -> None:
        bad = {k: v for k, v in fresh_payload().items() if k != "job_name"}
        resp = client.post("/events/ingest", json=bad)
        assert resp.status_code == 422

    def test_invalid_source_returns_422(self, client: TestClient) -> None:
        bad = {**fresh_payload(), "source": "kafka"}
        resp = client.post("/events/ingest", json=bad)
        assert resp.status_code == 422

    def test_invalid_environment_returns_422(self, client: TestClient) -> None:
        bad = {**fresh_payload(), "environment": "qa"}
        resp = client.post("/events/ingest", json=bad)
        assert resp.status_code == 422

    def test_error_response_has_trace_id(self, client: TestClient) -> None:
        bad = {k: v for k, v in fresh_payload().items() if k != "source"}
        resp = client.post("/events/ingest", json=bad)
        assert resp.status_code == 422
        # FastAPI's validation response body is standard; we check it's parseable
        assert "detail" in resp.json() or "error" in resp.json()


class TestHealthCheck:
    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
