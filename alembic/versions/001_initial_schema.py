"""Initial schema — all V1 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- incidents -----------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("job_name", sa.String(200), nullable=False),
        sa.Column("error_type", sa.String(100), nullable=False),
        sa.Column("error_message", sa.Text, nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_metadata", sa.JSON, nullable=True),
        sa.Column("classification", sa.JSON, nullable=True),
        sa.Column("diagnosis", sa.JSON, nullable=True),
        sa.Column("remediation", sa.JSON, nullable=True),
        sa.Column("simulation", sa.JSON, nullable=True),
        sa.Column("risk", sa.JSON, nullable=True),
        sa.Column("approval_status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])

    # --- incident_events -----------------------------------------------------
    op.create_table(
        "incident_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "incident_id",
            sa.String(36),
            sa.ForeignKey("incidents.incident_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])

    # --- transitions ---------------------------------------------------------
    op.create_table(
        "transitions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "incident_id",
            sa.String(36),
            sa.ForeignKey("incidents.incident_id"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(50), nullable=False),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(200), nullable=True),
    )
    op.create_index("ix_transitions_incident_id", "transitions", ["incident_id"])

    # --- approvals -----------------------------------------------------------
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "incident_id",
            sa.String(36),
            sa.ForeignKey("incidents.incident_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("required_role", sa.String(200), nullable=False),
        sa.Column("reviewer", sa.String(200), nullable=True),
        sa.Column("reviewer_note", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # One approval row per incident — enforce at the DB level
        sa.UniqueConstraint("incident_id", name="uq_approvals_incident_id"),
    )
    op.create_index("ix_approvals_incident_id", "approvals", ["incident_id"])

    # --- feedback ------------------------------------------------------------
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "incident_id",
            sa.String(36),
            sa.ForeignKey("incidents.incident_id"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("overrides", sa.JSON, nullable=True),
        sa.Column("reviewer_notes", sa.String(4000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_incident_id", "feedback", ["incident_id"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("approvals")
    op.drop_table("transitions")
    op.drop_table("incident_events")
    op.drop_table("incidents")
