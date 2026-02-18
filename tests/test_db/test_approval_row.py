"""Tests for ApprovalRow ORM model and approval queue repository methods."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.db.models import Base, IncidentRow, ApprovalRow


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def incident(session):
    now = datetime.now(tz=timezone.utc)
    row = IncidentRow(
        incident_id="aaaa0000-0000-0000-0000-000000000001",
        status="APPROVAL_REQUIRED",
        source="airflow",
        environment="prod",
        job_name="cdc_orders",
        error_type="schema_mismatch",
        error_message="Column missing",
        event_timestamp=now,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    return row


class TestApprovalRow:
    def test_can_create_approval_row(self, session, incident):
        now = datetime.now(tz=timezone.utc)
        row = ApprovalRow(
            incident_id=incident.incident_id,
            status="pending",
            required_role="on_call_engineer",
            created_at=now,
        )
        session.add(row)
        session.commit()
        assert row.id is not None

    def test_reviewer_fields_nullable(self, session, incident):
        now = datetime.now(tz=timezone.utc)
        row = ApprovalRow(
            incident_id=incident.incident_id,
            status="pending",
            required_role="on_call_engineer",
            created_at=now,
        )
        session.add(row)
        session.commit()
        assert row.reviewer is None
        assert row.reviewer_note is None
        assert row.reviewed_at is None

    def test_can_set_reviewer_fields(self, session, incident):
        now = datetime.now(tz=timezone.utc)
        row = ApprovalRow(
            incident_id=incident.incident_id,
            status="approved",
            required_role="on_call_engineer",
            reviewer="alice",
            reviewer_note="Looks good",
            created_at=now,
            reviewed_at=now,
        )
        session.add(row)
        session.commit()
        fetched = session.get(ApprovalRow, row.id)
        assert fetched.reviewer == "alice"
        assert fetched.reviewer_note == "Looks good"
