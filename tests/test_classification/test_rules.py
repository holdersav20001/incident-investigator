"""Tests for the deterministic rules classifier."""

import pytest

from investigator.classification import RulesClassifier
from investigator.models import ClassificationType


classifier = RulesClassifier()


class TestRulesClassifier:
    def test_schema_mismatch_from_error_type(self) -> None:
        result = classifier.classify(
            error_type="schema_mismatch",
            error_message="Column CUSTOMER_ID missing in target",
        )
        assert result.type == ClassificationType.schema_mismatch
        assert result.confidence >= 0.8

    def test_schema_mismatch_from_message_keywords(self) -> None:
        result = classifier.classify(
            error_type="pipeline_error",
            error_message="schema drift detected: column count changed",
        )
        assert result.type == ClassificationType.schema_mismatch

    def test_timeout(self) -> None:
        result = classifier.classify(
            error_type="timeout",
            error_message="Job exceeded maximum allowed runtime",
        )
        assert result.type == ClassificationType.timeout

    def test_timeout_from_message(self) -> None:
        result = classifier.classify(
            error_type="generic_error",
            error_message="Connection timed out after 30 seconds",
        )
        assert result.type == ClassificationType.timeout

    def test_data_quality(self) -> None:
        result = classifier.classify(
            error_type="data_quality",
            error_message="Null values found in non-nullable column",
        )
        assert result.type == ClassificationType.data_quality

    def test_data_quality_from_message(self) -> None:
        result = classifier.classify(
            error_type="validation_error",
            error_message="duplicate records detected, data quality check failed",
        )
        assert result.type == ClassificationType.data_quality

    def test_auth(self) -> None:
        result = classifier.classify(
            error_type="auth",
            error_message="Access denied: insufficient permissions",
        )
        assert result.type == ClassificationType.auth

    def test_auth_from_message(self) -> None:
        result = classifier.classify(
            error_type="generic_error",
            error_message="401 Unauthorized — token expired",
        )
        assert result.type == ClassificationType.auth

    def test_connectivity(self) -> None:
        result = classifier.classify(
            error_type="connectivity",
            error_message="Cannot connect to database host",
        )
        assert result.type == ClassificationType.connectivity

    def test_connectivity_from_message(self) -> None:
        result = classifier.classify(
            error_type="generic_error",
            error_message="Connection refused to host db.internal:5432",
        )
        assert result.type == ClassificationType.connectivity

    def test_unknown_fallback(self) -> None:
        result = classifier.classify(
            error_type="something_weird",
            error_message="An unexpected thing happened",
        )
        assert result.type == ClassificationType.unknown
        assert result.confidence < 0.5

    def test_result_is_classification_result(self) -> None:
        from investigator.models import ClassificationResult
        result = classifier.classify(error_type="timeout", error_message="timed out")
        assert isinstance(result, ClassificationResult)

    def test_reason_is_non_empty(self) -> None:
        result = classifier.classify(error_type="timeout", error_message="timed out")
        assert len(result.reason) > 0

    def test_confidence_always_in_range(self) -> None:
        cases = [
            ("schema_mismatch", "column missing"),
            ("unknown_type", "random error"),
            ("timeout", "expired"),
            ("auth", "unauthorized"),
        ]
        for error_type, error_message in cases:
            result = classifier.classify(error_type=error_type, error_message=error_message)
            assert 0.0 <= result.confidence <= 1.0
