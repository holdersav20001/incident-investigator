"""InvestigationPipeline — the central orchestrator.

Executes the full Classify → Diagnose → Remediate → Simulate → Risk →
Approve sequence, persisting state and artefacts after every step so the
pipeline is resumable if interrupted.

Design principles:
- Each step guards on the current status before running — idempotent re-runs
  will skip already-completed steps.
- Every state transition goes through the state machine (via the repository).
- LLM calls are isolated in DiagnosisEngine and RemediationPlanner;
  all other steps are deterministic.
- On any exception the pipeline halts, sets PipelineResult.error, and
  returns the partial result — the incident stays at its last good status.
"""

from __future__ import annotations

import time
from uuid import UUID

from investigator.approval.policy import ApprovalDecision, ApprovalPolicy
from investigator.classification.rules import RulesClassifier
from investigator.diagnosis.engine import DiagnosisEngine
from investigator.evidence.base import EvidenceProvider
from investigator.models.classification import ClassificationResult
from investigator.models.diagnosis import DiagnosisResult
from investigator.models.incident import IncidentEvent
from investigator.models.remediation import RemediationPlan, SimulationReport
from investigator.models.risk import RiskAssessment
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.risk.engine import RiskEngine
from investigator.observability.logger import PipelineLogger
from investigator.observability.metrics import MetricsRegistry
from investigator.state import IncidentStatus
from investigator.workflow.result import PipelineResult


