"""RiskEngine — deterministic risk scoring.

Scoring is explicit and auditable. Every factor is a named contribution
that can be traced in the rationale string.

Scoring factors (each contributes points to risk_score 0–100):
  - simulation failed:              +40
  - production environment:         +30  (≥MEDIUM alone — prod always gets a human look)
  - staging environment:            +10
  - low diagnosis confidence (<0.5):+15
  - long remediation time (>60m):   +10
  - unknown classification:         +10

Risk level thresholds:
  LOW    0–29   → auto_approve
  MEDIUM 30–59  → human_review
  HIGH   60–100 → human_review (or reject if simulation failed)
"""

from investigator.models.classification import ClassificationResult, ClassificationType
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.remediation import RemediationPlan, SimulationReport
from investigator.models.risk import ApprovalRecommendation, RiskAssessment, RiskLevel


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


class RiskEngine:
    """Compute a deterministic RiskAssessment from incident context."""

    def assess(
        self,
        *,
        classification: ClassificationResult,
        diagnosis: DiagnosisResult,
        plan: RemediationPlan,
        simulation: SimulationReport,
        environment: str,
    ) -> RiskAssessment:
        score = 0
        factors: list[str] = []

        # Simulation safety gate — biggest single factor
        if not simulation.ok:
            score += 40
            factors.append("simulation_failed(+40)")

        # Environment weight
        env = environment.lower()
        if env == "prod":
            score += 30
            factors.append("env=prod(+30)")
        elif env == "staging":
            score += 10
            factors.append("env=staging(+10)")

        # Diagnosis confidence (high confidence → better understood → lower risk)
        if diagnosis.confidence < 0.5:
            score += 15
            factors.append(f"low_diagnosis_confidence={diagnosis.confidence:.2f}(+15)")

        # Remediation complexity proxy
        if plan.expected_time_minutes > 60:
            score += 10
            factors.append(f"long_remediation={plan.expected_time_minutes}m(+10)")

        # Unknown classification means we don't fully understand the incident
        if classification.type == ClassificationType.unknown:
            score += 10
            factors.append("classification=unknown(+10)")

        score = _clamp(score)

        if score < 30:
            level = RiskLevel.LOW
            recommendation = ApprovalRecommendation.auto_approve
        elif score < 60:
            level = RiskLevel.MEDIUM
            recommendation = ApprovalRecommendation.human_review
        else:
            level = RiskLevel.HIGH
            # Reject only if simulation also failed (we know the plan is unsafe)
            recommendation = (
                ApprovalRecommendation.reject
                if not simulation.ok
                else ApprovalRecommendation.human_review
            )

        rationale = f"score={score}: " + ", ".join(factors) if factors else f"score={score}: no risk factors"

        return RiskAssessment(
            risk_score=score,
            risk_level=level,
            recommendation=recommendation,
            rationale=rationale,
        )
