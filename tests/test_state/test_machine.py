"""Tests for the incident state machine."""

import pytest

from investigator.state import IncidentStatus, transition


class TestIncidentStatus:
    def test_all_states_present(self) -> None:
        states = {s.value for s in IncidentStatus}
        assert states == {
            "RECEIVED",
            "CLASSIFIED",
            "DIAGNOSED",
            "REMEDIATION_PROPOSED",
            "RISK_ASSESSED",
            "APPROVAL_REQUIRED",
            "APPROVED",
            "REJECTED",
        }


class TestTransition:
    def test_happy_path(self) -> None:
        assert transition(IncidentStatus.RECEIVED, IncidentStatus.CLASSIFIED) == IncidentStatus.CLASSIFIED
        assert transition(IncidentStatus.CLASSIFIED, IncidentStatus.DIAGNOSED) == IncidentStatus.DIAGNOSED
        assert transition(IncidentStatus.DIAGNOSED, IncidentStatus.REMEDIATION_PROPOSED) == IncidentStatus.REMEDIATION_PROPOSED
        assert transition(IncidentStatus.REMEDIATION_PROPOSED, IncidentStatus.RISK_ASSESSED) == IncidentStatus.RISK_ASSESSED
        assert transition(IncidentStatus.RISK_ASSESSED, IncidentStatus.APPROVAL_REQUIRED) == IncidentStatus.APPROVAL_REQUIRED
        assert transition(IncidentStatus.RISK_ASSESSED, IncidentStatus.APPROVED) == IncidentStatus.APPROVED
        assert transition(IncidentStatus.APPROVAL_REQUIRED, IncidentStatus.APPROVED) == IncidentStatus.APPROVED
        assert transition(IncidentStatus.APPROVAL_REQUIRED, IncidentStatus.REJECTED) == IncidentStatus.REJECTED

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(IncidentStatus.RECEIVED, IncidentStatus.DIAGNOSED)

    def test_backward_transition_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(IncidentStatus.CLASSIFIED, IncidentStatus.RECEIVED)

    def test_skip_transition_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(IncidentStatus.RECEIVED, IncidentStatus.APPROVED)

    def test_approved_is_terminal(self) -> None:
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(IncidentStatus.APPROVED, IncidentStatus.CLASSIFIED)

    def test_rejected_is_terminal(self) -> None:
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(IncidentStatus.REJECTED, IncidentStatus.CLASSIFIED)

    def test_idempotent_same_state_raises(self) -> None:
        # Staying in same state is not a valid transition
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(IncidentStatus.RECEIVED, IncidentStatus.RECEIVED)
