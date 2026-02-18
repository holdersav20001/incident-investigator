"""Incident state machine — deterministic, no LLM involvement."""

from enum import StrEnum


class IncidentStatus(StrEnum):
    RECEIVED = "RECEIVED"
    CLASSIFIED = "CLASSIFIED"
    DIAGNOSED = "DIAGNOSED"
    REMEDIATION_PROPOSED = "REMEDIATION_PROPOSED"
    RISK_ASSESSED = "RISK_ASSESSED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Allowed (from, to) transitions — the only source of truth for state changes.
# Any transition not in this set is invalid.
_ALLOWED: frozenset[tuple[IncidentStatus, IncidentStatus]] = frozenset(
    {
        (IncidentStatus.RECEIVED, IncidentStatus.CLASSIFIED),
        (IncidentStatus.CLASSIFIED, IncidentStatus.DIAGNOSED),
        (IncidentStatus.DIAGNOSED, IncidentStatus.REMEDIATION_PROPOSED),
        (IncidentStatus.REMEDIATION_PROPOSED, IncidentStatus.RISK_ASSESSED),
        # Risk engine decides whether human review is needed or can auto-approve
        (IncidentStatus.RISK_ASSESSED, IncidentStatus.APPROVAL_REQUIRED),
        (IncidentStatus.RISK_ASSESSED, IncidentStatus.APPROVED),
        (IncidentStatus.APPROVAL_REQUIRED, IncidentStatus.APPROVED),
        (IncidentStatus.APPROVAL_REQUIRED, IncidentStatus.REJECTED),
    }
)


def transition(current: IncidentStatus, target: IncidentStatus) -> IncidentStatus:
    """Validate and perform a state transition.

    Raises ValueError for any disallowed move, keeping the state machine
    authoritative — workflow code must call this rather than setting status directly.
    """
    if (current, target) not in _ALLOWED:
        raise ValueError(
            f"Invalid transition: {current!r} -> {target!r}"
        )
    return target
