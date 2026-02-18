"""Tests that the generated OpenAPI spec covers all contracted routes.

FastAPI auto-generates an OpenAPI 3.x spec at /openapi.json.
These tests verify that every endpoint defined in docs/contracts.md
is present in the spec, preventing silent route regressions.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.api.app import create_app
from investigator.db.models import Base
from investigator.repository.incident_repo import SqlIncidentRepository


@pytest.fixture(scope="module")
def openapi_spec():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = SqlIncidentRepository(session)
    app = create_app(repo=repo)
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestOpenAPISpecRoutes:
    def test_spec_is_valid_json(self, openapi_spec):
        assert "openapi" in openapi_spec
        assert "paths" in openapi_spec

    def test_post_events_ingest(self, openapi_spec):
        assert "/events/ingest" in openapi_spec["paths"]
        assert "post" in openapi_spec["paths"]["/events/ingest"]

    def test_get_health(self, openapi_spec):
        assert "/health" in openapi_spec["paths"]
        assert "get" in openapi_spec["paths"]["/health"]

    def test_get_incidents_list(self, openapi_spec):
        assert "/incidents" in openapi_spec["paths"]
        assert "get" in openapi_spec["paths"]["/incidents"]

    def test_get_incident_by_id(self, openapi_spec):
        assert "/incidents/{incident_id}" in openapi_spec["paths"]
        assert "get" in openapi_spec["paths"]["/incidents/{incident_id}"]

    def test_post_investigate(self, openapi_spec):
        assert "/incidents/{incident_id}/investigate" in openapi_spec["paths"]
        assert "post" in openapi_spec["paths"]["/incidents/{incident_id}/investigate"]

    def test_post_feedback(self, openapi_spec):
        assert "/incidents/{incident_id}/feedback" in openapi_spec["paths"]
        assert "post" in openapi_spec["paths"]["/incidents/{incident_id}/feedback"]

    def test_get_approvals_pending(self, openapi_spec):
        assert "/approvals/pending" in openapi_spec["paths"]
        assert "get" in openapi_spec["paths"]["/approvals/pending"]

    def test_post_approvals_approve(self, openapi_spec):
        assert "/approvals/{incident_id}/approve" in openapi_spec["paths"]
        assert "post" in openapi_spec["paths"]["/approvals/{incident_id}/approve"]

    def test_post_approvals_reject(self, openapi_spec):
        assert "/approvals/{incident_id}/reject" in openapi_spec["paths"]
        assert "post" in openapi_spec["paths"]["/approvals/{incident_id}/reject"]

    def test_get_metrics(self, openapi_spec):
        assert "/metrics" in openapi_spec["paths"]
        assert "get" in openapi_spec["paths"]["/metrics"]


class TestOpenAPISpecSchemas:
    def test_schemas_present(self, openapi_spec):
        assert "components" in openapi_spec
        assert "schemas" in openapi_spec["components"]

    def test_ingest_response_schema(self, openapi_spec):
        schemas = openapi_spec["components"]["schemas"]
        assert "IngestResponse" in schemas

    def test_incident_response_schema(self, openapi_spec):
        schemas = openapi_spec["components"]["schemas"]
        assert "IncidentResponse" in schemas

    def test_health_response_schema(self, openapi_spec):
        schemas = openapi_spec["components"]["schemas"]
        assert "HealthResponse" in schemas
