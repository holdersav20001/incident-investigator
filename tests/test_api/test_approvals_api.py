"""Tests for approval queue API endpoints.

GET  /approvals/pending             — list incidents awaiting human review
POST /approvals/{incident_id}/approve — approve
POST /approvals/{incident_id}/reject  — reject
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.api.app import create_app
from investigator.approval.policy import ApprovalPolicy
from investigator.classification.rules import RulesClassifier
from investigator.db.models import Base, IncidentRow
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
from investigator.state.machine import IncidentStatus
from investigator.workflow.pipeline import InvestigationPipeline

from datetime import datetime, timezone
from uuid import UUID


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
def client_and_repo():
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
    return TestClient(app), repo


@pytest.fixture()
def pending_incident_id(client_and_repo):
    """Ingest + investigate a prod incident so it lands in APPROVAL_REQUIRED."""
    client, repo = client_and_repo
    incident_id = "cccc0000-0000-0000-0000-000000000001"
    event = {
        "incident_id": incident_id,
        "source": "airflow",
        "environment": "prod",
        "job_name": "cdc_orders",
        "error_type": "schema_mismatch",
        "error_message": "Column CUSTOMER_ID missing",
        "timestamp": "2026-02-18T11:00:00Z",
    }
    client.post("/events/ingest", json=event)
    client.post(f"/incidents/{incident_id}/investigate")
    # Pipeline now creates the approval queue entry automatically
    return incident_id


# ---------------------------------------------------------------------------
# GET /approvals/pending
# ---------------------------------------------------------------------------

class TestGetPendingApprovals:
    def test_returns_200(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.get("/approvals/pending")
        assert resp.status_code == 200

    def test_empty_list_when_none_pending(self, client_and_repo):
        client, _ = client_and_repo
        data = client.get("/approvals/pending").json()
        assert data == []

    def test_lists_pending_item(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        data = client.get("/approvals/pending").json()
        assert len(data) == 1

    def test_item_has_incident_id(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        data = client.get("/approvals/pending").json()
        assert data[0]["incident_id"] == pending_incident_id

    def test_item_has_required_role(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        data = client.get("/approvals/pending").json()
        assert "required_role" in data[0]

    def test_item_status_is_pending(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        data = client.get("/approvals/pending").json()
        assert data[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# POST /approvals/{id}/approve
# ---------------------------------------------------------------------------

class TestApproveEndpoint:
    def test_returns_200(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        resp = client.post(
            f"/approvals/{pending_incident_id}/approve",
            json={"reviewer": "alice", "reviewer_note": "Looks safe"},
        )
        assert resp.status_code == 200

    def test_incident_transitions_to_approved(self, client_and_repo, pending_incident_id):
        client, repo = client_and_repo
        client.post(
            f"/approvals/{pending_incident_id}/approve",
            json={"reviewer": "alice", "reviewer_note": None},
        )
        from uuid import UUID as _UUID
        incident = repo.get_incident(_UUID(pending_incident_id))
        assert incident.status == IncidentStatus.APPROVED

    def test_response_has_final_status(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        data = client.post(
            f"/approvals/{pending_incident_id}/approve",
            json={"reviewer": "alice", "reviewer_note": None},
        ).json()
        assert data["status"] == "approved"

    def test_unknown_incident_returns_404(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.post(
            "/approvals/00000000-0000-0000-0000-000000000099/approve",
            json={"reviewer": "alice", "reviewer_note": None},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /approvals/{id}/reject
# ---------------------------------------------------------------------------

class TestRejectEndpoint:
    def test_returns_200(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        resp = client.post(
            f"/approvals/{pending_incident_id}/reject",
            json={"reviewer": "bob", "reviewer_note": "Too risky"},
        )
        assert resp.status_code == 200

    def test_incident_transitions_to_rejected(self, client_and_repo, pending_incident_id):
        client, repo = client_and_repo
        client.post(
            f"/approvals/{pending_incident_id}/reject",
            json={"reviewer": "bob", "reviewer_note": "Too risky"},
        )
        from uuid import UUID as _UUID
        incident = repo.get_incident(_UUID(pending_incident_id))
        assert incident.status == IncidentStatus.REJECTED

    def test_response_has_final_status(self, client_and_repo, pending_incident_id):
        client, _ = client_and_repo
        data = client.post(
            f"/approvals/{pending_incident_id}/reject",
            json={"reviewer": "bob", "reviewer_note": "Too risky"},
        ).json()
        assert data["status"] == "rejected"

    def test_unknown_incident_returns_404(self, client_and_repo):
        client, _ = client_and_repo
        resp = client.post(
            "/approvals/00000000-0000-0000-0000-000000000099/reject",
            json={"reviewer": "bob", "reviewer_note": None},
        )
        assert resp.status_code == 404
