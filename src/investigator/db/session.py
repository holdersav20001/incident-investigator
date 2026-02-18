"""Engine and session-factory helpers."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.environ.get(
        "DATABASE_URL", "sqlite:///:memory:"
    )
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, echo=False)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)
