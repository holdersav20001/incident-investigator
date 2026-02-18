"""Tests that InvestigationPipeline emits structured log records at each step."""

import logging

import pytest

from investigator.state import IncidentStatus
from tests.test_workflow.conftest import make_event


class TestPipelineStructuredLogging:
    def test_pipeline_emits_log_records(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        assert len(caplog.records) > 0

    def test_classify_step_logged(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        step_names = [r.__dict__.get("step") for r in caplog.records]
        assert "classify" in step_names

    def test_diagnose_step_logged(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        step_names = [r.__dict__.get("step") for r in caplog.records]
        assert "diagnose" in step_names

    def test_all_major_steps_logged(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        step_names = {r.__dict__.get("step") for r in caplog.records}
        for expected in ("classify", "diagnose", "remediate", "risk", "approve"):
            assert expected in step_names, f"Missing step log: {expected}"

    def test_success_records_have_duration_ms(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        success_records = [r for r in caplog.records if r.__dict__.get("outcome") == "success"]
        assert len(success_records) > 0
        for r in success_records:
            assert isinstance(r.__dict__.get("duration_ms"), float)

    def test_records_carry_incident_id(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        for r in caplog.records:
            assert r.__dict__.get("incident_id") == str(event.incident_id)

    def test_pipeline_complete_logged(self, pipeline, repo, caplog):
        event = make_event(environment="dev")
        repo.create_incident(event)
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pipeline.run(incident_id=event.incident_id)
        outcomes = [r.__dict__.get("outcome") for r in caplog.records]
        assert "complete" in outcomes

    def test_llm_error_logs_error_level(self, repo, caplog):
        from investigator.approval.policy import ApprovalPolicy
        from investigator.classification.rules import RulesClassifier
        from investigator.diagnosis.engine import DiagnosisEngine
        from investigator.evidence.base import EvidenceProvider
        from investigator.llm.mock import MockLLMProvider
        from investigator.models.evidence import EvidenceRef
        from investigator.remediation.planner import RemediationPlanner
        from investigator.remediation.simulator import PlanSimulator
        from investigator.risk.engine import RiskEngine
        from investigator.workflow.pipeline import InvestigationPipeline

        class BrokenLLM(MockLLMProvider):
            def complete(self, *, system, user, response_model):
                raise RuntimeError("LLM down")

        class NullEvidence(EvidenceProvider):
            def fetch(self, *, job_name, incident_id):
                return []

        broken_llm = BrokenLLM(responses={})
        broken_pipeline = InvestigationPipeline(
            repo=repo,
            classifier=RulesClassifier(),
            evidence_provider=NullEvidence(),
            diagnosis_engine=DiagnosisEngine(llm=broken_llm),
            remediation_planner=RemediationPlanner(llm=broken_llm),
            plan_simulator=PlanSimulator(),
            risk_engine=RiskEngine(),
            approval_policy=ApprovalPolicy(),
        )
        event = make_event()
        repo.create_incident(event)
        with caplog.at_level(logging.ERROR, logger="investigator.pipeline"):
            broken_pipeline.run(incident_id=event.incident_id)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) > 0
