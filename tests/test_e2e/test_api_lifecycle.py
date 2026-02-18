"""E2E HTTP lifecycle tests — full investigation workflows via the API.

Each test class exercises a complete scenario across multiple endpoints in
sequence.  These are the integration smoke tests that verify the API layer,
pipeline, state machine, and approval workflow all cooperate correctly.
"""

from __future__ import annotations

import pytest

from tests.test_e2e.conftest import UNSAFE_PLAN, ingest


# ---------------------------------------------------------------------------
# Scenario 1: Dev auto-approve — full happy path including feedback
# ---------------------------------------------------------------------------


class TestDevAutoApproveLifecycle:
    """schema_mismatch in dev → pipeline auto-approves → feedback submitted."""

    def test_ingest_returns_201(self, safe_client):
        iid = ingest(safe_client, environment="dev")
        resp = safe_client.get(f"/incidents/{iid}")
        assert resp.status_code == 200

    def test_status_is_received_before_investigation(self, safe_client):
        iid = ingest(safe_client, environment="dev")
        assert safe_client.get(f"/incidents/{iid}").json()["status"] == "RECEIVED"

    def test_investigate_returns_approved(self, safe_client):
        iid = ingest(safe_client, environment="dev")
        resp = safe_client.post(f"/incidents/{iid}/investigate")
        assert resp.status_code == 200
        assert resp.json()["final_status"] == "APPROVED"

    def test_status_is_approved_after_investigation(self, safe_client):
        iid = ingest(safe_client, environment="dev")
        safe_client.post(f"/incidents/{iid}/investigate")
        assert safe_client.get(f"/incidents/{iid}").json()["status"] == "APPROVED"

    def test_feedback_accepted_after_approval(self, safe_client):
        iid = ingest(safe_client, environment="dev")
        safe_client.post(f"/incidents/{iid}/investigate")
        resp = safe_client.post(
            f"/incidents/{iid}/feedback",
            json={"outcome": "fixed", "timestamp": "2026-02-18T12:00:00Z"},
        )
        assert resp.status_code == 201

    def test_feedback_response_has_correct_incident_id(self, safe_client):
        iid = ingest(safe_client, environment="dev")
        safe_client.post(f"/incidents/{iid}/investigate")
        resp = safe_client.post(
            f"/incidents/{iid}/feedback",
            json={"outcome": "fixed", "timestamp": "2026-02-18T12:00:00Z"},
        )
        assert resp.json()["incident_id"] == iid


# ---------------------------------------------------------------------------
# Scenario 2: Prod human-review → approve via API → APPROVED
# ---------------------------------------------------------------------------


class TestProdHumanReviewLifecycle:
    """schema_mismatch in prod → APPROVAL_REQUIRED → engineer approves → APPROVED."""

    def _run_prod_investigation(self, client):
        iid = ingest(client, environment="prod")
        client.post(f"/incidents/{iid}/investigate")
        return iid

    def test_prod_incident_requires_approval(self, safe_client):
        iid = self._run_prod_investigation(safe_client)
        assert safe_client.get(f"/incidents/{iid}").json()["status"] == "APPROVAL_REQUIRED"

    def test_approval_appears_in_pending_queue(self, safe_client):
        iid = self._run_prod_investigation(safe_client)
        pending = safe_client.get("/approvals/pending").json()
        incident_ids = [a["incident_id"] for a in pending]
        assert iid in incident_ids

    def test_approve_transitions_to_approved(self, safe_client):
        iid = self._run_prod_investigation(safe_client)
        resp = safe_client.post(
            f"/approvals/{iid}/approve",
            json={"reviewer": "alice", "reviewer_note": "Looks good"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_status_is_approved_after_human_approval(self, safe_client):
        iid = self._run_prod_investigation(safe_client)
        safe_client.post(
            f"/approvals/{iid}/approve",
            json={"reviewer": "alice", "reviewer_note": "LGTM"},
        )
        assert safe_client.get(f"/incidents/{iid}").json()["status"] == "APPROVED"

    def test_no_longer_in_pending_queue_after_approval(self, safe_client):
        iid = self._run_prod_investigation(safe_client)
        safe_client.post(f"/approvals/{iid}/approve", json={"reviewer": "alice"})
        pending = safe_client.get("/approvals/pending").json()
        assert iid not in [a["incident_id"] for a in pending]


# ---------------------------------------------------------------------------
# Scenario 3: Prod human-review → reject via API → REJECTED
# ---------------------------------------------------------------------------


class TestProdHumanRejectLifecycle:
    """Reviewer rejects the incident; final status must be REJECTED."""

    def test_reject_returns_200(self, safe_client):
        iid = ingest(safe_client, environment="prod")
        safe_client.post(f"/incidents/{iid}/investigate")
        resp = safe_client.post(
            f"/approvals/{iid}/reject",
            json={"reviewer": "bob", "reviewer_note": "Too risky"},
        )
        assert resp.status_code == 200

    def test_status_is_rejected_after_human_rejection(self, safe_client):
        iid = ingest(safe_client, environment="prod")
        safe_client.post(f"/incidents/{iid}/investigate")
        safe_client.post(f"/approvals/{iid}/reject", json={"reviewer": "bob"})
        assert safe_client.get(f"/incidents/{iid}").json()["status"] == "REJECTED"


# ---------------------------------------------------------------------------
# Scenario 4: Unsafe remediation plan → auto-rejected by simulator
# ---------------------------------------------------------------------------


class TestUnsafePlanLifecycle:
    """A DELETE plan is caught by the simulator and the incident is rejected."""

    def test_unsafe_plan_results_in_rejected_status(self, unsafe_client):
        iid = ingest(unsafe_client, environment="prod", error_type="data_quality")
        resp = unsafe_client.post(f"/incidents/{iid}/investigate")
        assert resp.json()["final_status"] == "REJECTED"

    def test_rejected_incident_not_in_pending_queue(self, unsafe_client):
        iid = ingest(unsafe_client, environment="prod", error_type="data_quality")
        unsafe_client.post(f"/incidents/{iid}/investigate")
        pending = unsafe_client.get("/approvals/pending").json()
        assert iid not in [a["incident_id"] for a in pending]

    def test_incidents_list_shows_rejected_status(self, unsafe_client):
        iid = ingest(unsafe_client, environment="prod", error_type="data_quality")
        unsafe_client.post(f"/incidents/{iid}/investigate")
        rows = unsafe_client.get("/incidents").json()
        match = next((r for r in rows if r["incident_id"] == iid), None)
        assert match is not None
        assert match["status"] == "REJECTED"
