"""Agent evaluation scenarios — fixed, repeatable end-to-end pipeline runs.

Each scenario represents a realistic incident type and asserts the expected
classification, risk level, and approval outcome. These are the integration
smoke tests for the full investigation pipeline.
"""

import pytest

from investigator.approval.policy import ApprovalPolicy
from investigator.classification.rules import RulesClassifier
from investigator.diagnosis.engine import DiagnosisEngine
from investigator.llm.mock import MockLLMProvider
from investigator.models.classification import ClassificationType
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.remediation import RemediationPlan, SimCheck, SimulationReport
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.risk.engine import RiskEngine
from investigator.state import IncidentStatus
from investigator.workflow.pipeline import InvestigationPipeline
from tests.test_workflow.conftest import NullEvidenceProvider, make_event


# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------

def _safe_plan() -> RemediationPlan:
    return RemediationPlan(
        plan=[{"step": "Re-run extractor", "tool": "rerun_job", "command": "dag=cdc task=extract"}],
        rollback=[{"step": "Revert schema mapping"}],
        expected_time_minutes=15,
    )


def _safe_diagnosis(confidence: float = 0.85) -> DiagnosisResult:
    return DiagnosisResult(
        root_cause="upstream schema drift",
        evidence=[EvidenceRef(source="local_file", pointer="logs/j.log#L1", hash="sha256:abc")],
        confidence=confidence,
    )


def _make_pipeline(repo, *, diagnosis: DiagnosisResult, plan: RemediationPlan) -> InvestigationPipeline:
    llm = MockLLMProvider(responses={DiagnosisResult: diagnosis, RemediationPlan: plan})
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
# Scenario 1: Schema mismatch — dev, high confidence → LOW risk → auto_approve
# ---------------------------------------------------------------------------

class TestScenarioSchemaMismatchDev:
    """Schema mismatch in dev with high-confidence diagnosis and safe plan."""

    def test_classified_as_schema_mismatch(self, repo):
        event = make_event(
            environment="dev",
            error_type="schema_mismatch",
            error_message="Column CUSTOMER_ID missing in target",
        )
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.9), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.classification.type == ClassificationType.schema_mismatch

    def test_auto_approved_in_dev(self, repo):
        event = make_event(
            environment="dev",
            error_type="schema_mismatch",
            error_message="Column CUSTOMER_ID missing in target",
        )
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.9), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.final_status == IncidentStatus.APPROVED
        assert result.approval_decision.outcome == "approved"

    def test_risk_level_is_low(self, repo):
        event = make_event(environment="dev", error_type="schema_mismatch")
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.9), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.risk.risk_level == "LOW"


# ---------------------------------------------------------------------------
# Scenario 2: Schema mismatch — prod → MEDIUM risk → human_review
# ---------------------------------------------------------------------------

class TestScenarioSchemaMismatchProd:
    """Same incident but in prod should require human review."""

    def test_human_review_required_in_prod(self, repo):
        event = make_event(
            environment="prod",
            error_type="schema_mismatch",
            error_message="Column CUSTOMER_ID missing in target",
        )
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.85), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.final_status == IncidentStatus.APPROVAL_REQUIRED
        assert result.approval_decision.outcome == "pending"

    def test_on_call_engineer_assigned_for_medium_risk(self, repo):
        event = make_event(environment="prod", error_type="schema_mismatch")
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.85), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.approval_decision.required_role == "on_call_engineer"


# ---------------------------------------------------------------------------
# Scenario 3: Timeout — prod, high confidence → MEDIUM → human_review
# ---------------------------------------------------------------------------

class TestScenarioTimeoutProd:
    def test_classified_as_timeout(self, repo):
        event = make_event(
            environment="prod",
            error_type="timeout",
            error_message="Query timed out after 30s",
        )
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.88), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.classification.type == ClassificationType.timeout

    def test_timeout_prod_requires_approval(self, repo):
        event = make_event(environment="prod", error_type="timeout", error_message="deadline exceeded")
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.88), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.final_status == IncidentStatus.APPROVAL_REQUIRED


# ---------------------------------------------------------------------------
# Scenario 4: Unknown classification + low diagnosis confidence — HIGH risk
# ---------------------------------------------------------------------------

class TestScenarioUnknownHighRisk:
    """Unknown incident in prod with low confidence — elevated risk."""

    def test_classified_as_unknown(self, repo):
        event = make_event(
            environment="prod",
            error_type="weird_custom_error",
            error_message="Something unexpected happened",
        )
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.85), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        assert result.classification.type == ClassificationType.unknown

    def test_unknown_prod_routes_to_review(self, repo):
        event = make_event(
            environment="prod",
            error_type="weird_custom_error",
            error_message="Something unexpected happened",
        )
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.85), plan=_safe_plan())
        result = pipeline.run(incident_id=event.incident_id)
        # unknown + prod → at least MEDIUM risk
        assert result.final_status in (
            IncidentStatus.APPROVAL_REQUIRED,
            IncidentStatus.REJECTED,
        )


# ---------------------------------------------------------------------------
# Scenario 5: Unsafe remediation plan — simulation fails → reject
# ---------------------------------------------------------------------------

class TestScenarioUnsafePlan:
    """A plan containing a DELETE statement must be rejected by the simulator."""

    def test_unsafe_sql_plan_causes_rejection(self, repo):
        unsafe_plan = RemediationPlan(
            plan=[{"step": "Purge stale rows", "tool": "sql", "command": "DELETE FROM orders WHERE stale=1"}],
            rollback=[{"step": "Restore from backup"}],
            expected_time_minutes=10,
        )
        event = make_event(environment="prod", error_type="data_quality")
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.8), plan=unsafe_plan)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.simulation.ok is False
        assert result.final_status == IncidentStatus.REJECTED

    def test_unsafe_plan_risk_assessment_is_high(self, repo):
        unsafe_plan = RemediationPlan(
            plan=[{"step": "Drop index", "tool": "sql", "command": "DROP INDEX idx_orders"}],
            rollback=[{"step": "Recreate index"}],
            expected_time_minutes=5,
        )
        event = make_event(environment="prod", error_type="data_quality")
        repo.create_incident(event)
        pipeline = _make_pipeline(repo, diagnosis=_safe_diagnosis(0.8), plan=unsafe_plan)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.risk.risk_level == "HIGH"
