"""Integration smoke tests — verify Postgres container + schema.

These tests confirm that:
- The Postgres container starts and is reachable
- Base.metadata.create_all produces the expected tables
- A basic INSERT + SELECT round-trip works

All tests are marked `integration` and skipped when Docker is unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration


class TestPostgresConnection:
    def test_container_is_reachable(self, pg_engine):
        """Simple SELECT 1 confirms the container accepted the connection."""
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1

    def test_postgres_version_is_16(self, pg_engine):
        with pg_engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        assert "PostgreSQL 16" in version, f"Unexpected version: {version}"


class TestSchemaCreation:
    def test_all_tables_exist(self, pg_engine):
        inspector = inspect(pg_engine)
        tables = set(inspector.get_table_names())
        expected = {"incidents", "incident_events", "transitions", "approvals", "feedback"}
        assert expected.issubset(tables), f"Missing: {expected - tables}"

    def test_incidents_primary_key_is_incident_id(self, pg_engine):
        inspector = inspect(pg_engine)
        pk = inspector.get_pk_constraint("incidents")
        assert "incident_id" in pk["constrained_columns"]

    def test_approvals_has_unique_incident_id(self, pg_engine):
        # Postgres may represent column-level unique as an index rather than a
        # named constraint — check both.
        inspector = inspect(pg_engine)
        unique_from_constraints = {
            col
            for uc in inspector.get_unique_constraints("approvals")
            for col in uc["column_names"]
        }
        unique_from_indexes = {
            col
            for idx in inspector.get_indexes("approvals")
            if idx.get("unique")
            for col in idx["column_names"]
        }
        assert "incident_id" in unique_from_constraints | unique_from_indexes


class TestBasicRoundTrip:
    def test_insert_and_read_incident(self, pg_session):
        """Insert a minimal incident row and read it back."""
        from investigator.db.models import IncidentRow  # noqa: PLC0415

        now = datetime.now(tz=timezone.utc)
        row = IncidentRow(
            incident_id="test-integration-001",
            status="RECEIVED",
            source="test",
            environment="dev",
            job_name="smoke_test_job",
            error_type="schema_mismatch",
            error_message="Integration test",
            event_timestamp=now,
            created_at=now,
            updated_at=now,
        )
        pg_session.add(row)
        pg_session.flush()

        fetched = pg_session.get(IncidentRow, "test-integration-001")
        assert fetched is not None
        assert fetched.status == "RECEIVED"
        assert fetched.job_name == "smoke_test_job"
