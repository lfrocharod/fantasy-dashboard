"""ESPN NFL (in season)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from fantasy.api.deps import DB, require_user
from fantasy.api.schemas import nfl as S
from fantasy.leagues.nfl import views as V

router = APIRouter(prefix="/api/nfl", tags=["nfl"], dependencies=[Depends(require_user)])


@router.get("/overview", response_model=S.NflOverview)
def overview(session: DB) -> S.NflOverview:
    return V.overview(session)


@router.get("/players", response_model=S.PlayersResponse)
def players(
    session: DB,
    horizon: Literal["week", "ros"] = "ros",
    position: Annotated[str, Query(pattern="^(ALL|QB|RB|WR|TE|DST|K)$")] = "ALL",
) -> S.PlayersResponse:
    return V.players_page(session, horizon, position)


@router.get("/teams", response_model=S.TeamsResponse)
def teams(session: DB) -> S.TeamsResponse:
    return V.teams_page(session)


@router.get("/fixtures", response_model=S.FixturesResponse)
def fixtures(session: DB) -> S.FixturesResponse:
    return V.fixtures_page(session)


@router.get("/optimizer", response_model=S.NflOptimizer)
def optimizer(session: DB) -> S.NflOptimizer:
    return V.optimizer_page(session)


@router.get("/rivals", response_model=S.RivalsResponse)
def rivals(session: DB) -> S.RivalsResponse:
    return V.rivals_page(session)


@router.get("/standings", response_model=S.StandingsResponse)
def standings(session: DB, seeding: S.SeedingRule | None = None) -> S.StandingsResponse:
    return V.standings_page(session, seeding)


@router.get("/trade", response_model=S.TradeLab)
def trade_lab(session: DB, rival: int | None = None) -> S.TradeLab:
    return V.trade_lab(session, rival)


@router.post("/trade/evaluate", response_model=S.TradeEvaluation)
def evaluate_trade(body: S.TradeRequest, session: DB) -> S.TradeEvaluation:
    return V.evaluate_trade(session, body.give, body.get)
