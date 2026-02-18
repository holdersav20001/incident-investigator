"""Tests for SQLAlchemy ORM models — run against in-memory SQLite."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from investigator.db.models import Base, IncidentRow, IncidentEventRow, TransitionRow


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


class TestIncidentRow:
    def test_create_and_retrieve(self, session: Session) -> None:
        iid = uuid4()
        now = datetime.now(tz=timezone.utc)
        row = IncidentRow(
            incident_id=str(iid),
            status="RECEIVED",
            source="airflow",
            environment="prod",
            job_name="cdc_orders",
            error_type="schema_mismatch",
            error_message="Column X missing",
            event_timestamp=now,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()

        fetched = session.get(IncidentRow, str(iid))
        assert fetched is not None
        assert fetched.status == "RECEIVED"
        assert fetched.job_name == "cdc_orders"

    def test_classification_jsonb_roundtrip(self, session: Session) -> None:
        iid = uuid4()
        now = datetime.now(tz=timezone.utc)
        row = IncidentRow(
            incident_id=str(iid),
            status="CLASSIFIED",
            source="airflow",
            environment="prod",
            job_name="job_a",
            error_type="timeout",
            error_message="timed out",
            event_timestamp=now,
            created_at=now,
            updated_at=now,
            classification={"type": "timeout", "confidence": 0.9, "reason": "keyword match"},
        )
        session.add(row)
        session.commit()
        session.expire(row)

        fetched = session.get(IncidentRow, str(iid))
        assert fetched is not None
        assert fetched.classification["type"] == "timeout"


class TestIncidentEventRow:
    def test_create_event(self, session: Session) -> None:
        iid = str(uuid4())
        now = datetime.now(tz=timezone.utc)
        inc = IncidentRow(
            incident_id=iid,
            status="RECEIVED",
            source="airflow",
            environment="prod",
            job_name="job_a",
            error_type="timeout",
            error_message="timed out",
            event_timestamp=now,
            created_at=now,
            updated_at=now,
        )
        session.add(inc)
        session.flush()

        evt = IncidentEventRow(
            incident_id=iid,
            event_type="ingest",
            payload={"raw": "data"},
            occurred_at=now,
        )
        session.add(evt)
        session.commit()

        events = session.query(IncidentEventRow).filter_by(incident_id=iid).all()
        assert len(events) == 1
        assert events[0].event_type == "ingest"


class TestTransitionRow:
    def test_record_transition(self, session: Session) -> None:
        iid = str(uuid4())
        now = datetime.now(tz=timezone.utc)
        inc = IncidentRow(
            incident_id=iid,
            status="CLASSIFIED",
            source="airflow",
            environment="prod",
            job_name="job_b",
            error_type="timeout",
            error_message="timed out",
            event_timestamp=now,
            created_at=now,
            updated_at=now,
        )
        session.add(inc)
        session.flush()

        t = TransitionRow(
            incident_id=iid,
            from_status="RECEIVED",
            to_status="CLASSIFIED",
            transitioned_at=now,
        )
        session.add(t)
        session.commit()

        rows = session.query(TransitionRow).filter_by(incident_id=iid).all()
        assert len(rows) == 1
        assert rows[0].to_status == "CLASSIFIED"
