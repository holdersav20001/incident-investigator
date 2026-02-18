"""RemediationPlanner — LLM-backed remediation plan generation.

The planner builds a structured prompt from the incident context and
diagnosis, calls the LLM provider, and returns a validated RemediationPlan.
The plan is NEVER executed — it is proposed only and must pass the
PlanSimulator's deterministic safety checks before reaching an approver.
"""

from investigator.llm.base import LLMProvider
from investigator.models.classification import ClassificationResult
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.incident import IncidentEvent
from investigator.models.remediation import RemediationPlan

_REMEDIATION_SYSTEM = """\
You are an expert data-platform incident remediation planner.
Your task is to propose a safe, step-by-step remediation plan for a diagnosed incident.
You must respond ONLY with valid JSON matching the RemediationPlan schema.
Do NOT include any explanatory text outside the JSON object.

RemediationPlan schema:
- plan (array of PlanStep): ordered remediation steps (1-12 steps)
  - step (string): human-readable description
  - tool (string): one of: sql, vector, rest, rerun_job, notify, noop
  - command (string): tool-specific command or query
- rollback (array of RollbackStep): steps to undo if the plan fails
  - step (string): human-readable description
- expected_time_minutes (integer 1-1440): estimated total time

IMPORTANT constraints:
- SQL commands must be SELECT only (no writes, deletes, or DDL)
- Use 'noop' for steps that are informational only
- Keep the plan minimal and reversible
"""


def _build_remediation_user_prompt(
    event: IncidentEvent,
    classification: ClassificationResult,
    diagnosis: DiagnosisResult,
) -> str:
    next_checks = "\n".join(f"  - {c}" for c in (diagnosis.next_checks or []))
    return f"""\
Incident details:
  job_name: {event.job_name}
  environment: {event.environment}
  error_type: {event.error_type}
  error_message: {event.error_message}
  classification: {classification.type.value} (confidence={classification.confidence:.2f})

Diagnosis:
  root_cause: {diagnosis.root_cause}
  confidence: {diagnosis.confidence:.2f}
  suggested_next_checks:
{next_checks or "  (none)"}

Propose a RemediationPlan JSON object to resolve this incident.
"""


class RemediationPlanner:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def plan(
        self,
        *,
        event: IncidentEvent,
        classification: ClassificationResult,
        diagnosis: DiagnosisResult,
    ) -> RemediationPlan:
        """Produce a validated RemediationPlan for the given incident."""
        user_prompt = _build_remediation_user_prompt(event, classification, diagnosis)
        return self._llm.complete(
            system=_REMEDIATION_SYSTEM,
            user=user_prompt,
            response_model=RemediationPlan,
        )
