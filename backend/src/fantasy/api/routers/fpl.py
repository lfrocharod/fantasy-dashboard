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


@router.get("/teams", response_model=S.FplTeamsResponse)
def teams(session: DB) -> S.FplTeamsResponse:
    return V.teams_page(session)


@router.get("/fixtures", response_model=S.FplFixturesResponse)
def fixtures(session: DB) -> S.FplFixturesResponse:
    return V.fixtures_page(session)


@router.get("/optimizer", response_model=S.FplOptimizerResponse)
def optimizer(session: DB, horizon: S.Horizon = "medium") -> S.FplOptimizerResponse:
    return V.optimizer_page(session, horizon)


@router.get("/rivals", response_model=S.FplRivalsResponse)
def rivals(session: DB) -> S.FplRivalsResponse:
    return V.rivals_page(session)


@router.get("/standings", response_model=S.FplStandingsResponse)
def standings(session: DB) -> S.FplStandingsResponse:
    return V.standings_page(session)


@router.get("/trade", response_model=S.FplTradeLab)
def trade_lab(session: DB, horizon: S.Horizon = "medium") -> S.FplTradeLab:
    return V.trade_lab(session, horizon)


@router.post("/trade/evaluate", response_model=S.FplTradeEvaluation)
def evaluate_trade(body: S.FplTradeRequest, session: DB) -> S.FplTradeEvaluation:
    return V.evaluate_trade(session, body.give, body.get)
