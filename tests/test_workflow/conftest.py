"""Shared fixtures for workflow pipeline tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
# DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


@pytest.fixture()
def repo(session):
    return SqlIncidentRepository(session)


# ---------------------------------------------------------------------------
# Scripted LLM responses
# ---------------------------------------------------------------------------

SCRIPTED_DIAGNOSIS = DiagnosisResult(
    root_cause="upstream schema drift in extractor",
    evidence=[EvidenceRef(source="local_file", pointer="logs/j.log#L1", hash="sha256:abc")],
    confidence=0.85,
    next_checks=["Compare source vs target schema"],
)

SCRIPTED_PLAN = RemediationPlan(
    plan=[{"step": "Re-run extractor", "tool": "rerun_job", "command": "dag=cdc task=extract"}],
    rollback=[{"step": "Revert schema mapping"}],
    expected_time_minutes=20,
)


class NullEvidenceProvider(EvidenceProvider):
    """Returns no evidence — for fast unit tests that don't need log files."""

    def fetch(self, *, job_name: str, incident_id: str) -> list[EvidenceRef]:
        return []


def make_llm_provider() -> MockLLMProvider:
    return MockLLMProvider(
        responses={
            DiagnosisResult: SCRIPTED_DIAGNOSIS,
            RemediationPlan: SCRIPTED_PLAN,
        }
    )


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------

@pytest.fixture()
def pipeline(repo):
    llm = make_llm_provider()
    return InvestigationPipeline(
        repo=repo,
        classifier=RulesClassifier(),
        evidence_provider=NullEvidenceProvider(),
        diagnosis_engine=DiagnosisEngine(llm=llm),
        remediation_planner=RemediationPlanner(llm=llm),
        plan_simulator=PlanSimulator(),
        risk_engine=RiskEngine(),
        approval_policy=ApprovalPolicy(),
    )


# ---------------------------------------------------------------------------
# Incident helpers
# ---------------------------------------------------------------------------

VALID_EVENT_BASE = dict(
    source="airflow",
    environment="dev",
    job_name="cdc_orders",
    error_type="schema_mismatch",
    error_message="Column CUSTOMER_ID missing in target",
    timestamp="2026-02-18T11:00:00Z",
)


def make_event(**overrides) -> IncidentEvent:
    from uuid import uuid4
    data = {**VALID_EVENT_BASE, "incident_id": str(uuid4()), **overrides}
    return IncidentEvent.model_validate(data)
