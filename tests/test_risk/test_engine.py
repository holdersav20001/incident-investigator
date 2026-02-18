"""Tests for RiskEngine — deterministic risk scoring."""

import pytest

from investigator.models.classification import ClassificationResult, ClassificationType
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.remediation import RemediationPlan, SimCheck, SimulationReport
from investigator.models.risk import RiskAssessment
from investigator.risk.engine import RiskEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classification(type_=ClassificationType.schema_mismatch, confidence=0.87):
    return ClassificationResult(type=type_, confidence=confidence, reason="test")


def _diagnosis(confidence=0.8):
    return DiagnosisResult(
        root_cause="upstream schema drift",
        evidence=[EvidenceRef(source="local_file", pointer="logs/j.log#L1", hash="sha256:x")],
        confidence=confidence,
    )


def _plan(time_minutes=15):
    return RemediationPlan(
        plan=[{"step": "check", "tool": "sql", "command": "SELECT 1"}],
        rollback=[{"step": "revert"}],
        expected_time_minutes=time_minutes,
    )


def _sim_ok() -> SimulationReport:
    return SimulationReport(ok=True, checks=[SimCheck(name="sql_is_select_only", ok=True)])


def _sim_fail() -> SimulationReport:
    return SimulationReport(ok=False, checks=[SimCheck(name="sql_is_select_only", ok=False)])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRiskEngine:
    def setup_method(self):
        self.engine = RiskEngine()

    def test_returns_risk_assessment(self):
        result = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        )
        assert isinstance(result, RiskAssessment)

    def test_score_in_range(self):
        result = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        )
        assert 0 <= result.risk_score <= 100

    def test_failed_simulation_raises_score(self):
        score_ok = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        ).risk_score

        score_fail = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_fail(),
            environment="prod",
        ).risk_score

        assert score_fail > score_ok

    def test_prod_higher_risk_than_dev(self):
        score_prod = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        ).risk_score

        score_dev = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="dev",
        ).risk_score

        assert score_prod >= score_dev

    def test_long_remediation_time_raises_score(self):
        score_short = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(time_minutes=5),
            simulation=_sim_ok(),
            environment="dev",
        ).risk_score

        score_long = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(time_minutes=480),
            simulation=_sim_ok(),
            environment="dev",
        ).risk_score

        assert score_long >= score_short

    def test_low_diagnosis_confidence_raises_score(self):
        score_high_conf = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(confidence=0.95),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        ).risk_score

        score_low_conf = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(confidence=0.2),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        ).risk_score

        assert score_low_conf >= score_high_conf

    def test_risk_level_high_gives_human_review_recommendation(self):
        # Force HIGH: failed sim + prod + unknown classification
        result = self.engine.assess(
            classification=_classification(type_=ClassificationType.unknown, confidence=0.1),
            diagnosis=_diagnosis(confidence=0.1),
            plan=_plan(time_minutes=1440),
            simulation=_sim_fail(),
            environment="prod",
        )
        assert result.risk_level == "HIGH"
        assert result.recommendation in ("human_review", "reject")

    def test_low_risk_can_auto_approve(self):
        result = self.engine.assess(
            classification=_classification(confidence=0.92),
            diagnosis=_diagnosis(confidence=0.9),
            plan=_plan(time_minutes=5),
            simulation=_sim_ok(),
            environment="dev",
        )
        assert result.risk_level == "LOW"
        assert result.recommendation == "auto_approve"

    def test_rationale_is_present(self):
        result = self.engine.assess(
            classification=_classification(),
            diagnosis=_diagnosis(),
            plan=_plan(),
            simulation=_sim_ok(),
            environment="prod",
        )
        assert result.rationale and len(result.rationale) > 0
