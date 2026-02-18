"""Tests for ClassificationResult model."""

import pytest
from pydantic import ValidationError

from investigator.models import ClassificationResult, ClassificationType


class TestClassificationResult:
    def test_valid(self) -> None:
        result = ClassificationResult(
            type=ClassificationType.schema_mismatch,
            confidence=0.87,
            reason="Detected keywords: column missing, schema drift",
        )
        assert result.confidence == 0.87

    def test_confidence_out_of_range_high(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(type=ClassificationType.unknown, confidence=1.1, reason="x")

    def test_confidence_out_of_range_low(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(type=ClassificationType.unknown, confidence=-0.1, reason="x")

    def test_confidence_boundary_values(self) -> None:
        ClassificationResult(type=ClassificationType.unknown, confidence=0.0, reason="x")
        ClassificationResult(type=ClassificationType.unknown, confidence=1.0, reason="x")

    def test_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(type="not_a_type", confidence=0.5, reason="x")

    def test_all_types_valid(self) -> None:
        for t in ClassificationType:
            ClassificationResult(type=t, confidence=0.5, reason="test")

    def test_reason_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(
                type=ClassificationType.unknown,
                confidence=0.5,
                reason="x" * 1001,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(
                type=ClassificationType.unknown,
                confidence=0.5,
                reason="x",
                extra="oops",
            )
