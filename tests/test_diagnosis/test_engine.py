"""Tests for DiagnosisEngine — LLM-backed root-cause analysis."""

import pytest

from investigator.diagnosis.engine import DiagnosisEngine
from investigator.llm.mock import MockLLMProvider
from investigator.models.classification import ClassificationResult, ClassificationType
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.incident import IncidentEvent


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_event(**overrides) -> IncidentEvent:
    base = dict(
        incident_id="7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
        source="airflow",
        environment="prod",
        job_name="cdc_orders",
        error_type="schema_mismatch",
        error_message="Column CUSTOMER_ID missing in target",
        timestamp="2026-02-18T11:00:00Z",
    )
    base.update(overrides)
    return IncidentEvent(**base)


def _make_classification(**overrides) -> ClassificationResult:
    base = dict(
        type=ClassificationType.schema_mismatch,
        confidence=0.87,
        reason="Keyword match: schema_mismatch",
    )
    base.update(overrides)
    return ClassificationResult(**base)


_EVIDENCE = [
    EvidenceRef(
        source="local_file",
        pointer="logs/cdc_orders/2026-02-18/run_1.log#L1",
        snippet="Error: Column CUSTOMER_ID missing",
        hash="sha256:abc123",
    )
]

_SCRIPTED_DIAGNOSIS = DiagnosisResult(
    root_cause="schema drift in upstream extractor",
    evidence=_EVIDENCE,
    confidence=0.82,
    next_checks=["Compare source schema vs target"],
)


def _make_provider() -> MockLLMProvider:
    return MockLLMProvider(responses={DiagnosisResult: _SCRIPTED_DIAGNOSIS})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiagnosisEngine:
    def test_returns_diagnosis_result(self):
        engine = DiagnosisEngine(llm=_make_provider())
        result = engine.diagnose(
            event=_make_event(),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        assert isinstance(result, DiagnosisResult)

    def test_returns_scripted_llm_result(self):
        engine = DiagnosisEngine(llm=_make_provider())
        result = engine.diagnose(
            event=_make_event(),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        assert result == _SCRIPTED_DIAGNOSIS

    def test_calls_llm_exactly_once(self):
        provider = _make_provider()
        engine = DiagnosisEngine(llm=provider)
        engine.diagnose(
            event=_make_event(),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        assert len(provider.calls) == 1

    def test_system_prompt_mentions_diagnosis(self):
        provider = _make_provider()
        engine = DiagnosisEngine(llm=provider)
        engine.diagnose(
            event=_make_event(),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        system = provider.calls[0]["system"].lower()
        assert "diagnos" in system

    def test_user_prompt_contains_job_name(self):
        provider = _make_provider()
        engine = DiagnosisEngine(llm=provider)
        engine.diagnose(
            event=_make_event(job_name="my_special_job"),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        user = provider.calls[0]["user"]
        assert "my_special_job" in user

    def test_user_prompt_contains_error_message(self):
        provider = _make_provider()
        engine = DiagnosisEngine(llm=provider)
        engine.diagnose(
            event=_make_event(error_message="Column XYZ missing"),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        user = provider.calls[0]["user"]
        assert "Column XYZ missing" in user

    def test_user_prompt_contains_classification_type(self):
        provider = _make_provider()
        engine = DiagnosisEngine(llm=provider)
        engine.diagnose(
            event=_make_event(),
            classification=_make_classification(type=ClassificationType.timeout),
            evidence=_EVIDENCE,
        )
        user = provider.calls[0]["user"]
        assert "timeout" in user.lower()

    def test_user_prompt_contains_evidence_snippet(self):
        provider = _make_provider()
        engine = DiagnosisEngine(llm=provider)
        engine.diagnose(
            event=_make_event(),
            classification=_make_classification(),
            evidence=_EVIDENCE,
        )
        user = provider.calls[0]["user"]
        assert "CUSTOMER_ID" in user

    def test_works_with_no_evidence(self):
        engine = DiagnosisEngine(llm=_make_provider())
        result = engine.diagnose(
            event=_make_event(),
            classification=_make_classification(),
            evidence=[],
        )
        assert isinstance(result, DiagnosisResult)
