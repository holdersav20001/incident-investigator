"""Tests for feedback API: POST /incidents/{id}/feedback."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.api.app import create_app
from investigator.db.models import Base
from investigator.repository.incident_repo import SqlIncidentRepository

from datetime import datetime, timezone
from uuid import UUID


INCIDENT_ID = "dddd0000-0000-0000-0000-000000000001"


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


@pytest.fixture()
def existing_incident(client_and_repo):
    """Ingest an incident so POST /feedback has something to attach to."""
    client, _ = client_and_repo
    event = {
        "incident_id": INCIDENT_ID,
        "source": "airflow",
        "environment": "dev",
        "job_name": "cdc_orders",
        "error_type": "timeout",
        "error_message": "Job timed out",
        "timestamp": "2026-02-18T11:00:00Z",
    }
    client.post("/events/ingest", json=event)
    return INCIDENT_ID


VALID_FEEDBACK = {
    "outcome": "fixed",
    "reviewer_notes": "Applied patch and re-ran.",
    "timestamp": "2026-02-18T12:00:00Z",
}


class TestPostFeedback:
    def test_returns_201(self, client_and_repo, existing_incident):
        client, _ = client_and_repo
        resp = client.post(f"/incidents/{INCIDENT_ID}/feedback", json=VALID_FEEDBACK)
        assert resp.status_code == 201

    def test_response_has_incident_id(self, client_and_repo, existing_incident):
        client, _ = client_and_repo
        data = client.post(f"/incidents/{INCIDENT_ID}/feedback", json=VALID_FEEDBACK).json()
        assert data["incident_id"] == INCIDENT_ID

    def test_response_has_outcome(self, client_and_repo, existing_incident):
        client, _ = client_and_repo
        data = client.post(f"/incidents/{INCIDENT_ID}/feedback", json=VALID_FEEDBACK).json()
        assert data["outcome"] == "fixed"

    def test_unknown_incident_returns_404(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.post(
            "/incidents/00000000-0000-0000-0000-000000000099/feedback",
            json=VALID_FEEDBACK,
        )
        assert resp.status_code == 404

    def test_invalid_outcome_returns_422(self, client_and_repo, existing_incident):
        client, _ = client_and_repo
        resp = client.post(
            f"/incidents/{INCIDENT_ID}/feedback",
            json={**VALID_FEEDBACK, "outcome": "bad_value"},
        )
        assert resp.status_code == 422

    def test_feedback_persisted_to_db(self, client_and_repo, existing_incident):
        client, repo = client_and_repo
        client.post(f"/incidents/{INCIDENT_ID}/feedback", json=VALID_FEEDBACK)
        entries = repo.list_feedback(UUID(INCIDENT_ID))
        assert len(entries) == 1
        assert entries[0].outcome == "fixed"

    def test_optional_overrides_accepted(self, client_and_repo, existing_incident):
        client, _ = client_and_repo
        payload = {**VALID_FEEDBACK, "overrides": {"classification": "timeout"}}
        resp = client.post(f"/incidents/{INCIDENT_ID}/feedback", json=payload)
        assert resp.status_code == 201
