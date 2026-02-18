"""Shared fixtures for E2E HTTP lifecycle tests.

These tests exercise the full HTTP API stack — multiple endpoints in
sequence — to validate complete investigation workflows.  The only mock
is the LLM provider; all other components (classifier, risk engine,
approval policy, state machine, DB) run unmodified.
"""

from __future__ import annotations

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


class NullEvidenceProvider(EvidenceProvider):
    def fetch(self, *, job_name: str, incident_id: str) -> list[EvidenceRef]:
        return []


# Default scripted LLM responses — safe plan, high confidence
SAFE_DIAGNOSIS = DiagnosisResult(
    root_cause="upstream schema drift in extractor",
    evidence=[EvidenceRef(source="local_file", pointer="logs/j.log#L1", hash="sha256:abc")],
    confidence=0.9,
    next_checks=["Compare source vs target schema"],
)

SAFE_PLAN = RemediationPlan(
    plan=[{"step": "Re-run extractor", "tool": "rerun_job", "command": "dag=cdc task=extract"}],
    rollback=[{"step": "Revert schema mapping"}],
    expected_time_minutes=15,
)

UNSAFE_PLAN = RemediationPlan(
    plan=[{"step": "Purge stale rows", "tool": "sql", "command": "DELETE FROM orders WHERE stale=1"}],
    rollback=[{"step": "Restore from backup"}],
    expected_time_minutes=5,
)


def _make_client(*, diagnosis: DiagnosisResult = SAFE_DIAGNOSIS, plan: RemediationPlan = SAFE_PLAN) -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = SqlIncidentRepository(session)

    llm = MockLLMProvider(responses={DiagnosisResult: diagnosis, RemediationPlan: plan})
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

    return TestClient(create_app(repo=repo, pipeline=pipeline))


@pytest.fixture()
def safe_client() -> TestClient:
    """Client wired with a safe plan and high-confidence diagnosis."""
    return _make_client()


@pytest.fixture()
def unsafe_client() -> TestClient:
    """Client wired with an unsafe (DELETE) plan to trigger rejection."""
    return _make_client(plan=UNSAFE_PLAN)


BASE_EVENT = {
    "source": "airflow",
    "job_name": "cdc_orders",
    "error_type": "schema_mismatch",
    "error_message": "Column CUSTOMER_ID missing in target",
    "timestamp": "2026-02-18T11:00:00Z",
}


def ingest(client: TestClient, *, environment: str = "dev", **overrides) -> str:
    """POST /events/ingest and return the incident_id."""
    import uuid
    body = {**BASE_EVENT, "incident_id": str(uuid.uuid4()), "environment": environment, **overrides}
    resp = client.post("/events/ingest", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["incident_id"]
