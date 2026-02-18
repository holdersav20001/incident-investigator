"""Tests for RiskAssessment model."""

import pytest
from pydantic import ValidationError

from investigator.models import RiskAssessment, RiskLevel, ApprovalRecommendation


class TestRiskAssessment:
    def test_valid(self) -> None:
        r = RiskAssessment(
            risk_score=72,
            risk_level=RiskLevel.HIGH,
            recommendation=ApprovalRecommendation.human_review,
        )
        assert r.blast_radius == []

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_score=101,
                risk_level=RiskLevel.LOW,
                recommendation=ApprovalRecommendation.auto_approve,
            )
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_score=-1,
                risk_level=RiskLevel.LOW,
                recommendation=ApprovalRecommendation.auto_approve,
            )

    def test_blast_radius_max(self) -> None:
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_score=50,
                risk_level=RiskLevel.MEDIUM,
                recommendation=ApprovalRecommendation.human_review,
                blast_radius=["table"] * 201,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_score=50,
                risk_level=RiskLevel.MEDIUM,
                recommendation=ApprovalRecommendation.human_review,
                oops="field",
            )
