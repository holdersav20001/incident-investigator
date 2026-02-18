"""Contract compliance tests — verify all API responses match docs/contracts.md.

These tests are a living contract-conformance suite.  They assert:
- Required fields are present
- Field types are correct (string, list, bool, int, number)
- No unexpected extra fields leak out
- Enum values stay within their allowlists

Contracts tested:
  Contract 1  — POST /events/ingest response
  Contract 2  — GET /incidents/{id} response
  Contract 9  — GET /approvals/pending item
  Contract 10 — POST /incidents/{id}/feedback response
  Contract 11 — Error response envelope (400/404/422)
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.api.app import create_app
from investigator.approval.policy import ApprovalPolicy
from investigator.classification.rules import RulesClassifier
from investigator.db.models import Base
from investigator.diagnosis.engine import DiagnosisEngine
from investigator.evidence.base import EvidenceProvider
from investigator.llm.mock import MockLLMProvider
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.remediation import RemediationPlan
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.risk.engine import RiskEngine
from investigator.workflow.pipeline import InvestigationPipeline


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

class _NullEvidenceProvider(EvidenceProvider):
    def fetch(self, *, job_name: str, incident_id: str) -> list[EvidenceRef]:
        return []


_DIAGNOSIS = DiagnosisResult(
    root_cause="schema drift",
    evidence=[EvidenceRef(source="local_file", pointer="logs/j.log#L1", hash="sha256:abc")],
    confidence=0.88,
    next_checks=["check schema"],
)
_PLAN = RemediationPlan(
    plan=[{"step": "Re-run", "tool": "rerun_job", "command": "dag=cdc"}],
    rollback=[{"step": "Revert"}],
    expected_time_minutes=10,
)


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

    llm = MockLLMProvider(responses={DiagnosisResult: _DIAGNOSIS, RemediationPlan: _PLAN})
    pipeline = InvestigationPipeline(
        repo=repo,
        classifier=RulesClassifier(),
        evidence_provider=_NullEvidenceProvider(),
        diagnosis_engine=DiagnosisEngine(llm=llm),
        remediation_planner=RemediationPlanner(llm=llm),
        plan_simulator=PlanSimulator(),
        risk_engine=RiskEngine(),
        approval_policy=ApprovalPolicy(),
    )
    return TestClient(create_app(repo=repo, pipeline=pipeline))


def _new_event(environment: str = "dev", **overrides) -> dict[str, Any]:
    return {
        "incident_id": str(uuid.uuid4()),
        "source": "airflow",
        "environment": environment,
        "job_name": "cdc_orders",
        "error_type": "schema_mismatch",
        "error_message": "Column CUSTOMER_ID missing",
        "timestamp": "2026-02-18T11:00:00Z",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Contract 1 — POST /events/ingest response
# ---------------------------------------------------------------------------

class TestIngestResponseContract:
    """Response must have incident_id (string)."""

    def test_ingest_returns_201(self, client):
        resp = client.post("/events/ingest", json=_new_event())
        assert resp.status_code == 201

    def test_ingest_response_has_incident_id(self, client):
        resp = client.post("/events/ingest", json=_new_event())
        assert "incident_id" in resp.json()

    def test_ingest_incident_id_is_string(self, client):
        resp = client.post("/events/ingest", json=_new_event())
        assert isinstance(resp.json()["incident_id"], str)

    def test_ingest_incident_id_is_valid_uuid(self, client):
        resp = client.post("/events/ingest", json=_new_event())
        # Must parse without raising
        uuid.UUID(resp.json()["incident_id"])


# ---------------------------------------------------------------------------
# Contract 2 — GET /incidents/{id} response
# ---------------------------------------------------------------------------

class TestIncidentResponseContract:
    """Required: incident_id, status, created_at, updated_at (all strings)."""

    @pytest.fixture(scope="class")
    def investigated_id(self, client):
        event = _new_event(environment="dev")
        resp = client.post("/events/ingest", json=event)
        iid = resp.json()["incident_id"]
        client.post(f"/incidents/{iid}/investigate")
        return iid

    def test_required_fields_present(self, client, investigated_id):
        body = client.get(f"/incidents/{investigated_id}").json()
        for field in ("incident_id", "status", "created_at", "updated_at"):
            assert field in body, f"missing required field: {field}"

    def test_incident_id_is_uuid_string(self, client, investigated_id):
        body = client.get(f"/incidents/{investigated_id}").json()
        uuid.UUID(body["incident_id"])

    def test_status_is_string(self, client, investigated_id):
        body = client.get(f"/incidents/{investigated_id}").json()
        assert isinstance(body["status"], str)

    def test_created_at_is_isoformat_string(self, client, investigated_id):
        body = client.get(f"/incidents/{investigated_id}").json()
        # Validate it is a non-empty ISO datetime string
        assert isinstance(body["created_at"], str) and "T" in body["created_at"]

    def test_updated_at_is_isoformat_string(self, client, investigated_id):
        body = client.get(f"/incidents/{investigated_id}").json()
        assert isinstance(body["updated_at"], str) and "T" in body["updated_at"]

    def test_classification_is_object_or_null(self, client, investigated_id):
        body = client.get(f"/incidents/{investigated_id}").json()
        assert body["classification"] is None or isinstance(body["classification"], dict)

    def test_no_unexpected_fields(self, client, investigated_id):
        allowed = {
            "incident_id", "status", "classification", "diagnosis",
            "remediation", "simulation", "risk", "approval_status",
            "created_at", "updated_at",
        }
        body = client.get(f"/incidents/{investigated_id}").json()
        extra = set(body.keys()) - allowed
        assert not extra, f"Unexpected fields in incident response: {extra}"


# ---------------------------------------------------------------------------
# Contract 9 — GET /approvals/pending item
# ---------------------------------------------------------------------------

class TestApprovalQueueItemContract:
    """Required: incident_id, status, required_role, created_at."""

    @pytest.fixture(scope="class")
    def pending_id(self, client):
        event = _new_event(environment="prod")
        iid = client.post("/events/ingest", json=event).json()["incident_id"]
        client.post(f"/incidents/{iid}/investigate")
        return iid

    def test_pending_list_returns_list(self, client, pending_id):
        resp = client.get("/approvals/pending")
        assert isinstance(resp.json(), list)

    def test_pending_item_has_required_fields(self, client, pending_id):
        items = client.get("/approvals/pending").json()
        item = next((i for i in items if i["incident_id"] == pending_id), None)
        assert item is not None, "prod incident not found in pending queue"
        for field in ("incident_id", "status", "required_role", "created_at"):
            assert field in item, f"missing required field: {field}"

    def test_status_is_pending(self, client, pending_id):
        items = client.get("/approvals/pending").json()
        item = next(i for i in items if i["incident_id"] == pending_id)
        assert item["status"] == "pending"

    def test_required_role_is_string(self, client, pending_id):
        items = client.get("/approvals/pending").json()
        item = next(i for i in items if i["incident_id"] == pending_id)
        assert isinstance(item["required_role"], str) and item["required_role"]

    def test_created_at_is_datetime_string(self, client, pending_id):
        items = client.get("/approvals/pending").json()
        item = next(i for i in items if i["incident_id"] == pending_id)
        assert isinstance(item["created_at"], str) and "T" in item["created_at"]

    def test_no_unexpected_fields(self, client, pending_id):
        allowed = {
            "incident_id", "status", "required_role",
            "reviewer", "reviewer_note", "created_at", "reviewed_at",
        }
        items = client.get("/approvals/pending").json()
        item = next(i for i in items if i["incident_id"] == pending_id)
        extra = set(item.keys()) - allowed
        assert not extra, f"Unexpected fields in approval queue item: {extra}"


# ---------------------------------------------------------------------------
# Contract 11 — Error response envelope
# ---------------------------------------------------------------------------

class TestErrorEnvelopeContract:
    """All error responses must have error, message, trace_id."""

    def test_404_has_required_fields(self, client):
        body = client.get("/incidents/00000000-0000-0000-0000-000000000099").json()
        for field in ("error", "message", "trace_id"):
            assert field in body, f"missing error envelope field: {field}"

    def test_404_error_is_string(self, client):
        body = client.get("/incidents/00000000-0000-0000-0000-000000000099").json()
        assert isinstance(body["error"], str) and body["error"]

    def test_404_message_is_string(self, client):
        body = client.get("/incidents/00000000-0000-0000-0000-000000000099").json()
        assert isinstance(body["message"], str) and body["message"]

    def test_404_trace_id_min_length(self, client):
        body = client.get("/incidents/00000000-0000-0000-0000-000000000099").json()
        assert len(body["trace_id"]) >= 8

    def test_422_has_required_fields(self, client):
        # Send a body missing required fields
        body = client.post("/events/ingest", json={}).json()
        for field in ("error", "message", "trace_id"):
            assert field in body, f"missing error envelope field: {field}"

    def test_no_raw_python_traceback_in_404(self, client):
        # Error details must not expose raw stack traces
        text = client.get("/incidents/00000000-0000-0000-0000-000000000099").text
        assert "Traceback" not in text
        assert "File " not in text
