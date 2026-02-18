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
from sqlalchemy.orm import Session

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
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.risk.engine import RiskEngine
from investigator.workflow.pipeline import InvestigationPipeline


def _build_llm(settings: Settings) -> LLMProvider:
    """Return the configured LLM provider."""
    if settings.LLM_PROVIDER == "anthropic":
        from investigator.llm.anthropic_provider import AnthropicLLMProvider  # noqa: PLC0415
        return AnthropicLLMProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.LLM_MODEL,
        )
    # Default: mock provider (safe for CI and development)
    return MockLLMProvider(responses={})


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

    session_factory = get_session_factory(engine)
    session: Session = session_factory()

    repo = SqlIncidentRepository(session)
    metrics = MetricsRegistry()
    evidence = LocalFileEvidenceProvider(Path(s.EVIDENCE_ROOT))
    llm = _build_llm(s)

    pipeline = InvestigationPipeline(
        repo=repo,
        classifier=RulesClassifier(),
        evidence_provider=evidence,
        diagnosis_engine=DiagnosisEngine(llm),
        remediation_planner=RemediationPlanner(llm),
        plan_simulator=PlanSimulator(),
        risk_engine=RiskEngine(),
        approval_policy=ApprovalPolicy(),
    )

    return create_app(repo=repo, pipeline=pipeline, metrics=metrics)


if __name__ == "__main__":
    settings = Settings()
    app = build_app(settings)
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("PORT", "8000")),
        log_level=settings.LOG_LEVEL.lower(),
    )
