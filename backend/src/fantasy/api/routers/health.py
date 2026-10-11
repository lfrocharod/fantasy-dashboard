"""Liveness / readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from fantasy.api.deps import DB
from fantasy.api.schemas.common import Ok

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=Ok)
def live() -> Ok:
    return Ok()


@router.get("/ready", response_model=Ok)
def ready(session: DB) -> Ok:
    try:
        session.execute(text("select 1"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"database unavailable: {type(e).__name__}") from e
    return Ok()
