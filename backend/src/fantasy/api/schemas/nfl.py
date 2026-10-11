"""ESPN NFL (in-season) response models."""

from __future__ import annotations

from typing import Literal

from fantasy.api.schemas.common import CheckItem, Schema

LineupMode = Literal["floor", "mean", "ceiling"]
SeedingRule = Literal["H2H_RECORD", "TOTAL_POINTS_SCORED"]


class WeekOpp(Schema):
    week: int
    opp: str
    home: bool | None
    fdr: int


class NflPlayer(Schema):
    ext_id: str
    name: str
    pos: str
    team: str
    week_proj: float
    ros_proj: float
    vor: float
    ecr_rank: int | None
    ecr_tier: int | None
    bye: int
    on_bye: bool
    injury: str
    pct_owned: float
    pct_started: float
    slot: str
    owner_team_id: int | None
    owner_name: str
    available: bool
    next_opp: str
    next_fdr: int
    snap_pct: float
    snap_trend: float
    target_share: float
    wopr: float
    touches: float
    usage_games: int
    usage_stale: bool
    xfp_g: float
    xtd_g: float
    fp_oe: float
    exp_games: int
    matchups: list[WeekOpp]
    # derived (this week)
    week_points: float = 0.0
    lo: float = 0.0
    hi: float = 0.0
    usage_tag: str = ""
    opp_tag: str = ""


class LiveScore(Schema):
    mine: float
    opp: float
    final: bool


class RosterRow(Schema):
    player: NflPlayer
    starting: bool


class NflOverview(Schema):
    week: int
    has_roster: bool
    my_proj: float
    opp_name: str | None
    opp_proj: float | None
    win_pct: int | None
    mode: LineupMode
    live: LiveScore | None
    checklist: list[CheckItem]
    roster: list[RosterRow]


class SlotRow(Schema):
    slot: str
    player: NflPlayer | None


class StartSitRow(Schema):
    player: NflPlayer
    call: Literal["START", "SIT", "FLEX?"]


class NflOptimizer(Schema):
    week: int
    has_roster: bool
    mode: LineupMode
    win_pct: int
    seed_by_points: bool
    mean_total: float
    lo_total: float
    hi_total: float
    lineup: list[SlotRow]
    to_start: list[NflPlayer]
    to_bench: list[NflPlayer]
    start_sit: list[StartSitRow]


class Hole(Schema):
    gap: NflPlayer
    reason: str
    fill: NflPlayer | None


class StreamWeek(Schema):
    opp: str
    fdr: int
    proj: float


class StreamOption(Schema):
    player: NflPlayer
    weeks: list[StreamWeek]
    best: int
    total3: float


class StreamGroup(Schema):
    position: str
    options: list[StreamOption]


class FreeAgentRow(Schema):
    player: NflPlayer
    value: float
    upgrade: float  # vs your worst starter at the position


class NflPlayersResponse(Schema):
    week: int
    horizon: Literal["week", "ros"]
    position: str
    holes: list[Hole]
    stream: list[StreamGroup]
    free_agents: list[FreeAgentRow]


class NflManager(Schema):
    team_id: int
    name: str
    is_mine: bool
    players: list[NflPlayer]
    by_pos: dict[str, list[NflPlayer]]
    ros_total: int


class OpponentView(Schema):
    name: str
    my_proj: float
    their_proj: float
    advice: str
    lineup: list[SlotRow]


class NflRivalsResponse(Schema):
    week: int
    opponent: OpponentView | None
    teams: list[NflManager]


class NflClubFix(Schema):
    team: str
    cells: list[WeekOpp]
    avg_fdr: float


class NflClubDossier(Schema):
    team: str
    fixtures: list[WeekOpp]
    avg_fdr: float
    starters: list[NflPlayer]
    bench: list[NflPlayer]
    doubts: list[NflPlayer]
    bye: int


class NflFixturesResponse(Schema):
    weeks: list[int]
    clubs: list[NflClubFix]


class NflTeamsResponse(Schema):
    clubs: list[NflClubDossier]


class NflStandingRow(Schema):
    team_id: int
    name: str
    wins: int
    losses: int
    ties: int
    pf: float
    mine: bool
    in_line: bool
    proj_wins: float | None
    proj_pf: float | None
    playoff_pct: float | None
    bye_pct: float | None


class Pace(Schema):
    cur_rank: int
    cur_gap: float
    played: int
    weeks_left: int
    my_pace: float
    proj_margin: float
    per_week_gap: float
    playoff_pct: float | None


class ByeGap(Schema):
    week: int
    players: list[NflPlayer]


class PlayoffRun(Schema):
    player: NflPlayer
    avg: float
    weeks: list[WeekOpp]


class NflStandingsResponse(Schema):
    rule: SeedingRule
    espn_rule: SeedingRule
    by_points: bool
    playoff_teams: int
    reg_weeks: int
    playoff_weeks: list[int]
    rows: list[NflStandingRow]
    pace: Pace | None
    byes: list[ByeGap]
    playoff_runs: list[PlayoffRun]


class NflTradeIdea(Schema):
    rival_name: str
    rival_team_id: int
    give: NflPlayer
    get: NflPlayer
    my_gain: int
    their_gain: int


class SurplusRow(Schema):
    player: NflPlayer
    fills_need: bool
    tag: str


class NflTradeLab(Schema):
    me: NflManager | None
    rivals: list[NflManager]
    rival: NflManager | None
    ideas: list[NflTradeIdea]
    their_surplus: list[SurplusRow]


class NflTradeRequest(Schema):
    give: list[str]
    get: list[str]


class NflTradeEvaluation(Schema):
    me_week: float
    me_ros: int
    them_ros: int
    warnings: list[str]
    verdict: str
    need_pos: list[str]
