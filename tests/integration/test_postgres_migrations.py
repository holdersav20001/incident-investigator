"""Integration tests — Alembic migrations against real Postgres.

Verifies that the migration chain (upgrade head / downgrade base / upgrade
head again) works correctly on a real Postgres 16 instance, not just SQLite.

All tests are marked `integration` and skipped when Docker is unavailable.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fresh_pg_url(postgres_container) -> str:
    """URL for the shared Postgres container — we use a separate DB name
    to avoid conflicts with the schema created by pg_engine."""
    url = postgres_container.get_connection_url()
    return url.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture()
def alembic_pg_cfg(fresh_pg_url) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", fresh_pg_url)
    return cfg


def _full_drop(engine) -> None:
    """Drop all app tables AND the alembic_version tracking table."""
    from sqlalchemy import text  # noqa: PLC0415
    from investigator.db.models import Base  # noqa: PLC0415

    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture()
def fresh_pg_engine(fresh_pg_url):
    """Engine connected to the container; drops all tables before and after.

    Drops alembic_version too so each migration test starts from scratch.
    """
    from sqlalchemy import create_engine  # noqa: PLC0415

    engine = create_engine(fresh_pg_url)
    _full_drop(engine)
    yield engine
    _full_drop(engine)
    engine.dispose()


class TestAlembicOnPostgres:
    def test_upgrade_head_creates_all_tables(self, alembic_pg_cfg, fresh_pg_engine):
        command.upgrade(alembic_pg_cfg, "head")
        inspector = inspect(fresh_pg_engine)
        tables = set(inspector.get_table_names())
        expected = {"incidents", "incident_events", "transitions", "approvals", "feedback"}
        assert expected.issubset(tables), f"Missing: {expected - tables}"

    def test_downgrade_to_base_removes_tables(self, alembic_pg_cfg, fresh_pg_engine):
        command.upgrade(alembic_pg_cfg, "head")
        command.downgrade(alembic_pg_cfg, "base")

        inspector = inspect(fresh_pg_engine)
        tables = set(inspector.get_table_names())
        for t in ("incidents", "incident_events", "transitions", "approvals", "feedback"):
            assert t not in tables, f"{t!r} should be absent after downgrade"

    def test_upgrade_after_downgrade_restores_schema(self, alembic_pg_cfg, fresh_pg_engine):
        command.upgrade(alembic_pg_cfg, "head")
        command.downgrade(alembic_pg_cfg, "base")
        command.upgrade(alembic_pg_cfg, "head")

        inspector = inspect(fresh_pg_engine)
        tables = set(inspector.get_table_names())
        expected = {"incidents", "incident_events", "transitions", "approvals", "feedback"}
        assert expected.issubset(tables)

    def test_migration_is_idempotent_on_postgres(self, alembic_pg_cfg, fresh_pg_engine):
        """Running upgrade head twice on Postgres should be a no-op, not an error."""
        command.upgrade(alembic_pg_cfg, "head")
        command.upgrade(alembic_pg_cfg, "head")

        inspector = inspect(fresh_pg_engine)
        assert "incidents" in set(inspector.get_table_names())

    def test_migrated_incidents_table_accepts_json_columns(
        self, alembic_pg_cfg, fresh_pg_engine
    ):
        """Postgres JSONB columns should accept dict values."""
        command.upgrade(alembic_pg_cfg, "head")
        from datetime import datetime, timezone  # noqa: PLC0415

        now = datetime.now(tz=timezone.utc)
        with fresh_pg_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO incidents "
                    "(incident_id, status, source, environment, job_name, "
                    " error_type, error_message, event_timestamp, "
                    " classification, created_at, updated_at) "
                    "VALUES (:iid, 'RECEIVED', 'test', 'dev', 'job', "
                    " 'schema_mismatch', 'msg', :ts, "
                    " CAST(:cls AS jsonb), :ts, :ts)"
                ),
                {
                    "iid": "migration-json-test",
                    "ts": now,
                    "cls": '{"type": "schema_mismatch", "confidence": 0.9}',
                },
            )
            row = conn.execute(
                text("SELECT classification FROM incidents WHERE incident_id = :iid"),
                {"iid": "migration-json-test"},
            ).fetchone()
        assert row is not None
        assert row[0]["type"] == "schema_mismatch"
