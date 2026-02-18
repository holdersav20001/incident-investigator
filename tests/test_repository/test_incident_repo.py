"""Tests for IncidentRepository using in-memory SQLite."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investigator.db.models import Base
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.models import IncidentEvent
from investigator.state import IncidentStatus


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


@pytest.fixture()
def repo(session):
    return SqlIncidentRepository(session)


VALID_EVENT_DATA = {
    "incident_id": None,  # overridden per test
    "source": "airflow",
    "environment": "prod",
    "job_name": "cdc_orders",
    "error_type": "schema_mismatch",
    "error_message": "Column CUSTOMER_ID missing",
    "timestamp": "2026-02-18T11:00:00Z",
}


def make_event(incident_id=None) -> IncidentEvent:
    iid = incident_id or uuid4()
    return IncidentEvent.model_validate({**VALID_EVENT_DATA, "incident_id": str(iid)})


class TestCreateIncident:
    def test_create_returns_id(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        assert str(iid) == str(event.incident_id)

    def test_created_incident_has_received_status(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        row = repo.get_incident(iid)
        assert row is not None
        assert row.status == "RECEIVED"

    def test_duplicate_incident_id_raises(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        repo.create_incident(event)
        with pytest.raises(Exception):
            repo.create_incident(event)


class TestGetIncident:
    def test_returns_none_for_unknown(self, repo: SqlIncidentRepository) -> None:
        assert repo.get_incident(uuid4()) is None

    def test_get_after_create(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        row = repo.get_incident(iid)
        assert row is not None
        assert row.job_name == "cdc_orders"
        assert row.environment == "prod"


class TestListByStatus:
    def test_list_received(self, repo: SqlIncidentRepository) -> None:
        for _ in range(3):
            repo.create_incident(make_event())
        rows = repo.list_by_status(IncidentStatus.RECEIVED)
        assert len(rows) == 3

    def test_list_empty_for_other_status(self, repo: SqlIncidentRepository) -> None:
        repo.create_incident(make_event())
        rows = repo.list_by_status(IncidentStatus.CLASSIFIED)
        assert rows == []


class TestAppendEvent:
    def test_append_stores_event(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        repo.append_event(iid, event_type="ingest", payload={"extra": "info"})
        events = repo.get_events(iid)
        # The create itself may also record an event
        assert any(e.event_type == "ingest" for e in events)

    def test_append_to_nonexistent_raises(self, repo: SqlIncidentRepository) -> None:
        with pytest.raises(Exception):
            repo.append_event(uuid4(), event_type="ingest", payload={})


class TestRecordTransition:
    def test_transition_updates_status(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        repo.record_transition(iid, IncidentStatus.RECEIVED, IncidentStatus.CLASSIFIED)
        row = repo.get_incident(iid)
        assert row is not None
        assert row.status == "CLASSIFIED"

    def test_transition_is_audited(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        repo.record_transition(iid, IncidentStatus.RECEIVED, IncidentStatus.CLASSIFIED)
        transitions = repo.get_transitions(iid)
        assert any(
            t.from_status == "RECEIVED" and t.to_status == "CLASSIFIED"
            for t in transitions
        )

    def test_invalid_transition_raises(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        with pytest.raises(ValueError, match="Invalid transition"):
            repo.record_transition(iid, IncidentStatus.RECEIVED, IncidentStatus.APPROVED)


class TestUpdateClassification:
    def test_saves_classification_blob(self, repo: SqlIncidentRepository) -> None:
        event = make_event()
        iid = repo.create_incident(event)
        blob = {"type": "timeout", "confidence": 0.9, "reason": "keyword"}
        repo.update_classification(iid, blob)
        row = repo.get_incident(iid)
        assert row is not None
        assert row.classification is not None
        assert row.classification["type"] == "timeout"
