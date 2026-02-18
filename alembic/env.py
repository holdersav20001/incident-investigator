"""Alembic environment configuration.

Supports both online (direct DB connection) and offline (SQL script) modes.
The target_metadata is sourced from the application's SQLAlchemy Base so
`alembic revision --autogenerate` can diff against the real ORM models.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Import the Base that owns all ORM models so autogenerate works
from investigator.db.models import Base

# ---- Alembic Config object (provides access to .ini values) ----------------
config = context.config

# Use DATABASE_URL env var if set, otherwise fall back to alembic.ini value
_db_url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

# Interpret the config file for Python logging.
# Skip during pytest runs — fileConfig would override caplog's logging config,
# causing test failures in unrelated test suites that rely on caplog.
import os as _os
if config.config_file_name is not None and not _os.environ.get("PYTEST_CURRENT_TEST"):
    fileConfig(config.config_file_name)

# The metadata object for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout, no DB required."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the real database."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),  # type: ignore[arg-type]
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
