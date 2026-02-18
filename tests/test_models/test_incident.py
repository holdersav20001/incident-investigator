"""Tests for IncidentEvent and IncidentRecord models."""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from investigator.models import IncidentEvent, IncidentRecord


VALID_EVENT = {
    "incident_id": "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
    "source": "airflow",
    "environment": "prod",
    "job_name": "cdc_orders",
    "error_type": "schema_mismatch",
    "error_message": "Column CUSTOMER_ID missing in target",
    "timestamp": "2026-02-18T11:00:00Z",
    "metadata": {"dag_id": "cdc_orders", "task_id": "load_to_snowflake"},
}


class TestIncidentEvent:
    def test_valid_event_parses(self) -> None:
        event = IncidentEvent.model_validate(VALID_EVENT)
        assert event.incident_id == UUID("7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010")
        assert event.source == "airflow"
        assert event.environment == "prod"

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError) as exc:
            IncidentEvent.model_validate({})
        errors = {e["loc"][0] for e in exc.value.errors()}
        assert "incident_id" in errors
        assert "source" in errors
        assert "environment" in errors
        assert "job_name" in errors
        assert "error_type" in errors
        assert "error_message" in errors
        assert "timestamp" in errors

    def test_invalid_source_rejected(self) -> None:
        bad = {**VALID_EVENT, "source": "kafka"}
        with pytest.raises(ValidationError):
            IncidentEvent.model_validate(bad)

    def test_invalid_environment_rejected(self) -> None:
        bad = {**VALID_EVENT, "environment": "qa"}
        with pytest.raises(ValidationError):
            IncidentEvent.model_validate(bad)

    def test_extra_fields_rejected(self) -> None:
        bad = {**VALID_EVENT, "extra_field": "oops"}
        with pytest.raises(ValidationError):
            IncidentEvent.model_validate(bad)

    def test_job_name_max_length(self) -> None:
        bad = {**VALID_EVENT, "job_name": "x" * 201}
        with pytest.raises(ValidationError):
            IncidentEvent.model_validate(bad)

    def test_error_message_max_length(self) -> None:
        bad = {**VALID_EVENT, "error_message": "x" * 4001}
        with pytest.raises(ValidationError):
            IncidentEvent.model_validate(bad)

    def test_metadata_optional(self) -> None:
        no_meta = {k: v for k, v in VALID_EVENT.items() if k != "metadata"}
        event = IncidentEvent.model_validate(no_meta)
        assert event.metadata is None or event.metadata == {}

    def test_timestamp_is_parsed(self) -> None:
        event = IncidentEvent.model_validate(VALID_EVENT)
        assert isinstance(event.timestamp, datetime)


class TestIncidentRecord:
    def test_minimal_record(self) -> None:
        now = datetime.now(tz=timezone.utc)
        record = IncidentRecord(
            incident_id=uuid4(),
            status="RECEIVED",
            created_at=now,
            updated_at=now,
        )
        assert record.status == "RECEIVED"
        assert record.classification is None
        assert record.diagnosis is None

    def test_extra_fields_rejected(self) -> None:
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(ValidationError):
            IncidentRecord(
                incident_id=uuid4(),
                status="RECEIVED",
                created_at=now,
                updated_at=now,
                unknown="bad",
            )
