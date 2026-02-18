"""Tests for approval queue repository methods."""

import pytest
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from investigator.db.models import Base, IncidentRow
from investigator.repository.incident_repo import SqlIncidentRepository
from investigator.state.machine import IncidentStatus


INCIDENT_ID = UUID("bbbb0000-0000-0000-0000-000000000001")


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
def repo(session):
    return SqlIncidentRepository(session)


@pytest.fixture()
def pending_incident(session):
    """An incident already in APPROVAL_REQUIRED state."""
    now = datetime.now(tz=timezone.utc)
    row = IncidentRow(
        incident_id=str(INCIDENT_ID),
        status=IncidentStatus.APPROVAL_REQUIRED,
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


class TestCreateApprovalQueueItem:
    def test_creates_record(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        item = repo.get_approval(INCIDENT_ID)
        assert item is not None

    def test_status_is_pending(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        item = repo.get_approval(INCIDENT_ID)
        assert item.status == "pending"

    def test_required_role_stored(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="data_platform_lead")
        item = repo.get_approval(INCIDENT_ID)
        assert item.required_role == "data_platform_lead"


class TestListPendingApprovals:
    def test_returns_empty_list_when_none(self, repo):
        assert repo.list_pending_approvals() == []

    def test_returns_pending_item(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        items = repo.list_pending_approvals()
        assert len(items) == 1

    def test_approved_items_not_included(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=True, reviewer="alice", reviewer_note=None
        )
        items = repo.list_pending_approvals()
        assert len(items) == 0


class TestRecordApprovalDecision:
    def test_approve_updates_status(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=True, reviewer="alice", reviewer_note="ok"
        )
        item = repo.get_approval(INCIDENT_ID)
        assert item.status == "approved"

    def test_reject_updates_status(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=False, reviewer="bob", reviewer_note="too risky"
        )
        item = repo.get_approval(INCIDENT_ID)
        assert item.status == "rejected"

    def test_reviewer_stored(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=True, reviewer="alice", reviewer_note=None
        )
        item = repo.get_approval(INCIDENT_ID)
        assert item.reviewer == "alice"

    def test_reviewed_at_set(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=True, reviewer="alice", reviewer_note=None
        )
        item = repo.get_approval(INCIDENT_ID)
        assert item.reviewed_at is not None

    def test_approve_transitions_incident_to_approved(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=True, reviewer="alice", reviewer_note=None
        )
        incident = repo.get_incident(INCIDENT_ID)
        assert incident.status == IncidentStatus.APPROVED

    def test_reject_transitions_incident_to_rejected(self, repo, pending_incident):
        repo.create_approval_queue_item(INCIDENT_ID, required_role="on_call_engineer")
        repo.record_approval_decision(
            INCIDENT_ID, approved=False, reviewer="bob", reviewer_note=None
        )
        incident = repo.get_incident(INCIDENT_ID)
        assert incident.status == IncidentStatus.REJECTED
