"""Integration tests — full incident lifecycle against real Postgres.

Exercises ingest → state transitions → approval → feedback using
SqlIncidentRepository connected to a real Postgres container.  Proves
domain code, state machine, and ORM all work with Postgres.

All tests are marked `integration` and skipped when Docker is unavailable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(uuid.uuid4())


def _event(incident_id: str, **overrides):
    from investigator.models.incident import IncidentEvent, IncidentSource  # noqa: PLC0415

    defaults = dict(
        incident_id=incident_id,
        source=IncidentSource.airflow,
        environment="dev",
        job_name="test_job",
        error_type="schema_mismatch",
        error_message="Column missing in target",
        timestamp=datetime.now(tz=timezone.utc),
    )
    defaults.update(overrides)
    return IncidentEvent(**defaults)


# ---------------------------------------------------------------------------
# Function-scoped repo — fresh session per test avoids session poisoning
# when a test intentionally triggers a DB error (e.g. duplicate PK).
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(pg_engine):
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from investigator.repository.incident_repo import SqlIncidentRepository  # noqa: PLC0415

    session = Session(pg_engine)
    yield SqlIncidentRepository(session)
    session.close()


# ---------------------------------------------------------------------------
# Ingest tests
# ---------------------------------------------------------------------------

class TestIngestWithPostgres:
    def test_ingest_creates_row(self, repo):
        iid = _new_id()
        repo.create_incident(_event(iid))
        assert repo.get_incident(iid) is not None

    def test_ingest_sets_received_status(self, repo):
        iid = _new_id()
        repo.create_incident(_event(iid))
        assert repo.get_incident(iid).status == "RECEIVED"

    def test_ingest_persists_job_name(self, repo):
        iid = _new_id()
        repo.create_incident(_event(iid, job_name="cdc_orders"))
        assert repo.get_incident(iid).job_name == "cdc_orders"

    def test_ingest_duplicate_raises(self, repo):
        iid = _new_id()
        repo.create_incident(_event(iid))
        with pytest.raises(Exception):
            repo.create_incident(_event(iid))


# ---------------------------------------------------------------------------
# State transition tests
# ---------------------------------------------------------------------------

class TestStateTransitionsWithPostgres:
    def test_transition_updates_status(self, repo):
        from investigator.state.machine import IncidentStatus  # noqa: PLC0415

        iid = _new_id()
        repo.create_incident(_event(iid))
        repo.record_transition(iid, IncidentStatus.RECEIVED, IncidentStatus.CLASSIFIED, actor="test")
        assert repo.get_incident(iid).status == "CLASSIFIED"

    def test_invalid_transition_raises(self, repo):
        from investigator.state.machine import IncidentStatus  # noqa: PLC0415

        iid = _new_id()
        repo.create_incident(_event(iid))
        with pytest.raises(Exception):
            repo.record_transition(iid, IncidentStatus.RECEIVED, IncidentStatus.APPROVED, actor="test")

    def test_sequential_transitions_allowed(self, repo):
        from investigator.state.machine import IncidentStatus  # noqa: PLC0415

        iid = _new_id()
        repo.create_incident(_event(iid))
        repo.record_transition(iid, IncidentStatus.RECEIVED, IncidentStatus.CLASSIFIED, actor="t")
        repo.record_transition(iid, IncidentStatus.CLASSIFIED, IncidentStatus.DIAGNOSED, actor="t")
        assert repo.get_incident(iid).status == "DIAGNOSED"


# ---------------------------------------------------------------------------
# Approval queue tests
# ---------------------------------------------------------------------------

def _advance_to_approval_required(repo, iid: str) -> None:
    from investigator.state.machine import IncidentStatus  # noqa: PLC0415

    repo.create_incident(_event(iid))
    path = [
        (IncidentStatus.RECEIVED,             IncidentStatus.CLASSIFIED),
        (IncidentStatus.CLASSIFIED,           IncidentStatus.DIAGNOSED),
        (IncidentStatus.DIAGNOSED,            IncidentStatus.REMEDIATION_PROPOSED),
        (IncidentStatus.REMEDIATION_PROPOSED, IncidentStatus.RISK_ASSESSED),
        (IncidentStatus.RISK_ASSESSED,        IncidentStatus.APPROVAL_REQUIRED),
    ]
    for from_s, to_s in path:
        repo.record_transition(iid, from_s, to_s, actor="test")


class TestApprovalQueueWithPostgres:
    def test_pending_approval_appears_in_list(self, repo):
        iid = _new_id()
        _advance_to_approval_required(repo, iid)
        repo.create_approval_queue_item(iid, required_role="on_call_engineer")

        pending = repo.list_pending_approvals()
        assert any(a.incident_id == iid for a in pending)

    def test_approve_transitions_to_approved(self, repo):
        iid = _new_id()
        _advance_to_approval_required(repo, iid)
        repo.create_approval_queue_item(iid, required_role="on_call_engineer")
        repo.record_approval_decision(
            iid, approved=True, reviewer="engineer_1", reviewer_note=None
        )
        assert repo.get_incident(iid).status == "APPROVED"

    def test_reject_transitions_to_rejected(self, repo):
        iid = _new_id()
        _advance_to_approval_required(repo, iid)
        repo.create_approval_queue_item(iid, required_role="on_call_engineer")
        repo.record_approval_decision(
            iid, approved=False, reviewer="engineer_2", reviewer_note="Unsafe"
        )
        assert repo.get_incident(iid).status == "REJECTED"


# ---------------------------------------------------------------------------
# Feedback tests
# ---------------------------------------------------------------------------

class TestFeedbackWithPostgres:
    def test_feedback_stored(self, repo):
        iid = _new_id()
        repo.create_incident(_event(iid))
        repo.create_feedback(iid, outcome="fixed", overrides=None, reviewer_notes="Worked well.")

        rows = repo.list_feedback(iid)
        assert len(rows) == 1
        assert rows[0].outcome == "fixed"

    def test_multiple_feedback_entries_allowed(self, repo):
        iid = _new_id()
        repo.create_incident(_event(iid))
        repo.create_feedback(iid, outcome="fixed", overrides=None, reviewer_notes=None)
        repo.create_feedback(iid, outcome="not_fixed", overrides=None, reviewer_notes="Broke again")

        rows = repo.list_feedback(iid)
        assert len(rows) == 2
        outcomes = {r.outcome for r in rows}
        assert outcomes == {"fixed", "not_fixed"}