class InvestigationPipeline:
    def __init__(
        self,
        *,
        repo: SqlIncidentRepository,
        classifier: RulesClassifier,
        evidence_provider: EvidenceProvider,
        diagnosis_engine: DiagnosisEngine,
        remediation_planner: RemediationPlanner,
        plan_simulator: PlanSimulator,
        risk_engine: RiskEngine,
        approval_policy: ApprovalPolicy,
    ) -> None:
        self._repo = repo
        self._classifier = classifier
        self._evidence_provider = evidence_provider
        self._diagnosis_engine = diagnosis_engine
        self._remediation_planner = remediation_planner
        self._plan_simulator = plan_simulator
        self._risk_engine = risk_engine
        self._approval_policy = approval_policy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        incident_id: UUID,
        metrics: MetricsRegistry | None = None,
    ) -> PipelineResult:
        """Run (or resume) the investigation pipeline for the given incident.

        Returns a PipelineResult capturing every step's output.
        If any step fails the result carries `error` and the incident
        retains its last successfully-persisted status.

        Pass a MetricsRegistry to record pipeline counters and step durations.
        """
        row = self._repo.get_incident(incident_id)
        if row is None:
            raise LookupError(f"Incident {incident_id} not found")

        # Reconstruct IncidentEvent from persisted row data
        event = IncidentEvent(
            incident_id=incident_id,
            source=row.source,
            environment=row.environment,
            job_name=row.job_name,
            error_type=row.error_type,
            error_message=row.error_message,
            timestamp=row.event_timestamp,
            metadata=row.raw_metadata,
        )

        status = IncidentStatus(row.status)
        result = PipelineResult(incident_id=incident_id, final_status=status)

        # Re-hydrate any artefacts already persisted (for resumability)
        if row.classification:
            result.classification = ClassificationResult.model_validate(row.classification)
        if row.diagnosis:
            result.diagnosis = DiagnosisResult.model_validate(row.diagnosis)
        if row.remediation and row.simulation:
            result.remediation = RemediationPlan.model_validate(row.remediation)
            result.simulation = SimulationReport.model_validate(row.simulation)
        if row.risk:
            result.risk = RiskAssessment.model_validate(row.risk)

        pl = PipelineLogger(incident_id=str(incident_id))
        t_pipeline = time.perf_counter()
        current_step = "unknown"
        t_step = t_pipeline

        if metrics:
            metrics.counter("pipeline_runs_total").inc()

        try:
            for step_name, step_fn in [
                ("classify",  lambda r: self._step_classify(r, event)),
                ("diagnose",  lambda r: self._step_diagnose(r, event)),
                ("remediate", lambda r: self._step_remediate(r, event)),
                ("risk",      lambda r: self._step_risk(r, event)),
                ("approve",   lambda r: self._step_approve(r)),
            ]:
                current_step = step_name
                pl.step_start(step_name)
                t_step = time.perf_counter()
                result = step_fn(result)
                duration_ms = (time.perf_counter() - t_step) * 1000
                pl.step_success(step_name, duration_ms=duration_ms)
                if metrics:
                    metrics.histogram("pipeline_step_duration_ms").observe(duration_ms)

        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            pl.step_error(
                current_step,
                error=str(exc),
                duration_ms=(time.perf_counter() - t_step) * 1000,
            )
            if metrics:
                metrics.counter("pipeline_errors_total").inc()

        total_ms = (time.perf_counter() - t_pipeline) * 1000
        pl.pipeline_complete(
            final_status=result.final_status,
            total_duration_ms=total_ms,
        )
        if metrics:
            metrics.histogram("pipeline_total_duration_ms").observe(total_ms)
            metrics.counter("pipeline_final_status_total").inc(
                labels={"status": result.final_status}
            )
        return result

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _step_classify(self, result: PipelineResult, event: IncidentEvent) -> PipelineResult:
        if result.final_status != IncidentStatus.RECEIVED:
            return result

        classification = self._classifier.classify(
            error_type=event.error_type,
            error_message=event.error_message,
        )
        self._repo.update_classification(result.incident_id, classification.model_dump())
        self._repo.record_transition(
            result.incident_id,
            IncidentStatus.RECEIVED,
            IncidentStatus.CLASSIFIED,
            actor="pipeline",
        )
        result.classification = classification
        result.final_status = IncidentStatus.CLASSIFIED
        return result

    def _step_diagnose(self, result: PipelineResult, event: IncidentEvent) -> PipelineResult:
        if result.final_status != IncidentStatus.CLASSIFIED:
            return result

        evidence = self._evidence_provider.fetch(
            job_name=event.job_name,
            incident_id=str(result.incident_id),
        )
        assert result.classification is not None  # guaranteed by _step_classify
        diagnosis = self._diagnosis_engine.diagnose(
            event=event,
            classification=result.classification,
            evidence=evidence,
        )
        self._repo.update_diagnosis(result.incident_id, diagnosis.model_dump())
        self._repo.record_transition(
            result.incident_id,
            IncidentStatus.CLASSIFIED,
            IncidentStatus.DIAGNOSED,
            actor="pipeline",
        )
        result.diagnosis = diagnosis
        result.final_status = IncidentStatus.DIAGNOSED
        return result

    def _step_remediate(self, result: PipelineResult, event: IncidentEvent) -> PipelineResult:
        if result.final_status != IncidentStatus.DIAGNOSED:
            return result

        assert result.classification is not None
        assert result.diagnosis is not None
        remediation = self._remediation_planner.plan(
            event=event,
            classification=result.classification,
            diagnosis=result.diagnosis,
        )
        simulation = self._plan_simulator.simulate(remediation)
        self._repo.update_remediation(
            result.incident_id,
            remediation.model_dump(),
            simulation.model_dump(),
        )
        self._repo.record_transition(
            result.incident_id,
            IncidentStatus.DIAGNOSED,
            IncidentStatus.REMEDIATION_PROPOSED,
            actor="pipeline",
        )
        result.remediation = remediation
        result.simulation = simulation
        result.final_status = IncidentStatus.REMEDIATION_PROPOSED
        return result

    def _step_risk(self, result: PipelineResult, event: IncidentEvent) -> PipelineResult:
        if result.final_status != IncidentStatus.REMEDIATION_PROPOSED:
            return result

        assert result.classification is not None
        assert result.diagnosis is not None
        assert result.remediation is not None
        assert result.simulation is not None
        risk = self._risk_engine.assess(
            classification=result.classification,
            diagnosis=result.diagnosis,
            plan=result.remediation,
            simulation=result.simulation,
            environment=event.environment,
        )
        self._repo.update_risk(result.incident_id, risk.model_dump())
        self._repo.record_transition(
            result.incident_id,
            IncidentStatus.REMEDIATION_PROPOSED,
            IncidentStatus.RISK_ASSESSED,
            actor="pipeline",
        )
        result.risk = risk
        result.final_status = IncidentStatus.RISK_ASSESSED
        return result

    def _step_approve(self, result: PipelineResult) -> PipelineResult:
        if result.final_status != IncidentStatus.RISK_ASSESSED:
            return result

        assert result.risk is not None
        decision = self._approval_policy.decide(risk=result.risk)
        result.approval_decision = decision

        if decision.outcome == "approved":
            self._repo.record_transition(
                result.incident_id,
                IncidentStatus.RISK_ASSESSED,
                IncidentStatus.APPROVED,
                actor="pipeline",
            )
            self._repo.update_approval_status(result.incident_id, "approved")
            result.final_status = IncidentStatus.APPROVED

        elif decision.outcome == "rejected":
            # Route through APPROVAL_REQUIRED → REJECTED so the audit trail
            # reflects policy review, and humans can override before it settles.
            self._repo.record_transition(
                result.incident_id,
                IncidentStatus.RISK_ASSESSED,
                IncidentStatus.APPROVAL_REQUIRED,
                actor="pipeline",
            )
            self._repo.record_transition(
                result.incident_id,
                IncidentStatus.APPROVAL_REQUIRED,
                IncidentStatus.REJECTED,
                actor="pipeline:auto_reject",
            )
            self._repo.update_approval_status(result.incident_id, "rejected")
            result.final_status = IncidentStatus.REJECTED

        else:  # pending / human_review
            self._repo.record_transition(
                result.incident_id,
                IncidentStatus.RISK_ASSESSED,
                IncidentStatus.APPROVAL_REQUIRED,
                actor="pipeline",
            )
            self._repo.update_approval_status(
                result.incident_id, f"pending:{decision.required_role}"
            )
            self._repo.create_approval_queue_item(
                result.incident_id,
                required_role=decision.required_role or "on_call_engineer",
            )
            result.final_status = IncidentStatus.APPROVAL_REQUIRED

        return result
