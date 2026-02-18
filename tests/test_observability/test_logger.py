"""Tests for the structured pipeline logger."""

import json
import logging

import pytest

from investigator.observability.logger import PipelineLogger, get_pipeline_logger


class TestGetPipelineLogger:
    def test_returns_logger(self):
        lg = get_pipeline_logger()
        assert isinstance(lg, logging.Logger)

    def test_logger_name(self):
        lg = get_pipeline_logger()
        assert lg.name == "investigator.pipeline"


class TestPipelineLogger:
    def test_step_start_emits_info(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pl.step_start("classify")
        assert any("classify" in r.message for r in caplog.records)

    def test_step_success_emits_info(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pl.step_success("classify", duration_ms=42.5, classification_type="schema_mismatch")
        records = caplog.records
        assert any("classify" in r.message for r in records)

    def test_step_success_record_has_structured_fields(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pl.step_success("diagnose", duration_ms=120.0)
        record = next(r for r in caplog.records if "diagnose" in r.message)
        assert record.__dict__.get("incident_id") == "abc-123"
        assert record.__dict__.get("step") == "diagnose"
        assert record.__dict__.get("outcome") == "success"
        assert record.__dict__.get("duration_ms") == 120.0

    def test_step_error_emits_error_level(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.ERROR, logger="investigator.pipeline"):
            pl.step_error("diagnose", error="LLM timeout", duration_ms=5000.0)
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_step_error_record_has_structured_fields(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.ERROR, logger="investigator.pipeline"):
            pl.step_error("diagnose", error="LLM timeout", duration_ms=5000.0)
        record = next(r for r in caplog.records if r.levelno == logging.ERROR)
        assert record.__dict__.get("incident_id") == "abc-123"
        assert record.__dict__.get("outcome") == "error"
        assert record.__dict__.get("error") == "LLM timeout"

    def test_pipeline_complete_emits_info(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pl.pipeline_complete(final_status="APPROVED", total_duration_ms=800.0)
        assert any("APPROVED" in r.message for r in caplog.records)

    def test_extra_kwargs_attached_to_record(self, caplog):
        pl = PipelineLogger(incident_id="abc-123")
        with caplog.at_level(logging.INFO, logger="investigator.pipeline"):
            pl.step_success("classify", duration_ms=10.0, classification_type="timeout", confidence=0.87)
        record = next(r for r in caplog.records if "classify" in r.message)
        assert record.__dict__.get("classification_type") == "timeout"
        assert record.__dict__.get("confidence") == 0.87
