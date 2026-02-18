"""Structured pipeline logger.

Emits structured log records with per-step context fields attached as
`LogRecord` extras so downstream handlers (JSON formatters, log shippers)
can index them without parsing the message string.

Usage:
    pl = PipelineLogger(incident_id="abc-123")
    pl.step_start("classify")
    pl.step_success("classify", duration_ms=42.5, classification_type="schema_mismatch")
    pl.step_error("diagnose", error="LLM timeout", duration_ms=5000.0)
    pl.pipeline_complete(final_status="APPROVED", total_duration_ms=800.0)
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER_NAME = "investigator.pipeline"


def get_pipeline_logger() -> logging.Logger:
    """Return the shared pipeline logger (creates it if it doesn't exist)."""
    return logging.getLogger(_LOGGER_NAME)


class PipelineLogger:
    """Context-bound structured logger for a single pipeline run.

    All records emitted carry `incident_id` as a structured field so log
    queries can filter by incident without regex parsing.
    """

    def __init__(self, incident_id: str) -> None:
        self._incident_id = incident_id
        self._logger = get_pipeline_logger()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def step_start(self, step: str, **extra: Any) -> None:
        self._emit(
            level=logging.INFO,
            message=f"step_start step={step}",
            step=step,
            outcome="start",
            **extra,
        )

    def step_success(self, step: str, *, duration_ms: float, **extra: Any) -> None:
        self._emit(
            level=logging.INFO,
            message=f"step_success step={step} duration_ms={duration_ms:.1f}",
            step=step,
            outcome="success",
            duration_ms=duration_ms,
            **extra,
        )

    def step_error(self, step: str, *, error: str, duration_ms: float, **extra: Any) -> None:
        self._emit(
            level=logging.ERROR,
            message=f"step_error step={step} error={error!r} duration_ms={duration_ms:.1f}",
            step=step,
            outcome="error",
            duration_ms=duration_ms,
            error=error,
            **extra,
        )

    def pipeline_complete(self, *, final_status: str, total_duration_ms: float, **extra: Any) -> None:
        self._emit(
            level=logging.INFO,
            message=f"pipeline_complete final_status={final_status} total_duration_ms={total_duration_ms:.1f}",
            step="pipeline",
            outcome="complete",
            final_status=final_status,
            total_duration_ms=total_duration_ms,
            **extra,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, *, level: int, message: str, **fields: Any) -> None:
        """Emit a log record with structured extras attached."""
        extra = {"incident_id": self._incident_id, **fields}
        self._logger.log(level, message, extra=extra)
