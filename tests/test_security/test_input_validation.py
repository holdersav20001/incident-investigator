"""Security tests — input validation, boundary conditions, and error safety.

These tests verify that the API:
1. Enforces input length limits (Pydantic max_length constraints)
2. Safely handles special characters without injection
3. Does not leak internal Python details in error responses
4. Rejects path traversal attempts in the evidence provider
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.api.app import create_app
from investigator.db.models import Base
from investigator.evidence.local_file import LocalFileEvidenceProvider
from investigator.repository.incident_repo import SqlIncidentRepository


# ---------------------------------------------------------------------------
# Test client fixture (no pipeline needed — ingest-only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = SqlIncidentRepository(session)
    return TestClient(create_app(repo=repo))


def _event(**overrides) -> dict:
    return {
        "incident_id": str(uuid.uuid4()),
        "source": "airflow",
        "environment": "dev",
        "job_name": "cdc_orders",
        "error_type": "timeout",
        "error_message": "Query exceeded time limit",
        "timestamp": "2026-02-18T11:00:00Z",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Input length enforcement
# ---------------------------------------------------------------------------

class TestInputLengthLimits:
    def test_job_name_at_max_length_accepted(self, client):
        # max_length=200 per contracts.md
        resp = client.post("/events/ingest", json=_event(job_name="a" * 200))
        assert resp.status_code == 201

    def test_job_name_over_max_length_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(job_name="a" * 201))
        assert resp.status_code == 422

    def test_error_message_at_max_length_accepted(self, client):
        # max_length=4000 per contracts.md
        resp = client.post("/events/ingest", json=_event(error_message="x" * 4000))
        assert resp.status_code == 201

    def test_error_message_over_max_length_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(error_message="x" * 4001))
        assert resp.status_code == 422

    def test_error_type_at_max_length_accepted(self, client):
        # max_length=100 per contracts.md
        resp = client.post("/events/ingest", json=_event(error_type="e" * 100))
        assert resp.status_code == 201

    def test_error_type_over_max_length_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(error_type="e" * 101))
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------

class TestEnumValidation:
    def test_invalid_source_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(source="unknown_source"))
        assert resp.status_code == 422

    def test_invalid_environment_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(environment="local"))
        assert resp.status_code == 422

    def test_valid_sources_accepted(self, client):
        for src in ("airflow", "cloudwatch", "manual", "other"):
            resp = client.post("/events/ingest", json=_event(source=src))
            assert resp.status_code == 201, f"source={src} should be accepted"

    def test_valid_environments_accepted(self, client):
        for env in ("prod", "staging", "dev"):
            resp = client.post("/events/ingest", json=_event(environment=env))
            assert resp.status_code == 201, f"environment={env} should be accepted"


# ---------------------------------------------------------------------------
# Empty / missing required fields
# ---------------------------------------------------------------------------

class TestRequiredFieldValidation:
    def test_empty_body_rejected(self, client):
        resp = client.post("/events/ingest", json={})
        assert resp.status_code == 422

    def test_missing_incident_id_rejected(self, client):
        body = {k: v for k, v in _event().items() if k != "incident_id"}
        resp = client.post("/events/ingest", json=body)
        assert resp.status_code == 422

    def test_empty_job_name_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(job_name=""))
        assert resp.status_code == 422

    def test_empty_error_message_rejected(self, client):
        resp = client.post("/events/ingest", json=_event(error_message=""))
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Special characters — must be handled safely (no injection)
# ---------------------------------------------------------------------------

class TestSpecialCharacterHandling:
    def test_sql_chars_in_job_name_accepted(self, client):
        # SQLAlchemy uses parameterized queries — SQL metacharacters must not
        # cause errors, they should be stored as-is.
        resp = client.post(
            "/events/ingest",
            json=_event(job_name="job'; DROP TABLE incidents; --"),
        )
        # Pydantic passes it through; ORM handles it safely
        assert resp.status_code == 201

    def test_unicode_in_error_message_accepted(self, client):
        resp = client.post(
            "/events/ingest",
            json=_event(error_message="错误: 列 CUSTOMER_ID 缺失 ñoño 🔥"),
        )
        assert resp.status_code == 201

    def test_html_tags_in_error_message_accepted(self, client):
        # The API is JSON-only — HTML is just stored text, never rendered
        resp = client.post(
            "/events/ingest",
            json=_event(error_message="<script>alert(1)</script> error"),
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Error response safety — no internal detail leakage
# ---------------------------------------------------------------------------

class TestErrorResponseSafety:
    def test_404_does_not_expose_stack_trace(self, client):
        text = client.get("/incidents/00000000-0000-0000-0000-000000000000").text
        assert "Traceback" not in text
        assert "File " not in text

    def test_422_does_not_expose_stack_trace(self, client):
        text = client.post("/events/ingest", json={}).text
        assert "Traceback" not in text

    def test_404_uses_error_envelope(self, client):
        body = client.get("/incidents/00000000-0000-0000-0000-000000000000").json()
        assert "error" in body
        assert "message" in body
        assert "trace_id" in body

    def test_duplicate_ingest_returns_409_with_envelope(self, client):
        event = _event()
        client.post("/events/ingest", json=event)
        resp = client.post("/events/ingest", json=event)
        assert resp.status_code == 409
        body = resp.json()
        assert "error" in body
        assert "trace_id" in body


# ---------------------------------------------------------------------------
# Path traversal — LocalFileEvidenceProvider
# ---------------------------------------------------------------------------

class TestPathTraversalPrevention:
    def test_normal_job_name_returns_empty_when_no_logs(self, tmp_path):
        provider = LocalFileEvidenceProvider(root=tmp_path)
        refs = provider.fetch(job_name="my_job", incident_id="abc")
        assert refs == []

    def test_path_traversal_dot_dot_slash_blocked(self, tmp_path):
        # Create a sensitive file outside the root that traversal would reach
        sensitive = tmp_path.parent / "sensitive.log"
        sensitive.write_text("SECRET_DATA")

        provider = LocalFileEvidenceProvider(root=tmp_path)
        refs = provider.fetch(job_name="../sensitive_dir", incident_id="abc")
        assert refs == []

    def test_absolute_path_as_job_name_blocked(self, tmp_path):
        provider = LocalFileEvidenceProvider(root=tmp_path)
        refs = provider.fetch(job_name="/etc/passwd", incident_id="abc")
        assert refs == []

    def test_deeply_nested_traversal_blocked(self, tmp_path):
        provider = LocalFileEvidenceProvider(root=tmp_path)
        refs = provider.fetch(job_name="../../../../../../etc", incident_id="abc")
        assert refs == []

    def test_valid_subdirectory_with_logs_returned(self, tmp_path):
        job_dir = tmp_path / "cdc_orders"
        job_dir.mkdir()
        (job_dir / "run.log").write_text("Error: timeout after 30s")

        provider = LocalFileEvidenceProvider(root=tmp_path)
        refs = provider.fetch(job_name="cdc_orders", incident_id="abc")
        assert len(refs) == 1
        assert refs[0].pointer == "cdc_orders/run.log"
