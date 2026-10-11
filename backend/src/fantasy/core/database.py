"""SQLAlchemy engine + session factory (the API's read/write path)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def database_url(raw: str | None = None) -> str:
    """DATABASE_URL in the form SQLAlchemy wants: the psycopg 3 driver."""
    url = raw if raw is not None else os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache(maxsize=1)
def engine() -> Engine:
    url = database_url()
    connect_args: dict[str, object] = {"connect_timeout": 10}
    if "-pooler." in url:
        # Neon's pooled endpoint is PgBouncer in transaction mode: don't rely on
        # server-side prepared statements surviving between transactions.
        connect_args["prepare_threshold"] = None
    return create_engine(
        url,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
        max_overflow=5,
        # Neon suspends idle computes and drops their sockets; check before use.
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )


@lru_cache(maxsize=1)
def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed afterwards."""
    with session_factory()() as session:
        yield session
