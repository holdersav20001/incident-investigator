"""Tests for pipeline fault-tolerance — partial runs, error capture, resumability."""

import pytest

from investigator.approval.policy import ApprovalPolicy
from investigator.classification.rules import RulesClassifier
from investigator.diagnosis.engine import DiagnosisEngine
from investigator.evidence.base import EvidenceProvider
from investigator.llm.mock import MockLLMProvider
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.remediation import RemediationPlan
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.risk.engine import RiskEngine
from investigator.state import IncidentStatus
from investigator.workflow.pipeline import InvestigationPipeline
from tests.test_workflow.conftest import (
    NullEvidenceProvider,
    SCRIPTED_DIAGNOSIS,
    SCRIPTED_PLAN,
    make_event,
)


# ---------------------------------------------------------------------------
# Broken LLM provider — raises on complete()
# ---------------------------------------------------------------------------

class BrokenLLMProvider(MockLLMProvider):
    def complete(self, *, system, user, response_model):
        raise RuntimeError("LLM service unavailable")


def make_broken_pipeline(repo) -> InvestigationPipeline:
    broken_llm = BrokenLLMProvider(responses={})
    return InvestigationPipeline(
        repo=repo,
        classifier=RulesClassifier(),
        evidence_provider=NullEvidenceProvider(),
        diagnosis_engine=DiagnosisEngine(llm=broken_llm),
        remediation_planner=RemediationPlanner(llm=broken_llm),
        plan_simulator=PlanSimulator(),
        risk_engine=RiskEngine(),
        approval_policy=ApprovalPolicy(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipelineFaultTolerance:
    def test_llm_failure_returns_result_not_exception(self, pipeline, repo):
        """A broken LLM should not propagate an exception — return partial result."""
        event = make_event()
        repo.create_incident(event)
        broken = make_broken_pipeline(repo)
        result = broken.run(incident_id=event.incident_id)
        # Result is returned, not raised
        assert result is not None

    def test_llm_failure_sets_error_field(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        broken = make_broken_pipeline(repo)
        result = broken.run(incident_id=event.incident_id)
        assert result.error is not None
        assert len(result.error) > 0

    def test_llm_failure_incident_stays_at_classified(self, pipeline, repo):
        """After classify succeeds but diagnose fails, incident should be CLASSIFIED."""
        event = make_event()
        repo.create_incident(event)
        broken = make_broken_pipeline(repo)
        result = broken.run(incident_id=event.incident_id)
        # classify (deterministic) succeeded; diagnose (LLM) failed
        assert result.final_status == IncidentStatus.CLASSIFIED

    def test_classification_populated_before_llm_failure(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        broken = make_broken_pipeline(repo)
        result = broken.run(incident_id=event.incident_id)
        assert result.classification is not None

    def test_diagnosis_none_after_llm_failure(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        broken = make_broken_pipeline(repo)
        result = broken.run(incident_id=event.incident_id)
        assert result.diagnosis is None

    def test_db_status_preserved_after_failure(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        broken = make_broken_pipeline(repo)
        broken.run(incident_id=event.incident_id)
        row = repo.get_incident(event.incident_id)
        assert row.status == IncidentStatus.CLASSIFIED

    def test_resumable_from_classified(self, pipeline, repo):
        """Running the good pipeline on a CLASSIFIED incident skips classify and finishes."""
        event = make_event(environment="dev")
        repo.create_incident(event)
        # First run with broken LLM — stops at CLASSIFIED
        broken = make_broken_pipeline(repo)
        partial = broken.run(incident_id=event.incident_id)
        assert partial.final_status == IncidentStatus.CLASSIFIED

        # Second run with working pipeline — should complete from CLASSIFIED
        result = pipeline.run(incident_id=event.incident_id)
        assert result.final_status in (
            IncidentStatus.APPROVED,
            IncidentStatus.APPROVAL_REQUIRED,
            IncidentStatus.REJECTED,
        )
        assert result.error is None
