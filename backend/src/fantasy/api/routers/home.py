"""The cross-league command centre."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fantasy import home
from fantasy.api.deps import DB, require_user
from fantasy.api.schemas.home import HomeSummary

router = APIRouter(prefix="/api", tags=["home"], dependencies=[Depends(require_user)])


@router.get("/home", response_model=HomeSummary)
def home_summary(session: DB) -> HomeSummary:
    return home.summary(session)
