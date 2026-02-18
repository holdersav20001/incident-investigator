"""ApprovalPolicy — deterministic approval routing.

Maps a RiskAssessment → ApprovalDecision with no LLM involvement.
All routing rules are explicit and code-reviewed.

Role assignments:
  MEDIUM risk → "on_call_engineer"
  HIGH risk   → "data_platform_lead"
"""

from dataclasses import dataclass
from typing import Optional

from investigator.models.risk import ApprovalRecommendation, RiskAssessment, RiskLevel

# Role constants — changing these is a code-reviewed decision
_ROLE_MEDIUM = "on_call_engineer"
_ROLE_HIGH = "data_platform_lead"


@dataclass(frozen=True)
class ApprovalDecision:
    outcome: str          # "approved" | "pending" | "rejected"
    required_role: Optional[str]  # None for auto-approved/rejected
    rationale: str


class ApprovalPolicy:
    """Route an incident to approval, auto-approve, or reject.

    The policy is deterministic: same RiskAssessment → same decision.
    """

    def decide(self, *, risk: RiskAssessment) -> ApprovalDecision:
        rec = risk.recommendation

        if rec == ApprovalRecommendation.auto_approve:
            return ApprovalDecision(
                outcome="approved",
                required_role=None,
                rationale=f"Auto-approved: risk_score={risk.risk_score}, level={risk.risk_level}",
            )

        if rec == ApprovalRecommendation.reject:
            return ApprovalDecision(
                outcome="rejected",
                required_role=None,
                rationale=f"Rejected by policy: risk_score={risk.risk_score}, level={risk.risk_level}",
            )

        # human_review — assign role based on risk level
        role = _ROLE_HIGH if risk.risk_level == RiskLevel.HIGH else _ROLE_MEDIUM
        return ApprovalDecision(
            outcome="pending",
            required_role=role,
            rationale=(
                f"Queued for human review: risk_score={risk.risk_score}, "
                f"level={risk.risk_level}, required_role={role}"
            ),
        )
