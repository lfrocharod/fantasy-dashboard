"""FPL Draft response models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from fantasy.api.schemas.common import CheckItem, Schema

Horizon = Literal["short", "medium", "season"]


class GwCell(Schema):
    gw: int
    opp: str
    home: bool | None
    fdr: int
    fdr_att: int | None = None
    fdr_def: int | None = None
    xpts: float
    lo: float | None = None
    hi: float | None = None
    cs: float


class FplPlayer(Schema):
    ext_id: str
    name: str
    team: str
    pos: str
    proj: float
    horizon: float
    fit_next: float
    fit_horizon: float
    ros: float
    ros_ppg: float
    yellows: int
    yc_to_ban: int
    susp_risk: bool
    p_start: float
    provider_rank: int
    unavailable: bool
    vbd: float
    cs_prob: float
    xgi90: float
    ict90: float
    inf90: float
    cre90: float
    thr90: float
    xgc90: float
    starts: int
    status: str
    news: str
    owner: str
    owner_name: str
    available: bool
    set_piece: str
    next_opp: str
    next_fdr: int
    form: float
    minutes: float
    ppg: float
    total_points: float
    gws: list[GwCell]
    # derived
    opp_tag: str = ""  # "value" | "output-led" | ""


class BoardResponse(Schema):
    """Every player on the board — the players page filters/sorts this."""

    gws: list[int]
    my_ids: list[str]
    players: list[FplPlayer]


# ---- overview -----------------------------------------------------------------------


class LivePlayerRow(Schema):
    player: FplPlayer
    points: int
    minutes: int
    starter: bool
    dnp: bool
    proj: float
    role: Literal["start", "bench", "auto-in", "auto-out"]


class LiveSubstitution(Schema):
    out: str
    in_: str = Field(alias="in")


class FplLiveView(Schema):
    gw: int
    state: Literal["live", "finished"]
    secured: float
    played: int
    starters: int
    projected_finish: float
    not_played: list[str]
    auto_subs: list[LiveSubstitution]
    rows: list[LivePlayerRow]
    my_points: float | None
    opp_points: float | None
    opp_name: str | None


class Swap(Schema):
    out: FplPlayer
    in_: FplPlayer = Field(alias="in")
    gain: float


class FplSquadRow(Schema):
    player: FplPlayer
    starting: bool


class FixtureRunRow(Schema):
    player: FplPlayer
    cells: list[GwCell]
    mean: float


class FixtureRun(Schema):
    gws: list[int]
    col_mean: list[float]
    overall: float
    rows: list[FixtureRunRow]


class FplOverview(Schema):
    teams: int
    gws: list[int]
    next_gw: int
    has_squad: bool
    from_app: bool
    lineup_source: str | None  # "my-team" | "event/N" | None
    formation: str
    next_gw_proj: float
    ros_per_gw: float
    my_rank: int | None
    league_size: int
    live: FplLiveView | None
    swaps: list[Swap]
    checklist: list[CheckItem]
    squad: list[FplSquadRow]
    fixture_run: FixtureRun | None


# ---- clubs ---------------------------------------------------------------------------


class ClubCell(Schema):
    gw: int
    opp: str
    home: bool | None
    fdr: int
    fdr_att: int
    fdr_def: int


class ClubFix(Schema):
    team: str
    cells: list[ClubCell]
    avg_fdr: float


class ClubDossier(Schema):
    team: str
    fixtures: list[ClubCell]
    avg_fdr: float
    probable_xi: list[FplPlayer]
    bench: list[FplPlayer]
    set_pieces: dict[str, list[FplPlayer]]
    doubts: list[FplPlayer]
    key_players: list[FplPlayer]


class FplFixturesResponse(Schema):
    gws: list[int]
    clubs: list[ClubFix]


class FplTeamsResponse(Schema):
    clubs: list[ClubDossier]


# ---- optimizer -------------------------------------------------------------------------


class Upgrade(Schema):
    out: FplPlayer
    in_: FplPlayer = Field(alias="in")
    gain: float
    out_value: float  # the dropped player's value over the window


class FplOptimizerResponse(Schema):
    horizon: Horizon
    gws: list[int]
    squad: list[FplPlayer]  # by position, then 6-GW total
    best_xi_totals: list[float]  # best legal XI total per GW
    best_xi_horizon: float
    targets: dict[str, list[FplPlayer]]  # top free agents by 6-GW total: ALL / GKP / DEF / MID / FWD
    upgrades: list[Upgrade]
    stash: list[FplPlayer]


# ---- rivals ----------------------------------------------------------------------------


class Manager(Schema):
    entry_id: str
    name: str
    is_mine: bool
    players: list[FplPlayer]
    by_pos: dict[str, list[FplPlayer]]
    total_medium: float
    total_season: float


class RivalProjection(Schema):
    entry_id: str
    name: str
    proj: float
    diffs: list[FplPlayer]  # they have, you don't


class ClaimPrediction(Schema):
    rival_name: str
    weak_pos: str
    weak_starter: str
    target: FplPlayer
    gain: int


class FplEffectiveOwnership(Schema):
    player: FplPlayer
    owners: int
    pct: int
    mine: bool


class FplRivalsResponse(Schema):
    my_proj: float
    rivals: list[RivalProjection]
    claims: list[ClaimPrediction]
    effective_ownership: list[FplEffectiveOwnership]
    managers: list[Manager]
    league_size: int


# ---- standings ------------------------------------------------------------------------


class FplStandingRow(Schema):
    entry_id: str
    name: str
    rank: int
    total: float
    wins: int | None
    draws: int | None
    losses: int | None
    ros: float
    final_pts: float
    proj_rank: int
    gap: float
    mine: bool
    first_pct: float | None = None
    top_half_pct: float | None = None
    mean_rank: float | None = None


class Path(Schema):
    proj_rank: int
    to_next: int
    next_name: str | None
    to_leader: int
    leader_name: str
    move_name: str | None
    move_gain: int | None


class H2hFixture(Schema):
    gw: int
    home: str
    away: str
    home_proj: float
    away_proj: float
    mine: bool
    lean: str


class FplStandingsResponse(Schema):
    is_h2h: bool
    gws_left: int
    simulated: bool
    rows: list[FplStandingRow]
    path: Path | None
    schedule: list[H2hFixture]


# ---- trades -----------------------------------------------------------------------------


class FplTradeIdea(Schema):
    rival_name: str
    give: list[FplPlayer]
    get: list[FplPlayer]
    my_gain: float
    their_gain: float


class FplTradeLab(Schema):
    horizon: Horizon
    me: Manager | None
    rivals: list[Manager]
    suggestions: list[FplTradeIdea]


class FplTradeRequest(Schema):
    give: list[str]
    get: list[str]


class FplTradeEvaluation(Schema):
    balanced: bool
    pos_give: str
    pos_get: str
    me_short: float
    me_medium: float
    me_season: float
    them_short: float
    them_medium: float
    them_season: float
    warnings: list[str]
    verdict: str
