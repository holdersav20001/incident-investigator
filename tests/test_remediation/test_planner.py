"""Tests for RemediationPlanner — LLM-backed plan generation."""

from investigator.llm.mock import MockLLMProvider
from investigator.models.classification import ClassificationResult, ClassificationType
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.incident import IncidentEvent
from investigator.models.remediation import RemediationPlan
from investigator.remediation.planner import RemediationPlanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PLAN = RemediationPlan(
    plan=[
        {"step": "Re-run extractor", "tool": "rerun_job", "command": "dag=cdc task=extract"}
    ],
    rollback=[{"step": "Revert schema mapping"}],
    expected_time_minutes=20,
)

_DIAGNOSIS = DiagnosisResult(
    root_cause="schema drift in upstream extractor",
    evidence=[
        EvidenceRef(source="local_file", pointer="logs/job.log#L1", hash="sha256:abc")
    ],
    confidence=0.82,
)

_EVENT = IncidentEvent(
    incident_id="7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
    source="airflow",
    environment="prod",
    job_name="cdc_orders",
    error_type="schema_mismatch",
    error_message="Column CUSTOMER_ID missing",
    timestamp="2026-02-18T11:00:00Z",
)

_CLASSIFICATION = ClassificationResult(
    type=ClassificationType.schema_mismatch,
    confidence=0.87,
    reason="Keyword match",
)


def _make_provider() -> MockLLMProvider:
    return MockLLMProvider(responses={RemediationPlan: _PLAN})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRemediationPlanner:
    def test_returns_remediation_plan(self):
        planner = RemediationPlanner(llm=_make_provider())
        result = planner.plan(
            event=_EVENT,
            classification=_CLASSIFICATION,
            diagnosis=_DIAGNOSIS,
        )
        assert isinstance(result, RemediationPlan)

    def test_returns_scripted_plan(self):
        planner = RemediationPlanner(llm=_make_provider())
        result = planner.plan(
            event=_EVENT,
            classification=_CLASSIFICATION,
            diagnosis=_DIAGNOSIS,
        )
        assert result == _PLAN

    def test_calls_llm_exactly_once(self):
        provider = _make_provider()
        planner = RemediationPlanner(llm=provider)
        planner.plan(event=_EVENT, classification=_CLASSIFICATION, diagnosis=_DIAGNOSIS)
        assert len(provider.calls) == 1

    def test_system_prompt_mentions_remediation(self):
        provider = _make_provider()
        planner = RemediationPlanner(llm=provider)
        planner.plan(event=_EVENT, classification=_CLASSIFICATION, diagnosis=_DIAGNOSIS)
        assert "remediat" in provider.calls[0]["system"].lower()

    def test_user_prompt_contains_root_cause(self):
        provider = _make_provider()
        planner = RemediationPlanner(llm=provider)
        planner.plan(event=_EVENT, classification=_CLASSIFICATION, diagnosis=_DIAGNOSIS)
        assert "schema drift" in provider.calls[0]["user"]

    def test_user_prompt_contains_job_name(self):
        provider = _make_provider()
        planner = RemediationPlanner(llm=provider)
        planner.plan(event=_EVENT, classification=_CLASSIFICATION, diagnosis=_DIAGNOSIS)
        assert "cdc_orders" in provider.calls[0]["user"]
