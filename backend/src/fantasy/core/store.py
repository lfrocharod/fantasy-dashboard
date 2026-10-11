"""Settings and documents through a SQLAlchemy session (the API's side; the
pipelines use the psycopg writer in fantasy.core.db)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fantasy.core import models as M


def get_settings(session: Session, keys: Iterable[str]) -> dict[str, str]:
    rows = session.execute(select(M.Setting.key, M.Setting.value).where(M.Setting.key.in_(list(keys))))
    return {k: v for k, v in rows.tuples()}


def get_setting(session: Session, key: str) -> str | None:
    return session.scalar(select(M.Setting.value).where(M.Setting.key == key))


def set_setting(session: Session, key: str, value: str) -> None:
    stmt = insert(M.Setting).values(key=key, value=value)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[M.Setting.key],
            set_={"value": stmt.excluded.value, "updated_at": func.now()},
        )
    )


def get_document(session: Session, key: str) -> Any:
    return session.scalar(select(M.Document.payload).where(M.Document.key == key))
