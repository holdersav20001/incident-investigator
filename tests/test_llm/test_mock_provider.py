"""Tests for MockLLMProvider — the CI-safe, scripted LLM stub."""

import pytest

from investigator.llm.mock import MockLLMProvider
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.remediation import RemediationPlan
from investigator.models.evidence import EvidenceRef


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DIAGNOSIS = DiagnosisResult(
    root_cause="schema drift in upstream extractor",
    evidence=[
        EvidenceRef(source="local_file", pointer="logs/job.log#L1", hash="sha256:abc")
    ],
    confidence=0.82,
    next_checks=["Check schema changelog"],
)

_PLAN = RemediationPlan(
    plan=[
        {"step": "Re-run extractor", "tool": "rerun_job", "command": "dag=foo task=extract"}
    ],
    rollback=[{"step": "Revert mapping"}],
    expected_time_minutes=15,
)


class TestMockLLMProvider:
    def test_returns_scripted_diagnosis(self):
        provider = MockLLMProvider(responses={DiagnosisResult: _DIAGNOSIS})
        result = provider.complete(
            system="You are an incident investigator.",
            user="Diagnose this incident.",
            response_model=DiagnosisResult,
        )
        assert result == _DIAGNOSIS

    def test_returns_scripted_plan(self):
        provider = MockLLMProvider(responses={RemediationPlan: _PLAN})
        result = provider.complete(
            system="You are a remediation planner.",
            user="Propose a plan.",
            response_model=RemediationPlan,
        )
        assert result == _PLAN

    def test_raises_if_no_scripted_response(self):
        provider = MockLLMProvider(responses={})
        with pytest.raises(KeyError):
            provider.complete(
                system="s",
                user="u",
                response_model=DiagnosisResult,
            )

    def test_multiple_calls_return_same_response(self):
        provider = MockLLMProvider(responses={DiagnosisResult: _DIAGNOSIS})
        r1 = provider.complete(system="s", user="u", response_model=DiagnosisResult)
        r2 = provider.complete(system="s", user="u", response_model=DiagnosisResult)
        assert r1 == r2

    def test_call_log_records_prompts(self):
        provider = MockLLMProvider(responses={DiagnosisResult: _DIAGNOSIS})
        provider.complete(system="sys", user="usr", response_model=DiagnosisResult)
        assert len(provider.calls) == 1
        assert provider.calls[0]["system"] == "sys"
        assert provider.calls[0]["user"] == "usr"
        assert provider.calls[0]["response_model"] is DiagnosisResult
