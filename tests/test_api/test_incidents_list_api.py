"""Tests for GET /incidents list endpoint and error response envelope."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.api.app import create_app
from investigator.db.models import Base
from investigator.repository.incident_repo import SqlIncidentRepository


@pytest.fixture()
def client_and_repo():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = SqlIncidentRepository(session)
    app = create_app(repo=repo)
    return TestClient(app), repo


def _ingest(client, incident_id: str, env: str = "dev") -> None:
    client.post(
        "/events/ingest",
        json={
            "incident_id": incident_id,
            "source": "airflow",
            "environment": env,
            "job_name": "cdc_orders",
            "error_type": "timeout",
            "error_message": "Job timed out",
            "timestamp": "2026-02-18T11:00:00Z",
        },
    )


class TestListIncidents:
    def test_returns_200(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.get("/incidents")
        assert resp.status_code == 200

    def test_empty_list_when_none(self, client_and_repo):
        client, _ = client_and_repo
        data = client.get("/incidents").json()
        assert data == []

    def test_lists_ingested_incident(self, client_and_repo):
        client, _ = client_and_repo
        _ingest(client, "eeee0000-0000-0000-0000-000000000001")
        data = client.get("/incidents").json()
        assert len(data) == 1

    def test_each_item_has_incident_id(self, client_and_repo):
        client, _ = client_and_repo
        _ingest(client, "eeee0000-0000-0000-0000-000000000002")
        data = client.get("/incidents").json()
        assert "incident_id" in data[0]

    def test_each_item_has_status(self, client_and_repo):
        client, _ = client_and_repo
        _ingest(client, "eeee0000-0000-0000-0000-000000000003")
        data = client.get("/incidents").json()
        assert "status" in data[0]

    def test_filter_by_status(self, client_and_repo):
        client, _ = client_and_repo
        _ingest(client, "eeee0000-0000-0000-0000-000000000004")
        data_received = client.get("/incidents?status=RECEIVED").json()
        data_approved = client.get("/incidents?status=APPROVED").json()
        assert len(data_received) == 1
        assert len(data_approved) == 0

    def test_limit_parameter(self, client_and_repo):
        client, _ = client_and_repo
        for i in range(5):
            _ingest(client, f"ffff0000-0000-0000-0000-00000000000{i}")
        data = client.get("/incidents?limit=3").json()
        assert len(data) == 3

    def test_offset_parameter(self, client_and_repo):
        client, _ = client_and_repo
        for i in range(3):
            _ingest(client, f"aaaa1000-0000-0000-0000-00000000000{i}")
        all_data = client.get("/incidents").json()
        offset_data = client.get("/incidents?offset=2").json()
        assert len(offset_data) == 1


class TestErrorEnvelope:
    def test_404_has_trace_id(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.get("/incidents/00000000-0000-0000-0000-000000000099")
        assert resp.status_code == 404
        data = resp.json()
        assert "trace_id" in data

    def test_404_has_error_field(self, client_and_repo):
        client, _ = client_and_repo
        data = client.get("/incidents/00000000-0000-0000-0000-000000000099").json()
        assert "error" in data

    def test_404_has_message_field(self, client_and_repo):
        client, _ = client_and_repo
        data = client.get("/incidents/00000000-0000-0000-0000-000000000099").json()
        assert "message" in data

    def test_422_has_trace_id(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.post("/events/ingest", json={"bad": "payload"})
        assert resp.status_code == 422
        data = resp.json()
        assert "trace_id" in data
