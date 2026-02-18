"""Tests for ApprovalQueueItem and Feedback models."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from investigator.models import ApprovalQueueItem, ApprovalStatus, Feedback, OutcomeType


NOW = datetime.now(tz=timezone.utc)


class TestApprovalQueueItem:
    def test_valid_minimal(self) -> None:
        item = ApprovalQueueItem(
            incident_id=uuid4(),
            status=ApprovalStatus.pending,
            required_role="oncall_engineer",
            created_at=NOW,
        )
        assert item.reviewer is None
        assert item.reviewer_note is None

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalQueueItem(
                incident_id=uuid4(),
                status="maybe",
                required_role="oncall",
                created_at=NOW,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalQueueItem(
                incident_id=uuid4(),
                status=ApprovalStatus.pending,
                required_role="oncall",
                created_at=NOW,
                unknown="x",
            )


class TestFeedback:
    def test_valid(self) -> None:
        fb = Feedback(
            incident_id=uuid4(),
            outcome=OutcomeType.fixed,
            timestamp=NOW,
        )
        assert fb.reviewer_notes is None
        assert fb.overrides is None

    def test_invalid_outcome(self) -> None:
        with pytest.raises(ValidationError):
            Feedback(incident_id=uuid4(), outcome="partial", timestamp=NOW)

    def test_reviewer_notes_max_length(self) -> None:
        with pytest.raises(ValidationError):
            Feedback(
                incident_id=uuid4(),
                outcome=OutcomeType.fixed,
                timestamp=NOW,
                reviewer_notes="x" * 4001,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Feedback(
                incident_id=uuid4(),
                outcome=OutcomeType.fixed,
                timestamp=NOW,
                bad="field",
            )
