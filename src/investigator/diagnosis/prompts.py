"""Prompt builders for the diagnosis engine.

Prompts are extracted here so they can be reviewed, tested, and versioned
independently of the engine wiring.
"""

from investigator.models.classification import ClassificationResult
from investigator.models.evidence import EvidenceRef
from investigator.models.incident import IncidentEvent

_DIAGNOSIS_SYSTEM = """\
You are an expert data-platform incident investigator.
Your task is to diagnose the root cause of a data pipeline incident.
You must respond ONLY with valid JSON matching the DiagnosisResult schema.
Do NOT include any explanatory text outside the JSON object.

DiagnosisResult schema:
- root_cause (string): concise technical description of the root cause
- evidence (array of EvidenceRef): supporting evidence from the logs provided
- confidence (float 0-1): your confidence in the diagnosis
- next_checks (array of strings, optional): suggested follow-up checks
"""


def build_diagnosis_user_prompt(
    event: IncidentEvent,
    classification: ClassificationResult,
    evidence: list[EvidenceRef],
) -> str:
    evidence_block = "\n".join(
        f"  [{i+1}] pointer={ref.pointer} snippet={ref.snippet or '(none)'}"
        for i, ref in enumerate(evidence)
    ) or "  (no evidence available)"

    return f"""\
Incident details:
  job_name: {event.job_name}
  environment: {event.environment}
  error_type: {event.error_type}
  error_message: {event.error_message}
  timestamp: {event.timestamp.isoformat()}
  classification: {classification.type.value} (confidence={classification.confidence:.2f})
  classification_reason: {classification.reason}

Evidence:
{evidence_block}

Diagnose the root cause and return a DiagnosisResult JSON object.
"""
