"""Draft-night board: tap picks as they happen."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from fantasy import settings_views as V
from fantasy.api.deps import DB, require_user, writable
from fantasy.api.schemas.common import Ok, Schema
from fantasy.api.schemas.home import DraftBoard, PickRequest

router = APIRouter(prefix="/api/draft", tags=["draft"], dependencies=[Depends(require_user)])


class PickAdded(Schema):
    ok: bool = True
    overall: int


@router.get("/board", response_model=DraftBoard)
def board(session: DB, sport: Literal["nfl", "fpl"] = "nfl") -> DraftBoard:
    return V.board(session, sport)


@router.post("/pick", response_model=PickAdded, dependencies=[Depends(writable)])
def add_pick(body: PickRequest, session: DB) -> PickAdded:
    return PickAdded(overall=V.add_pick(session, body))


@router.delete("/pick", response_model=Ok, dependencies=[Depends(writable)])
def undo_pick(session: DB, sport: Literal["nfl", "fpl"] = "nfl", all: bool = False) -> Ok:  # noqa: A002
    return Ok(ok=V.undo_pick(session, sport, reset=all))
