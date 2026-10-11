"""FPL Draft."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fantasy.api.deps import DB, require_user
from fantasy.api.schemas import fpl as S
from fantasy.leagues.fpl import views as V

router = APIRouter(prefix="/api/fpl", tags=["fpl"], dependencies=[Depends(require_user)])


@router.get("/board", response_model=S.BoardResponse)
def board(session: DB) -> S.BoardResponse:
    return V.board_page(session)


@router.get("/overview", response_model=S.FplOverview)
def overview(session: DB) -> S.FplOverview:
    return V.overview(session)


@router.get("/teams", response_model=S.TeamsResponse)
def teams(session: DB) -> S.TeamsResponse:
    return V.teams_page(session)


@router.get("/fixtures", response_model=S.FixturesResponse)
def fixtures(session: DB) -> S.FixturesResponse:
    return V.fixtures_page(session)


@router.get("/optimizer", response_model=S.OptimizerResponse)
def optimizer(session: DB, horizon: S.Horizon = "medium") -> S.OptimizerResponse:
    return V.optimizer_page(session, horizon)


@router.get("/rivals", response_model=S.RivalsResponse)
def rivals(session: DB) -> S.RivalsResponse:
    return V.rivals_page(session)


@router.get("/standings", response_model=S.StandingsResponse)
def standings(session: DB) -> S.StandingsResponse:
    return V.standings_page(session)


@router.get("/trade", response_model=S.TradeLab)
def trade_lab(session: DB, horizon: S.Horizon = "medium") -> S.TradeLab:
    return V.trade_lab(session, horizon)


@router.post("/trade/evaluate", response_model=S.TradeEvaluation)
def evaluate_trade(body: S.TradeRequest, session: DB) -> S.TradeEvaluation:
    return V.evaluate_trade(session, body.give, body.get)
