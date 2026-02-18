"""Tests for the postmortem generator.

Validates that PostmortemGenerator.generate() produces a Postmortem with:
- All required sections present in the Markdown output
- Correct data fields sourced from the IncidentRow
- Proper handling of None / missing agent output blobs
- Correct action items based on incident disposition
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from investigator.reporting.postmortem import PostmortemGenerator, Postmortem


# ---------------------------------------------------------------------------
# Helpers — build mock IncidentRow objects
# ---------------------------------------------------------------------------

def _make_row(**overrides) -> MagicMock:
    """Return a mock IncidentRow with sensible defaults for all tests."""
    row = MagicMock()
    row.incident_id = "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010"
    row.status = "APPROVED"
    row.environment = "prod"
    row.job_name = "cdc_orders"
    row.error_type = "schema_mismatch"
    row.error_message = "Column CUSTOMER_ID missing in target"
    row.event_timestamp = datetime(2026, 2, 18, 11, 0, 0, tzinfo=timezone.utc)
    row.classification = {"type": "schema_mismatch", "confidence": 0.87, "reason": "keyword match"}
    row.diagnosis = {
        "root_cause": "upstream schema drift in extractor",
        "confidence": 0.88,
        "next_checks": ["Compare source schema vs target", "Check last successful run"],
    }
    row.remediation = {
        "plan": [
            {"step": "Re-run extractor with updated schema mapping", "tool": "rerun_job", "command": "dag=cdc"},
        ],
        "rollback": [{"step": "Revert mapping to previous version"}],
        "expected_time_minutes": 15,
    }
    row.simulation = {"ok": True, "checks": [], "notes": ["No writes detected."]}
    row.risk = {
        "risk_score": 45,
        "risk_level": "MEDIUM",
        "recommendation": "human_review",
        "rationale": "Production incident with moderate confidence",
        "blast_radius": ["cdc_orders pipeline", "downstream reporting"],
    }
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


@pytest.fixture()
def gen() -> PostmortemGenerator:
    return PostmortemGenerator()


@pytest.fixture()
def postmortem(gen) -> Postmortem:
    return gen.generate(_make_row())


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestPostmortemGeneration:
    def test_returns_postmortem_instance(self, gen):
        result = gen.generate(_make_row())
        assert isinstance(result, Postmortem)

    def test_incident_id_matches(self, postmortem):
        assert postmortem.incident_id == "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010"

    def test_status_matches(self, postmortem):
        assert postmortem.status == "APPROVED"

    def test_environment_matches(self, postmortem):
        assert postmortem.environment == "prod"

    def test_job_name_matches(self, postmortem):
        assert postmortem.job_name == "cdc_orders"

    def test_error_type_matches(self, postmortem):
        assert postmortem.error_type == "schema_mismatch"

    def test_root_cause_extracted(self, postmortem):
        assert postmortem.root_cause == "upstream schema drift in extractor"

    def test_confidence_extracted(self, postmortem):
        assert postmortem.confidence == pytest.approx(0.88)

    def test_next_checks_extracted(self, postmortem):
        assert len(postmortem.next_checks) == 2

    def test_remediation_steps_extracted(self, postmortem):
        assert len(postmortem.remediation_steps) == 1
        assert "Re-run extractor" in postmortem.remediation_steps[0]

    def test_rollback_steps_extracted(self, postmortem):
        assert len(postmortem.rollback_steps) == 1

    def test_estimated_time_extracted(self, postmortem):
        assert postmortem.estimated_time_minutes == 15

    def test_simulation_ok_extracted(self, postmortem):
        assert postmortem.simulation_ok is True

    def test_risk_score_extracted(self, postmortem):
        assert postmortem.risk_score == 45

    def test_risk_level_extracted(self, postmortem):
        assert postmortem.risk_level == "MEDIUM"

    def test_blast_radius_extracted(self, postmortem):
        assert len(postmortem.blast_radius) == 2


# ---------------------------------------------------------------------------
# Markdown output — required sections
# ---------------------------------------------------------------------------

class TestMarkdownSections:
    REQUIRED_SECTIONS = [
        "## Executive Summary",
        "## Incident Timeline",
        "## Root Cause Analysis",
        "## Remediation Plan",
        "## Simulation Results",
        "## Risk Assessment",
        "## Impact & Blast Radius",
        "## Action Items",
    ]

    def test_markdown_is_non_empty_string(self, postmortem):
        assert isinstance(postmortem.markdown, str) and postmortem.markdown

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_section_present(self, postmortem, section):
        assert section in postmortem.markdown, f"Missing section: {section}"

    def test_incident_id_in_markdown(self, postmortem):
        assert postmortem.incident_id in postmortem.markdown

    def test_root_cause_in_markdown(self, postmortem):
        assert "upstream schema drift in extractor" in postmortem.markdown

    def test_risk_level_in_markdown(self, postmortem):
        assert "MEDIUM" in postmortem.markdown

    def test_job_name_in_markdown(self, postmortem):
        assert "cdc_orders" in postmortem.markdown

    def test_markdown_starts_with_h1(self, postmortem):
        assert postmortem.markdown.startswith("# Postmortem")

    def test_no_python_objects_in_markdown(self, postmortem):
        # Must not contain raw Python repr like "<MagicMock ...>"
        assert "<MagicMock" not in postmortem.markdown


# ---------------------------------------------------------------------------
# Edge cases — partial / missing data
# ---------------------------------------------------------------------------

class TestMissingData:
    def test_no_diagnosis_produces_valid_output(self, gen):
        row = _make_row(diagnosis=None)
        pm = gen.generate(row)
        assert "## Root Cause Analysis" in pm.markdown

    def test_no_remediation_produces_valid_output(self, gen):
        row = _make_row(remediation=None)
        pm = gen.generate(row)
        assert "## Remediation Plan" in pm.markdown
        assert "_No remediation plan recorded._" in pm.markdown

    def test_no_simulation_produces_valid_output(self, gen):
        row = _make_row(simulation=None)
        pm = gen.generate(row)
        assert "_Simulation not run._" in pm.markdown

    def test_no_risk_produces_valid_output(self, gen):
        row = _make_row(risk=None)
        pm = gen.generate(row)
        assert "_Risk assessment not recorded._" in pm.markdown

    def test_no_blast_radius_falls_back_gracefully(self, gen):
        risk = {"risk_score": 30, "risk_level": "LOW", "recommendation": "auto_approve"}
        row = _make_row(risk=risk)
        pm = gen.generate(row)
        assert "_No blast radius recorded._" in pm.markdown


# ---------------------------------------------------------------------------
# Action items by disposition
# ---------------------------------------------------------------------------

class TestActionItems:
    def test_rejected_incident_gets_review_actions(self, gen):
        pm = gen.generate(_make_row(status="REJECTED"))
        assert len(pm.action_items) >= 1
        joined = " ".join(pm.action_items)
        assert "remediation" in joined.lower() or "unsafe" in joined.lower()

    def test_approval_required_incident_gets_review_action(self, gen):
        pm = gen.generate(_make_row(status="APPROVAL_REQUIRED"))
        assert len(pm.action_items) >= 1
        assert "approve" in pm.action_items[0].lower() or "review" in pm.action_items[0].lower()

    def test_approved_incident_with_next_checks_gets_followup_actions(self, gen):
        pm = gen.generate(_make_row(status="APPROVED"))
        # next_checks from the diagnosis should become action items
        assert len(pm.action_items) >= 1
