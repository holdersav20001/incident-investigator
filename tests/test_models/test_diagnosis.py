"""Tests for DiagnosisResult model."""

import pytest
from pydantic import ValidationError

from investigator.models import DiagnosisResult, EvidenceRef, EvidenceSource


VALID_EVIDENCE = {
    "source": "local_file",
    "pointer": "logs/run_123.log",
    "hash": "sha256:abc",
}


class TestDiagnosisResult:
    def test_valid_minimal(self) -> None:
        result = DiagnosisResult(
            root_cause="schema drift in upstream extractor",
            evidence=[EvidenceRef.model_validate(VALID_EVIDENCE)],
            confidence=0.78,
        )
        assert result.next_checks == []

    def test_valid_full(self) -> None:
        result = DiagnosisResult(
            root_cause="timeout in downstream job",
            evidence=[EvidenceRef.model_validate(VALID_EVIDENCE)],
            confidence=0.9,
            next_checks=["Check resource limits", "Review logs"],
        )
        assert len(result.next_checks) == 2

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DiagnosisResult(
                root_cause="x",
                evidence=[EvidenceRef.model_validate(VALID_EVIDENCE)],
                confidence=1.5,
            )

    def test_too_many_evidence_items(self) -> None:
        items = [EvidenceRef.model_validate(VALID_EVIDENCE) for _ in range(11)]
        with pytest.raises(ValidationError):
            DiagnosisResult(root_cause="x", evidence=items, confidence=0.5)

    def test_too_many_next_checks(self) -> None:
        with pytest.raises(ValidationError):
            DiagnosisResult(
                root_cause="x",
                evidence=[],
                confidence=0.5,
                next_checks=["check"] * 11,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiagnosisResult(
                root_cause="x",
                evidence=[],
                confidence=0.5,
                unexpected="oops",
            )
