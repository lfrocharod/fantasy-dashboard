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


@router.get("/players", response_model=S.UclPlayersResponse)
def players(
    session: DB,
    position: Annotated[str | None, Query(pattern="^(GK|DEF|MID|FWD)$")] = None,
    max_price: Annotated[float | None, Query(alias="maxPrice", ge=0)] = None,
    search: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=400)] = 250,
) -> S.UclPlayersResponse:
    return V.players_page(session, position=position, max_price=max_price, search=search, limit=limit)


@router.get("/teams", response_model=S.UclTeamsResponse)
def teams(session: DB) -> S.UclTeamsResponse:
    return V.teams_page(session)


@router.get("/fixtures", response_model=S.UclFixturesResponse)
def fixtures(session: DB) -> S.UclFixturesResponse:
    return V.fixtures_page(session)


@router.get("/optimizer", response_model=S.UclOptimizerResponse)
def optimizer(session: DB) -> S.UclOptimizerResponse:
    return V.optimizer_page(session)


@router.get("/rivals", response_model=S.UclRivalsResponse)
def rivals(session: DB) -> S.UclRivalsResponse:
    return V.rivals_page(session)


@router.get("/league", response_model=S.LeagueResponse)
def league(session: DB) -> S.LeagueResponse:
    return V.league_page(session)
