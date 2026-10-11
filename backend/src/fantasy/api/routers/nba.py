"""ESPN fantasy basketball (head-to-head points)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from fantasy.api.deps import DB, require_user
from fantasy.api.schemas import nba as S
from fantasy.leagues.nba import views as V

router = APIRouter(prefix="/api/nba", tags=["nba"], dependencies=[Depends(require_user)])


@router.get("/overview", response_model=S.NbaOverview)
def overview(session: DB) -> S.NbaOverview:
    return V.overview(session)


@router.get("/lineup", response_model=S.NbaLineup)
def lineup(session: DB) -> S.NbaLineup:
    return V.lineup_page(session)


@router.get("/players", response_model=S.NbaPlayersResponse)
def players(
    session: DB,
    sort: S.NbaSort = "week",
    position: Annotated[str, Query(pattern="^(ALL|PG|SG|SF|PF|C)$")] = "ALL",
    show: S.NbaShow = "free",
) -> S.NbaPlayersResponse:
    return V.players_page(session, sort, position, show)


@router.get("/schedule", response_model=S.NbaScheduleResponse)
def schedule(session: DB) -> S.NbaScheduleResponse:
    return V.schedule_page(session)


@router.get("/standings", response_model=S.NbaStandingsResponse)
def standings(session: DB) -> S.NbaStandingsResponse:
    return V.standings_page(session)


@router.get("/rivals", response_model=S.NbaRivalsResponse)
def rivals(session: DB) -> S.NbaRivalsResponse:
    return V.rivals_page(session)


@router.get("/trade", response_model=S.NbaTradeLab)
def trade_lab(session: DB, rival: int | None = None) -> S.NbaTradeLab:
    return V.trade_lab(session, rival)


@router.post("/trade/evaluate", response_model=S.NbaTradeEvaluation)
def evaluate_trade(body: S.NbaTradeRequest, session: DB) -> S.NbaTradeEvaluation:
    return V.evaluate_trade(session, body.give, body.get)
