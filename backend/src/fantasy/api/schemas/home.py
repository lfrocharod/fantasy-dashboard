"""Home (cross-league command centre) + settings + draft-board models."""

from __future__ import annotations

from typing import Literal

from fantasy.api.schemas.common import Schema
from fantasy.api.schemas.ucl import XgCoverage

LeagueTag = Literal["UCL", "FPL", "NFL", "NBA"]


class Alert(Schema):
    league: LeagueTag
    tone: Literal["bad", "warn", "accent"]
    text: str
    href: str


class UclLive(Schema):
    # the matchday these numbers belong to: one behind UclHome.matchday while a
    # finished matchday's result is kept up until the next one kicks off
    matchday: int
    state: str
    secured: float
    projected_finish: float
    played: int
    starters: int
    manual_subs: int
    captain_note: str | None


class UclHome(Schema):
    active: bool
    matchday: int
    deadline_iso: str | None
    projected: int
    captain: str | None
    rank: int | None
    league_size: int
    ingest_ok: bool | None
    ingest_at: str | None
    live: UclLive | None


class Claim(Schema):
    name: str
    gain: int


class FplLiveHome(Schema):
    gw: int
    state: Literal["live", "finished"]
    secured: float
    played: int
    starters: int


class FplHome(Schema):
    active: bool
    gw: int | None
    xi_proj: int
    rank: int | None
    top_claim: Claim | None
    injured: int
    live: FplLiveHome | None


class NflLiveHome(Schema):
    mine: float
    opp: float
    final: bool


class NflHome(Schema):
    active: bool
    week: int | None
    my_proj: int
    opp_name: str | None
    opp_proj: int | None
    win_pct: int | None
    lineup_issues: int
    top_claim: Claim | None
    live: NflLiveHome | None


class NbaHome(Schema):
    active: bool
    period: int | None
    days_left: int
    my_proj: int
    opp_name: str | None
    opp_proj: int | None
    win_pct: int | None
    live: NflLiveHome | None
    tonight: int  # lineup changes to make for the next game day
    top_stream: Claim | None


class Freshness(Schema):
    """When each league's data last landed — the home runner going quiet shows
    up here before it costs a deadline."""

    league: LeagueTag
    updated_at: str | None
    stale: bool


class HomeSummary(Schema):
    ucl: UclHome
    fpl: FplHome
    nfl: NflHome
    nba: NbaHome
    alerts: list[Alert]
    freshness: list[Freshness]


# ---- settings ------------------------------------------------------------------------


class UclSettings(Schema):
    league_id: str
    league_code: str
    entry_id: str
    matchday_override: str
    deadline_iso: str
    auth_state: str
    token_saved_at: str | None
    has_token: bool
    model_params: str
    xg_coverage: XgCoverage | None


class UclSettingsUpdate(Schema):
    league_id: str | None = None
    league_code: str | None = None
    entry_id: str | None = None
    matchday_override: int | None = None  # 0 clears the pin
    uefa_token: str | None = None
    model_params: str | None = None


class DraftConfig(Schema):
    sport: Literal["nfl", "fpl", "nba"]
    league_id: str
    my_team_id: str
    my_slot: str
    teams: str
    scoring: str
    year: str
    roster: str
    entry_id: str
    has_cookies: bool
    # NBA: no ESPN cookies of its own, but the NFL ones are stored (same account)
    shared_login: bool = False


class DraftConfigUpdate(Schema):
    sport: Literal["nfl", "fpl", "nba"] = "nfl"
    league_id: str | None = None
    my_team_id: int | None = None
    my_slot: int | None = None
    teams: int | None = None
    scoring: Literal["ppr", "half", "standard"] | None = None
    year: int | None = None
    espn_s2: str | None = None
    swid: str | None = None
    entry_id: str | None = None
    pl_profile: str | None = None


# ---- draft board (NFL pre-draft) -------------------------------------------------------


class BoardPlayer(Schema):
    ext_id: str
    name: str
    team: str
    positions: str
    primary_pos: str
    proj_points: float
    adp: float
    provider_rank: int | None
    ecr_rank: int | None
    ecr_tier: int | None
    ecr_pos_rank: str
    ecr_std: float
    vbd: float
    bye_week: int | None
    injury_status: str
    outlook: str


class BoardPick(Schema):
    overall: int
    team_id: int
    team_name: str
    player_ext_id: str
    is_mine: bool
    source: str


class DraftBoard(Schema):
    sport: Literal["nfl", "fpl"]
    players: list[BoardPlayer]
    picks: list[BoardPick]
    teams: int
    my_slot: int | None
    roster: dict[str, int]


class PickRequest(Schema):
    sport: Literal["nfl", "fpl"] = "nfl"
    ext_id: str
    is_mine: bool = False
    team_id: int | None = None
    team_name: str | None = None


class SessionInfo(Schema):
    authenticated: bool
    demo: bool
