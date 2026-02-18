"""Tests for investigation API endpoints."""

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
from investigator.models.incident import IncidentEvent
from investigator.models.remediation import RemediationPlan
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.risk.engine import RiskEngine
from investigator.workflow.pipeline import InvestigationPipeline


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

DIAGNOSIS = DiagnosisResult(
    root_cause="schema drift",
    evidence=[EvidenceRef(source="local_file", pointer="logs/j.log#L1", hash="sha256:abc")],
    confidence=0.85,
)
PLAN = RemediationPlan(
    plan=[{"step": "Re-run", "tool": "rerun_job", "command": "dag=cdc task=extract"}],
    rollback=[{"step": "Revert"}],
    expected_time_minutes=10,
)


class NullEvidenceProvider(EvidenceProvider):
    def fetch(self, *, job_name, incident_id):
        return []


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = SqlIncidentRepository(session)

    llm = MockLLMProvider(responses={DiagnosisResult: DIAGNOSIS, RemediationPlan: PLAN})
    pipeline = InvestigationPipeline(
        repo=repo,
        classifier=RulesClassifier(),
        evidence_provider=NullEvidenceProvider(),
        diagnosis_engine=DiagnosisEngine(llm=llm),
        remediation_planner=RemediationPlanner(llm=llm),
        plan_simulator=PlanSimulator(),
        risk_engine=RiskEngine(),
        approval_policy=ApprovalPolicy(),
    )

    app = create_app(repo=repo, pipeline=pipeline)
    return TestClient(app)


VALID_EVENT = {
    "incident_id": "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
    "source": "airflow",
    "environment": "dev",
    "job_name": "cdc_orders",
    "error_type": "schema_mismatch",
    "error_message": "Column CUSTOMER_ID missing",
    "timestamp": "2026-02-18T11:00:00Z",
}


def _ingest_and_get_id(client) -> str:
    resp = client.post("/events/ingest", json=VALID_EVENT)
    assert resp.status_code == 201
    return resp.json()["incident_id"]


# ---------------------------------------------------------------------------
# POST /incidents/{id}/investigate
# ---------------------------------------------------------------------------

class TestInvestigateEndpoint:
    def test_returns_200(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.post(f"/incidents/{iid}/investigate")
        assert resp.status_code == 200

    def test_response_contains_incident_id(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.post(f"/incidents/{iid}/investigate")
        assert resp.json()["incident_id"] == iid

    def test_response_contains_final_status(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.post(f"/incidents/{iid}/investigate")
        assert "final_status" in resp.json()

    def test_dev_incident_auto_approved(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.post(f"/incidents/{iid}/investigate")
        assert resp.json()["final_status"] == "APPROVED"

    def test_unknown_incident_returns_404(self, client):
        resp = client.post("/incidents/00000000-0000-0000-0000-000000000000/investigate")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /incidents/{id}
# ---------------------------------------------------------------------------

class TestGetIncidentEndpoint:
    def test_returns_200_after_ingest(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.get(f"/incidents/{iid}")
        assert resp.status_code == 200

    def test_response_has_incident_id(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.get(f"/incidents/{iid}")
        assert resp.json()["incident_id"] == iid

    def test_response_has_status(self, client):
        iid = _ingest_and_get_id(client)
        resp = client.get(f"/incidents/{iid}")
        assert resp.json()["status"] == "RECEIVED"

    def test_status_updated_after_investigation(self, client):
        iid = _ingest_and_get_id(client)
        client.post(f"/incidents/{iid}/investigate")
        resp = client.get(f"/incidents/{iid}")
        assert resp.json()["status"] == "APPROVED"

    def test_classification_present_after_investigation(self, client):
        iid = _ingest_and_get_id(client)
        client.post(f"/incidents/{iid}/investigate")
        resp = client.get(f"/incidents/{iid}")
        assert resp.json()["classification"] is not None

    def test_unknown_incident_returns_404(self, client):
        resp = client.get("/incidents/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
