"""Tests for ApprovalPolicy — deterministic approval routing."""

import pytest

from investigator.approval.policy import ApprovalPolicy, ApprovalDecision
from investigator.models.risk import ApprovalRecommendation, RiskAssessment, RiskLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk(
    score: int = 20,
    level: RiskLevel = RiskLevel.LOW,
    recommendation: ApprovalRecommendation = ApprovalRecommendation.auto_approve,
) -> RiskAssessment:
    return RiskAssessment(
        risk_score=score,
        risk_level=level,
        recommendation=recommendation,
        rationale="test",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestApprovalPolicy:
    def setup_method(self):
        self.policy = ApprovalPolicy()

    def test_returns_approval_decision(self):
        decision = self.policy.decide(risk=_risk())
        assert isinstance(decision, ApprovalDecision)

    def test_auto_approve_recommendation_gives_approved(self):
        decision = self.policy.decide(
            risk=_risk(score=10, level=RiskLevel.LOW, recommendation=ApprovalRecommendation.auto_approve)
        )
        assert decision.outcome == "approved"

    def test_human_review_recommendation_gives_pending(self):
        decision = self.policy.decide(
            risk=_risk(score=45, level=RiskLevel.MEDIUM, recommendation=ApprovalRecommendation.human_review)
        )
        assert decision.outcome == "pending"

    def test_reject_recommendation_gives_rejected(self):
        decision = self.policy.decide(
            risk=_risk(score=75, level=RiskLevel.HIGH, recommendation=ApprovalRecommendation.reject)
        )
        assert decision.outcome == "rejected"

    def test_auto_approve_has_no_required_role(self):
        decision = self.policy.decide(
            risk=_risk(recommendation=ApprovalRecommendation.auto_approve)
        )
        assert decision.required_role is None

    def test_human_review_requires_a_role(self):
        decision = self.policy.decide(
            risk=_risk(score=45, level=RiskLevel.MEDIUM, recommendation=ApprovalRecommendation.human_review)
        )
        assert decision.required_role is not None
        assert len(decision.required_role) > 0

    def test_high_risk_human_review_requires_elevated_role(self):
        medium_role = self.policy.decide(
            risk=_risk(score=45, level=RiskLevel.MEDIUM, recommendation=ApprovalRecommendation.human_review)
        ).required_role

        high_role = self.policy.decide(
            risk=_risk(score=80, level=RiskLevel.HIGH, recommendation=ApprovalRecommendation.human_review)
        ).required_role

        # HIGH incidents require a more privileged role than MEDIUM
        assert high_role != medium_role

    def test_decision_includes_rationale(self):
        decision = self.policy.decide(risk=_risk())
        assert decision.rationale and len(decision.rationale) > 0
