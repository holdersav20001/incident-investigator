"""Postmortem generator — produces a structured blameless postmortem in Markdown.

`PostmortemGenerator.generate(row)` accepts a completed `IncidentRow` and
returns a `Postmortem` dataclass whose `.markdown` property renders the full
document ready for Confluence / GitHub / PagerDuty.

Sections (aligned with Google SRE blameless postmortem template):
  1. Executive Summary
  2. Incident Timeline
  3. Root Cause Analysis
  4. Remediation Plan
  5. Risk Assessment
  6. Impact & Blast Radius
  7. Action Items
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from investigator.db.models import IncidentRow


# ---------------------------------------------------------------------------
# Postmortem data model
# ---------------------------------------------------------------------------

@dataclass
class Postmortem:
    """Structured postmortem output from PostmortemGenerator.generate()."""

    incident_id: str
    title: str
    status: str
    environment: str
    job_name: str
    error_type: str
    error_message: str
    incident_timestamp: str
    generated_at: str
    root_cause: str
    confidence: float | None
    next_checks: list[str]
    remediation_steps: list[str]
    rollback_steps: list[str]
    estimated_time_minutes: int | None
    simulation_ok: bool | None
    simulation_notes: list[str]
    risk_score: int | None
    risk_level: str | None
    recommendation: str | None
    rationale: str | None
    blast_radius: list[str]
    action_items: list[str] = field(default_factory=list)

    @property
    def markdown(self) -> str:
        """Render this postmortem as a Markdown document."""
        lines: list[str] = []

        # Header
        lines += [
            f"# Postmortem — {self.title}",
            "",
            f"**Incident ID:** `{self.incident_id}`  ",
            f"**Status:** {self.status}  ",
            f"**Environment:** {self.environment}  ",
            f"**Job:** {self.job_name}  ",
            f"**Generated:** {self.generated_at}",
            "",
            "---",
            "",
        ]

        # Executive Summary
        lines += [
            "## Executive Summary",
            "",
            f"A `{self.error_type}` incident occurred in **{self.environment}** for job "
            f"`{self.job_name}` at {self.incident_timestamp}.  ",
            f"**Final disposition:** {self.status}.",
            "",
        ]

        if self.root_cause:
            lines += [f"> **Root cause:** {self.root_cause}", ""]

        # Timeline
        lines += [
            "## Incident Timeline",
            "",
            f"| Time | Event |",
            f"|------|-------|",
            f"| {self.incident_timestamp} | Incident ingested — `{self.error_type}` detected |",
            f"| {self.generated_at} | Postmortem generated |",
            "",
        ]

        # Root Cause Analysis
        lines += [
            "## Root Cause Analysis",
            "",
            self.root_cause or "_No root cause recorded._",
            "",
        ]
        if self.confidence is not None:
            lines += [f"**Diagnosis confidence:** {self.confidence:.0%}", ""]
        if self.next_checks:
            lines += ["**Recommended follow-up checks:**", ""]
            lines += [f"- {c}" for c in self.next_checks]
            lines += [""]

        # Remediation Plan
        lines += ["## Remediation Plan", ""]
        if self.remediation_steps:
            lines += ["**Steps:**", ""]
            for i, step in enumerate(self.remediation_steps, 1):
                lines.append(f"{i}. {step}")
            lines += [""]
        else:
            lines += ["_No remediation plan recorded._", ""]

        if self.rollback_steps:
            lines += ["**Rollback steps:**", ""]
            lines += [f"- {s}" for s in self.rollback_steps]
            lines += [""]

        if self.estimated_time_minutes is not None:
            lines += [f"**Estimated resolution time:** {self.estimated_time_minutes} minutes", ""]

        # Simulation Results
        lines += ["## Simulation Results", ""]
        if self.simulation_ok is None:
            lines += ["_Simulation not run._", ""]
        else:
            icon = "✅" if self.simulation_ok else "❌"
            lines += [f"**Plan safety check:** {icon} {'PASSED' if self.simulation_ok else 'FAILED'}", ""]
            if self.simulation_notes:
                lines += [f"- {n}" for n in self.simulation_notes]
                lines += [""]

        # Risk Assessment
        lines += ["## Risk Assessment", ""]
        if self.risk_level:
            lines += [
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Risk score | {self.risk_score}/100 |",
                f"| Risk level | **{self.risk_level}** |",
                f"| Recommendation | {self.recommendation} |",
                "",
            ]
        else:
            lines += ["_Risk assessment not recorded._", ""]

        if self.rationale:
            lines += [f"**Rationale:** {self.rationale}", ""]

        # Impact / Blast Radius
        lines += ["## Impact & Blast Radius", ""]
        if self.blast_radius:
            lines += [f"- {b}" for b in self.blast_radius]
            lines += [""]
        else:
            lines += ["_No blast radius recorded._", ""]

        # Action Items
        lines += ["## Action Items", ""]
        if self.action_items:
            for i, item in enumerate(self.action_items, 1):
                lines.append(f"{i}. {item}")
            lines += [""]
        else:
            lines += ["_Review incident findings and add action items._", ""]

        lines += [
            "---",
            "",
            "*Generated by Autonomous Data Incident Investigator — blameless postmortem template.*",
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class PostmortemGenerator:
    """Produces a structured Postmortem from a completed IncidentRow."""

    def generate(self, row: IncidentRow) -> Postmortem:
        """Convert a persisted IncidentRow into a Postmortem document."""
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event_ts = (
            row.event_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
            if row.event_timestamp
            else "unknown"
        )
        title = f"{row.error_type} — {row.job_name}"

        # Diagnosis
        root_cause = ""
        confidence: float | None = None
        next_checks: list[str] = []
        if row.diagnosis:
            root_cause = row.diagnosis.get("root_cause", "")
            confidence = row.diagnosis.get("confidence")
            next_checks = row.diagnosis.get("next_checks") or []

        # Remediation
        remediation_steps: list[str] = []
        rollback_steps: list[str] = []
        estimated_time: int | None = None
        if row.remediation:
            remediation_steps = [
                s.get("step", "") for s in (row.remediation.get("plan") or [])
            ]
            rollback_steps = [
                s.get("step", "") for s in (row.remediation.get("rollback") or [])
            ]
            estimated_time = row.remediation.get("expected_time_minutes")

        # Simulation
        simulation_ok: bool | None = None
        simulation_notes: list[str] = []
        if row.simulation:
            simulation_ok = row.simulation.get("ok")
            simulation_notes = row.simulation.get("notes") or []

        # Risk
        risk_score: int | None = None
        risk_level: str | None = None
        recommendation: str | None = None
        rationale: str | None = None
        blast_radius: list[str] = []
        if row.risk:
            risk_score = row.risk.get("risk_score")
            risk_level = row.risk.get("risk_level")
            recommendation = row.risk.get("recommendation")
            rationale = row.risk.get("rationale")
            blast_radius = row.risk.get("blast_radius") or []

        # Default action items derived from state
        action_items: list[str] = []
        if row.status == "REJECTED":
            action_items = [
                "Review remediation plan for unsafe steps and revise",
                "Re-run investigation after plan is corrected",
            ]
        elif row.status in ("APPROVAL_REQUIRED",):
            action_items = [
                "On-call engineer to review and approve or reject",
            ]
        elif next_checks:
            action_items = [f"Investigate: {c}" for c in next_checks[:3]]

        return Postmortem(
            incident_id=row.incident_id,
            title=title,
            status=row.status,
            environment=row.environment,
            job_name=row.job_name,
            error_type=row.error_type,
            error_message=row.error_message,
            incident_timestamp=event_ts,
            generated_at=now,
            root_cause=root_cause,
            confidence=confidence,
            next_checks=next_checks,
            remediation_steps=remediation_steps,
            rollback_steps=rollback_steps,
            estimated_time_minutes=estimated_time,
            simulation_ok=simulation_ok,
            simulation_notes=simulation_notes,
            risk_score=risk_score,
            risk_level=risk_level,
            recommendation=recommendation,
            rationale=rationale,
            blast_radius=blast_radius,
            action_items=action_items,
        )
