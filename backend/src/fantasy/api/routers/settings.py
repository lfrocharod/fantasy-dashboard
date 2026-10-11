"""League connections and setup."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from fantasy import settings_views as V
from fantasy.api.deps import DB, require_user, writable
from fantasy.api.schemas.common import Ok
from fantasy.api.schemas.home import DraftConfig, DraftConfigUpdate, UclSettings, UclSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_user)])


@router.get("/ucl", response_model=UclSettings)
def get_ucl(session: DB) -> UclSettings:
    return V.ucl_settings(session)


@router.post("/ucl", response_model=Ok, dependencies=[Depends(writable)])
def save_ucl(body: UclSettingsUpdate, session: DB) -> Ok:
    try:
        V.update_ucl_settings(session, body)
    except ValueError as e:
        raise HTTPException(400, f"model parameters must be valid JSON: {e}") from e
    return Ok()


@router.get("/draft", response_model=DraftConfig)
def get_draft(session: DB, sport: Literal["nfl", "fpl"] = "nfl") -> DraftConfig:
    return V.draft_config(session, sport)


@router.post("/draft", response_model=Ok, dependencies=[Depends(writable)])
def save_draft(body: DraftConfigUpdate, session: DB) -> Ok:
    V.update_draft_config(session, body)
    return Ok()
