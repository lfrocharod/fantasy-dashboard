"""FastAPI dependencies: database session and the auth gate."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fantasy.api.security import SESSION_COOKIE, demo_mode, verify_session_token
from fantasy.core.database import get_session


def db() -> Iterator[Session]:
    yield from get_session()


def require_user(fd_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> None:
    if demo_mode():
        return
    if not verify_session_token(fd_session):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")


def writable() -> None:
    """Endpoints that change data are refused in the public demo."""
    if demo_mode():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this is a read-only demo")


DB = Annotated[Session, Depends(db)]
