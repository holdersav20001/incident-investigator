"""SQLAlchemy ORM models — V1 schema.

All JSON/JSONB fields use SA's JSON type (maps to JSONB on Postgres,
TEXT on SQLite) so tests run without a real database.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class IncidentRow(Base):
    """Primary incident record — source of truth for state."""

    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Ingest fields (denormalised for fast reads)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_metadata: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Agent outputs (append-only JSONB blobs)
    classification: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    diagnosis: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    remediation: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    simulation: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    risk: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    approval_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["IncidentEventRow"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    transitions: Mapped[list["TransitionRow"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class IncidentEventRow(Base):
    """Append-only log of all events received for an incident."""

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.incident_id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    incident: Mapped["IncidentRow"] = relationship(back_populates="events")


class TransitionRow(Base):
    """Append-only audit trail of every state transition."""

    __tablename__ = "transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.incident_id"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(50), nullable=False)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    incident: Mapped["IncidentRow"] = relationship(back_populates="transitions")


class ApprovalRow(Base):
    """Human approval queue — one record per incident that requires review."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.incident_id"), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pending|approved|rejected
    required_role: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewer: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reviewer_note: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped["IncidentRow"] = relationship()


class FeedbackRow(Base):
    """Outcome feedback from engineers — learning loop signal."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.incident_id"), nullable=False, index=True
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # fixed|not_fixed|unknown
    overrides: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(String(4000), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    incident: Mapped["IncidentRow"] = relationship()
