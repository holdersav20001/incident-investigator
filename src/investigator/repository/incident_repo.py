"""SQLAlchemy-backed incident repository.

All state transitions go through the deterministic state machine — the
repository never sets `status` directly without calling `transition()`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from investigator.db.models import ApprovalRow, FeedbackRow, IncidentEventRow, IncidentRow, TransitionRow
from investigator.models import IncidentEvent
from investigator.state import IncidentStatus, transition


class SqlIncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_incident(self, event: IncidentEvent) -> UUID:
        """Persist a new incident in RECEIVED state and log the ingest event."""
        now = datetime.now(tz=timezone.utc)
        row = IncidentRow(
            incident_id=str(event.incident_id),
            status=IncidentStatus.RECEIVED,
            source=event.source,
            environment=event.environment,
            job_name=event.job_name,
            error_type=event.error_type,
            error_message=event.error_message,
            event_timestamp=event.timestamp,
            raw_metadata=event.metadata,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.flush()  # surface duplicate-PK errors before appending event

        evt = IncidentEventRow(
            incident_id=str(event.incident_id),
            event_type="ingest",
            payload=event.model_dump(mode="json"),
            occurred_at=now,
        )
        self._session.add(evt)
        self._session.commit()
        return event.incident_id

    def record_transition(
        self,
        incident_id: UUID,
        from_status: IncidentStatus,
        to_status: IncidentStatus,
        actor: str | None = None,
    ) -> None:
        """Validate the transition via the state machine, then persist it."""
        # Raises ValueError on invalid move — callers must not swallow this.
        transition(from_status, to_status)

        now = datetime.now(tz=timezone.utc)
        row = self._require(incident_id)
        row.status = to_status
        row.updated_at = now

        t = TransitionRow(
            incident_id=str(incident_id),
            from_status=from_status,
            to_status=to_status,
            transitioned_at=now,
            actor=actor,
        )
        self._session.add(t)
        self._session.commit()

    def append_event(
        self,
        incident_id: UUID,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append an event to the incident's event log."""
        self._require(incident_id)  # raises if not found
        evt = IncidentEventRow(
            incident_id=str(incident_id),
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(evt)
        self._session.commit()

    def update_classification(
        self, incident_id: UUID, classification: dict[str, Any]
    ) -> None:
        row = self._require(incident_id)
        row.classification = classification
        row.updated_at = datetime.now(tz=timezone.utc)
        self._session.commit()

    def update_diagnosis(self, incident_id: UUID, diagnosis: dict[str, Any]) -> None:
        row = self._require(incident_id)
        row.diagnosis = diagnosis
        row.updated_at = datetime.now(tz=timezone.utc)
        self._session.commit()

    def update_remediation(
        self,
        incident_id: UUID,
        remediation: dict[str, Any],
        simulation: dict[str, Any],
    ) -> None:
        row = self._require(incident_id)
        row.remediation = remediation
        row.simulation = simulation
        row.updated_at = datetime.now(tz=timezone.utc)
        self._session.commit()

    def update_risk(self, incident_id: UUID, risk: dict[str, Any]) -> None:
        row = self._require(incident_id)
        row.risk = risk
        row.updated_at = datetime.now(tz=timezone.utc)
        self._session.commit()

    def update_approval_status(self, incident_id: UUID, approval_status: str) -> None:
        row = self._require(incident_id)
        row.approval_status = approval_status
        row.updated_at = datetime.now(tz=timezone.utc)
        self._session.commit()

    def create_approval_queue_item(self, incident_id: UUID, *, required_role: str) -> None:
        """Create a pending approval queue record for a human-review incident."""
        item = ApprovalRow(
            incident_id=str(incident_id),
            status="pending",
            required_role=required_role,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(item)
        self._session.commit()

    def record_approval_decision(
        self,
        incident_id: UUID,
        *,
        approved: bool,
        reviewer: str,
        reviewer_note: str | None,
    ) -> None:
        """Record the human reviewer's decision and transition the incident state."""
        item = self._require_approval(incident_id)
        now = datetime.now(tz=timezone.utc)
        item.status = "approved" if approved else "rejected"
        item.reviewer = reviewer
        item.reviewer_note = reviewer_note
        item.reviewed_at = now
        self._session.flush()

        # Transition incident state through the state machine
        target = IncidentStatus.APPROVED if approved else IncidentStatus.REJECTED
        self.record_transition(incident_id, IncidentStatus.APPROVAL_REQUIRED, target, actor=reviewer)

    def create_feedback(
        self,
        incident_id: UUID,
        *,
        outcome: str,
        overrides: dict[str, Any] | None,
        reviewer_notes: str | None,
    ) -> None:
        """Persist outcome feedback for an incident."""
        self._require(incident_id)  # raises if incident missing
        fb = FeedbackRow(
            incident_id=str(incident_id),
            outcome=outcome,
            overrides=overrides,
            reviewer_notes=reviewer_notes,
            submitted_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(fb)
        self._session.commit()

    def list_feedback(self, incident_id: UUID) -> list[FeedbackRow]:
        return (
            self._session.query(FeedbackRow)
            .filter(FeedbackRow.incident_id == str(incident_id))
            .order_by(FeedbackRow.id)
            .all()
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_incident(self, incident_id: UUID) -> Optional[IncidentRow]:
        return self._session.get(IncidentRow, str(incident_id))

    def get_approval(self, incident_id: UUID) -> Optional[ApprovalRow]:
        return (
            self._session.query(ApprovalRow)
            .filter(ApprovalRow.incident_id == str(incident_id))
            .first()
        )

    def list_pending_approvals(self) -> list[ApprovalRow]:
        return (
            self._session.query(ApprovalRow)
            .filter(ApprovalRow.status == "pending")
            .order_by(ApprovalRow.created_at)
            .all()
        )

    def list_incidents(
        self,
        *,
        status: Optional[IncidentStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentRow]:
        q = self._session.query(IncidentRow)
        if status is not None:
            q = q.filter(IncidentRow.status == status)
        return q.order_by(IncidentRow.created_at.desc()).offset(offset).limit(limit).all()

    def list_by_status(self, status: IncidentStatus) -> list[IncidentRow]:
        return (
            self._session.query(IncidentRow)
            .filter(IncidentRow.status == status)
            .all()
        )

    def get_events(self, incident_id: UUID) -> list[IncidentEventRow]:
        return (
            self._session.query(IncidentEventRow)
            .filter(IncidentEventRow.incident_id == str(incident_id))
            .order_by(IncidentEventRow.id)
            .all()
        )

    def get_transitions(self, incident_id: UUID) -> list[TransitionRow]:
        return (
            self._session.query(TransitionRow)
            .filter(TransitionRow.incident_id == str(incident_id))
            .order_by(TransitionRow.id)
            .all()
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require(self, incident_id: UUID) -> IncidentRow:
        row = self._session.get(IncidentRow, str(incident_id))
        if row is None:
            raise LookupError(f"Incident {incident_id} not found")
        return row

    def _require_approval(self, incident_id: UUID) -> ApprovalRow:
        item = self.get_approval(incident_id)
        if item is None:
            raise LookupError(f"No approval queue entry for incident {incident_id}")
        return item
