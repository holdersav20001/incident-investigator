"""Tests for InvestigationPipeline — happy path and state progression."""

import pytest

from investigator.state import IncidentStatus
from investigator.workflow.result import PipelineResult
from tests.test_workflow.conftest import make_event


class TestPipelineHappyPath:
    def test_returns_pipeline_result(self, pipeline, repo):
        event = make_event(environment="dev")
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert isinstance(result, PipelineResult)

    def test_final_status_is_terminal(self, pipeline, repo):
        event = make_event(environment="dev")
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.final_status in (
            IncidentStatus.APPROVED,
            IncidentStatus.APPROVAL_REQUIRED,
            IncidentStatus.REJECTED,
        )

    def test_incident_db_status_matches_result(self, pipeline, repo):
        event = make_event(environment="dev")
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        row = repo.get_incident(event.incident_id)
        assert row.status == result.final_status

    def test_classification_is_populated(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.classification is not None

    def test_diagnosis_is_populated(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.diagnosis is not None

    def test_remediation_is_populated(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.remediation is not None

    def test_simulation_is_populated(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.simulation is not None

    def test_risk_is_populated(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.risk is not None

    def test_approval_decision_is_populated(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.approval_decision is not None

    def test_no_error_on_happy_path(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.error is None

    def test_classification_persisted_to_db(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        pipeline.run(incident_id=event.incident_id)
        row = repo.get_incident(event.incident_id)
        assert row.classification is not None

    def test_diagnosis_persisted_to_db(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        pipeline.run(incident_id=event.incident_id)
        row = repo.get_incident(event.incident_id)
        assert row.diagnosis is not None

    def test_transition_audit_trail_recorded(self, pipeline, repo):
        event = make_event()
        repo.create_incident(event)
        pipeline.run(incident_id=event.incident_id)
        transitions = repo.get_transitions(event.incident_id)
        # At minimum: RECEIVED→CLASSIFIED, CLASSIFIED→DIAGNOSED, etc.
        assert len(transitions) >= 4

    def test_dev_low_risk_auto_approves(self, pipeline, repo):
        # dev + schema_mismatch + high-confidence LLM + safe plan → LOW risk → auto_approve
        event = make_event(environment="dev", error_type="schema_mismatch")
        repo.create_incident(event)
        result = pipeline.run(incident_id=event.incident_id)
        assert result.final_status == IncidentStatus.APPROVED

    def test_unknown_incident_raises(self, pipeline):
        from uuid import uuid4
        with pytest.raises(LookupError):
            pipeline.run(incident_id=uuid4())
