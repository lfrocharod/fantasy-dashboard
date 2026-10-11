"""Champions League Fantasy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from fantasy.api.deps import DB, require_user
from fantasy.api.schemas import ucl as S
from fantasy.leagues.ucl import views as V

router = APIRouter(prefix="/api/ucl", tags=["ucl"], dependencies=[Depends(require_user)])


@router.get("/overview", response_model=S.UclOverview)
def overview(session: DB) -> S.UclOverview:
    return V.overview(session)


@router.get("/players", response_model=S.PlayersResponse)
def players(
    session: DB,
    position: Annotated[str | None, Query(pattern="^(GK|DEF|MID|FWD)$")] = None,
    max_price: Annotated[float | None, Query(alias="maxPrice", ge=0)] = None,
    search: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=400)] = 250,
) -> S.PlayersResponse:
    return V.players_page(session, position=position, max_price=max_price, search=search, limit=limit)


@router.get("/teams", response_model=S.TeamsResponse)
def teams(session: DB) -> S.TeamsResponse:
    return V.teams_page(session)


@router.get("/fixtures", response_model=S.FixturesResponse)
def fixtures(session: DB) -> S.FixturesResponse:
    return V.fixtures_page(session)


@router.get("/optimizer", response_model=S.OptimizerResponse)
def optimizer(session: DB) -> S.OptimizerResponse:
    return V.optimizer_page(session)


@router.get("/rivals", response_model=S.RivalsResponse)
def rivals(session: DB) -> S.RivalsResponse:
    return V.rivals_page(session)


@router.get("/league", response_model=S.LeagueResponse)
def league(session: DB) -> S.LeagueResponse:
    return V.league_page(session)
