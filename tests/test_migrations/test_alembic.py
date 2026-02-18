"""Smoke tests for Alembic migrations.

Verifies that running `alembic upgrade head` against a fresh SQLite database
creates all expected tables with the expected columns.  No Postgres required
in CI — SQLite is sufficient to validate the migration logic.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

EXPECTED_TABLES = {
    "incidents",
    "incident_events",
    "transitions",
    "approvals",
    "feedback",
}


@pytest.fixture(scope="module")
def alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    # Use an in-memory SQLite database for the migration smoke test
    cfg.set_main_option("sqlalchemy.url", "sqlite:///:memory:")
    return cfg


@pytest.fixture(scope="module")
def migrated_engine(alembic_cfg, tmp_path_factory):
    """Run upgrade head on a fresh in-memory SQLite db."""
    # We need a file-based SQLite for alembic to reuse across connections
    db_path = tmp_path_factory.mktemp("migration") / "test.db"
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    yield engine
    engine.dispose()


class TestMigrationUpgrade:
    def test_all_expected_tables_created(self, migrated_engine):
        inspector = inspect(migrated_engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(tables), (
            f"Missing tables: {EXPECTED_TABLES - tables}"
        )

    def test_incidents_table_has_required_columns(self, migrated_engine):
        inspector = inspect(migrated_engine)
        cols = {c["name"] for c in inspector.get_columns("incidents")}
        required = {
            "incident_id", "status", "source", "environment",
            "job_name", "error_type", "error_message", "event_timestamp",
            "classification", "diagnosis", "remediation", "simulation",
            "risk", "approval_status", "created_at", "updated_at",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_incident_events_table_has_required_columns(self, migrated_engine):
        inspector = inspect(migrated_engine)
        cols = {c["name"] for c in inspector.get_columns("incident_events")}
        assert {"id", "incident_id", "event_type", "payload", "occurred_at"}.issubset(cols)

    def test_transitions_table_has_required_columns(self, migrated_engine):
        inspector = inspect(migrated_engine)
        cols = {c["name"] for c in inspector.get_columns("transitions")}
        assert {"id", "incident_id", "from_status", "to_status", "transitioned_at"}.issubset(cols)

    def test_approvals_table_has_required_columns(self, migrated_engine):
        inspector = inspect(migrated_engine)
        cols = {c["name"] for c in inspector.get_columns("approvals")}
        assert {
            "id", "incident_id", "status", "required_role", "reviewer",
            "reviewer_note", "created_at", "reviewed_at",
        }.issubset(cols)

    def test_feedback_table_has_required_columns(self, migrated_engine):
        inspector = inspect(migrated_engine)
        cols = {c["name"] for c in inspector.get_columns("feedback")}
        assert {"id", "incident_id", "outcome", "submitted_at"}.issubset(cols)

    def test_incidents_primary_key_is_incident_id(self, migrated_engine):
        inspector = inspect(migrated_engine)
        pk = inspector.get_pk_constraint("incidents")
        assert "incident_id" in pk["constrained_columns"]

    def test_approvals_has_unique_incident_id(self, migrated_engine):
        inspector = inspect(migrated_engine)
        unique_constraints = inspector.get_unique_constraints("approvals")
        unique_cols = {col for uc in unique_constraints for col in uc["column_names"]}
        indexes = inspector.get_indexes("approvals")
        unique_index_cols = {
            col for idx in indexes if idx.get("unique") for col in idx["column_names"]
        }
        assert "incident_id" in unique_cols or "incident_id" in unique_index_cols, (
            "approvals.incident_id should be unique"
        )

    def test_migration_is_idempotent(self, alembic_cfg, tmp_path_factory):
        """Running upgrade head twice should not raise."""
        db_path = tmp_path_factory.mktemp("idempotent") / "test.db"
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")
        command.upgrade(alembic_cfg, "head")  # second run — should be a no-op


class TestMigrationDowngrade:
    def test_downgrade_to_base_removes_tables(self, alembic_cfg, tmp_path_factory):
        db_path = tmp_path_factory.mktemp("downgrade") / "test.db"
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")

        engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        for table in EXPECTED_TABLES:
            assert table not in tables, f"Table {table!r} should be gone after downgrade"

    def test_upgrade_after_downgrade_restores_tables(self, alembic_cfg, tmp_path_factory):
        db_path = tmp_path_factory.mktemp("roundtrip") / "test.db"
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        assert EXPECTED_TABLES.issubset(tables)
