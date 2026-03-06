"""Production entrypoint — wires the full application stack and starts uvicorn.

Usage:
    python main.py                             # development (SQLite, mock LLM)
    APP_ENV=production \\
      DATABASE_URL=postgresql://... \\
      LLM_PROVIDER=anthropic \\
      ANTHROPIC_API_KEY=sk-ant-... \\
      python main.py

In production, prefer running via the Docker image:
    docker compose up
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn

from investigator.api.app import create_app
from investigator.approval.policy import ApprovalPolicy
from investigator.classification.rules import RulesClassifier
from investigator.config import Settings
from investigator.db.models import Base
from investigator.db.session import get_engine, get_session_factory
from investigator.diagnosis.engine import DiagnosisEngine
from investigator.evidence.local_file import LocalFileEvidenceProvider
from investigator.llm.base import LLMProvider
from investigator.llm.mock import MockLLMProvider
from investigator.observability.metrics import MetricsRegistry
from investigator.remediation.planner import RemediationPlanner
from investigator.remediation.simulator import PlanSimulator
from investigator.risk.engine import RiskEngine


def _build_llm(settings: Settings) -> LLMProvider:
    """Return the configured LLM provider."""
    if settings.LLM_PROVIDER == "anthropic":
        from investigator.llm.anthropic_provider import AnthropicLLMProvider  # noqa: PLC0415
        return AnthropicLLMProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.LLM_MODEL,
        )
    if settings.LLM_PROVIDER == "openrouter":
        from investigator.llm.openrouter_provider import OpenRouterLLMProvider  # noqa: PLC0415
        return OpenRouterLLMProvider(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_MODEL,
        )
    # Default: mock provider with plausible stub responses so the full
    # pipeline completes end-to-end without an API key.  Set
    # LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY for real AI analysis.
    from investigator.models.diagnosis import DiagnosisResult  # noqa: PLC0415
    from investigator.models.remediation import (  # noqa: PLC0415
        PlanStep, PlanTool, RemediationPlan, RollbackStep,
    )
    mock_diagnosis = DiagnosisResult(
        root_cause=(
            "Automated diagnosis unavailable (mock LLM). "
            "Set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY for AI-powered root-cause analysis."
        ),
        evidence=[],
        confidence=0.5,
        next_checks=[
            "Review job logs for the full stack trace",
            "Check upstream data sources for recent schema changes",
            "Verify pipeline configuration and dependency versions",
        ],
    )
    mock_remediation = RemediationPlan(
        plan=[
            PlanStep(
                step="Notify on-call engineer of the incident",
                tool=PlanTool.notify,
                command="notify oncall 'Incident requires manual investigation'",
            ),
            PlanStep(
                step="Review and triage job logs",
                tool=PlanTool.rerun_job,
                command="rerun_job --dry-run --verbose",
            ),
        ],
        rollback=[RollbackStep(step="No automated rollback — manual review required")],
        expected_time_minutes=30,
    )
    return MockLLMProvider(responses={
        DiagnosisResult: mock_diagnosis,
        RemediationPlan: mock_remediation,
    })


def build_app(settings: Settings | None = None):
    """Build the FastAPI app with all production dependencies wired.

    Accepts an optional Settings instance for testability.
    """
    s = settings or Settings()

    logging.basicConfig(
        level=s.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    engine = get_engine(s.DATABASE_URL)
    # create_all is idempotent — for development convenience.
    # In production, schema is managed by Alembic: `alembic upgrade head`
    Base.metadata.create_all(engine)

    sf = get_session_factory(engine)
    metrics = MetricsRegistry()
    evidence = LocalFileEvidenceProvider(Path(s.EVIDENCE_ROOT))
    llm = _build_llm(s)

    # Store pipeline components — the pipeline itself is assembled per-request
    # with a fresh repo (per-request session) by the investigate route.
    pipeline_components = {
        "classifier": RulesClassifier(),
        "evidence_provider": evidence,
        "diagnosis_engine": DiagnosisEngine(llm),
        "remediation_planner": RemediationPlanner(llm),
        "plan_simulator": PlanSimulator(),
        "risk_engine": RiskEngine(),
        "approval_policy": ApprovalPolicy(),
    }

    return create_app(
        session_factory=sf,
        pipeline_components=pipeline_components,
        metrics=metrics,
    )


if __name__ == "__main__":
    settings = Settings()
    app = build_app(settings)
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("PORT", "8000")),
        log_level=settings.LOG_LEVEL.lower(),
    )
