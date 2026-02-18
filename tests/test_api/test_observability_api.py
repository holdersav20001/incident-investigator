"""Tests for observability API endpoints: GET /metrics and GET /health (enhanced)."""

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
from investigator.observability.metrics import MetricsRegistry
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.risk.engine import RiskEngine
from investigator.workflow.pipeline import InvestigationPipeline


# ---------------------------------------------------------------------------
# Fixtures
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
def client_with_metrics():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    repo = SqlIncidentRepository(session)
    metrics = MetricsRegistry()

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

    app = create_app(repo=repo, pipeline=pipeline, metrics=metrics)
    return TestClient(app), metrics


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    def test_returns_200(self, client_with_metrics):
        client, _ = client_with_metrics
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_response_has_counters_key(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/metrics").json()
        assert "counters" in data

    def test_response_has_histograms_key(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/metrics").json()
        assert "histograms" in data

    def test_pipeline_runs_counter_present_after_run(self, client_with_metrics):
        client, _ = client_with_metrics
        # Ingest then investigate
        event = {
            "incident_id": "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
            "source": "airflow",
            "environment": "dev",
            "job_name": "cdc_orders",
            "error_type": "schema_mismatch",
            "error_message": "Column CUSTOMER_ID missing",
            "timestamp": "2026-02-18T11:00:00Z",
        }
        client.post("/events/ingest", json=event)
        client.post("/incidents/7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010/investigate")
        data = client.get("/metrics").json()
        assert "pipeline_runs_total" in data["counters"]

    def test_step_duration_histogram_present_after_run(self, client_with_metrics):
        client, _ = client_with_metrics
        event = {
            "incident_id": "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
            "source": "airflow",
            "environment": "dev",
            "job_name": "cdc_orders",
            "error_type": "schema_mismatch",
            "error_message": "Column CUSTOMER_ID missing",
            "timestamp": "2026-02-18T11:00:00Z",
        }
        client.post("/events/ingest", json=event)
        client.post("/incidents/7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010/investigate")
        data = client.get("/metrics").json()
        assert "pipeline_step_duration_ms" in data["histograms"]


# ---------------------------------------------------------------------------
# GET /health (enhanced)
# ---------------------------------------------------------------------------

class TestEnhancedHealthEndpoint:
    def test_returns_200(self, client_with_metrics):
        client, _ = client_with_metrics
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_response_has_status(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/health").json()
        assert "status" in data

    def test_response_has_db_key(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/health").json()
        assert "db" in data

    def test_db_is_ok(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/health").json()
        assert data["db"] == "ok"

    def test_response_has_slos_key(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/health").json()
        assert "slos" in data

    def test_slos_list_present(self, client_with_metrics):
        client, _ = client_with_metrics
        data = client.get("/health").json()
        assert isinstance(data["slos"], list)
        assert len(data["slos"]) > 0
