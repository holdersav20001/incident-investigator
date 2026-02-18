"""PipelineResult — typed output of a complete or partial pipeline run.

Each field is Optional; a None value means that step was not reached
(either because the incident was already past that step, or because
an earlier step failed and populated `error`).
"""

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from investigator.approval.policy import ApprovalDecision
from investigator.models.classification import ClassificationResult
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.remediation import RemediationPlan, SimulationReport
from investigator.models.risk import RiskAssessment
from investigator.state import IncidentStatus


@dataclass
class PipelineResult:
    incident_id: UUID
    final_status: IncidentStatus

    classification: Optional[ClassificationResult] = field(default=None)
    diagnosis: Optional[DiagnosisResult] = field(default=None)
    remediation: Optional[RemediationPlan] = field(default=None)
    simulation: Optional[SimulationReport] = field(default=None)
    risk: Optional[RiskAssessment] = field(default=None)
    approval_decision: Optional[ApprovalDecision] = field(default=None)

    # Populated when a step raises an unexpected exception.
    # The incident stays at `final_status` (last successful step).
    error: Optional[str] = field(default=None)
