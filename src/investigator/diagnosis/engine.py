"""DiagnosisEngine — orchestrates LLM-backed root-cause analysis.

The engine builds structured prompts from incident context and evidence,
calls the LLM provider, and returns a validated DiagnosisResult.
All validation is handled by Pydantic; the LLM only proposes.
"""

from investigator.diagnosis.prompts import (
    _DIAGNOSIS_SYSTEM,
    build_diagnosis_user_prompt,
)
from investigator.llm.base import LLMProvider
from investigator.models.classification import ClassificationResult
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.evidence import EvidenceRef
from investigator.models.incident import IncidentEvent


class DiagnosisEngine:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def diagnose(
        self,
        *,
        event: IncidentEvent,
        classification: ClassificationResult,
        evidence: list[EvidenceRef],
    ) -> DiagnosisResult:
        """Produce a validated DiagnosisResult for the given incident."""
        user_prompt = build_diagnosis_user_prompt(event, classification, evidence)
        return self._llm.complete(
            system=_DIAGNOSIS_SYSTEM,
            user=user_prompt,
            response_model=DiagnosisResult,
        )
