"""Champions League Fantasy response models.

The optimizer and live-matchday payloads are documents the pipeline writes
(`documents` table); their models are deliberately lenient (defaults
everywhere) so a document written by an older pipeline still validates.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from fantasy.api.schemas.common import CheckItem, Schema

Position = Literal["GK", "DEF", "MID", "FWD"]
Confirmed = Literal["start", "bench"]


# ---- players ----------------------------------------------------------------------


class PlayerRow(Schema):
    player_id: int
    name: str
    position: str
    team_id: int
    team_name: str
    price: float
    selected_pct: float
    status_code: int
    status_detail: str
    uefa_form: float
    price_momentum: float
    set_piece: str
    xpts: float | None = None
    xpts_captain: float | None = None
    xpts_high: float | None = None
    xpts_low: float | None = None
    value: float | None = None
    p_start: float | None = None
    exp_minutes: float | None = None
    components: dict[str, Any] | None = None
    # recent-form layer (null when no source matched)
    role: str | None = None
    role_note: str | None = None
    team_ok: bool | None = None
    start_prob: float | None = None
    hot_score: float | None = None
    avg_rating: float | None = None
    matches14d: int | None = None
    comps: str | None = None
    recent_goals: float | None = None
    recent_assists: float | None = None
    recent_starts: int | None = None
    recent_matches: int | None = None
    recent_minutes: float | None = None
    # season underlying rates — null below the sample bar the model trusts
    npxg90: float | None = None
    xa90: float | None = None
    xgi90: float | None = None
    shots90: float | None = None
    xg_matches: int | None = None
    xg_minutes: float | None = None
    # derived for display
    confirmed: Confirmed | None = None  # official lineup, once published
    start_pct: float | None = None  # 0..1 — confirmed > composed > raw form
    start_disagreement: float = 0.0  # start-probability sources disagree (>= 0.4: flag)
    leverage_role: str | None = None  # playing further forward than listed
    recent_goal_involvements: float | None = None


class UclSquadRow(PlayerRow):
    is_starter: bool
    is_captain: bool
    is_vice: bool
    bench_order: int
    purchase_price: float


class UclPlayersResponse(Schema):
    matchday: int
    owned_ids: list[int]
    players: list[PlayerRow]


# ---- fixtures ---------------------------------------------------------------------


class FixtureDifficulty(Schema):
    att: int
    def_: int = Field(alias="def")
    pos: int


class Opponent(Schema):
    name: str
    home: bool
    fdr: FixtureDifficulty  # position-aware, for this player's position


class SquadTableRow(UclSquadRow):
    opponent: Opponent | None = None
    recommended_captain: bool = False


class FixtureRow(Schema):
    match_id: int
    matchday: int
    kickoff: str | None
    status: str
    home_team: str
    away_team: str
    home_xg: float
    away_xg: float
    home_goals: int | None
    away_goals: int | None


class TickerCell(Schema):
    matchday: int
    opp: str
    opp_code: str
    home: bool
    difficulty: int  # blended
    att_difficulty: int  # for attackers
    def_difficulty: int  # for keepers/defenders
    kickoff: str | None


class TickerRow(Schema):
    team_id: int
    team: str
    code: str
    cells: list[TickerCell]
    avg_difficulty: float


class UclFixturesResponse(Schema):
    matchdays: list[int]
    rows: list[TickerRow]


class TeamDossier(Schema):
    team_id: int
    team: str
    code: str
    attack_rating: float
    defence_rating: float
    tier: str
    fixtures: list[TickerCell]
    avg_difficulty: float
    probable_xi: list[PlayerRow]
    bench: list[PlayerRow]
    set_pieces: dict[str, list[PlayerRow]]
    doubts: list[PlayerRow]
    moved_on: list[PlayerRow]
    top_picks: list[PlayerRow]


class UclTeamsResponse(Schema):
    matchday: int
    teams: list[TeamDossier]


# ---- league position strategy + captaincy ------------------------------------------------


class LeagueStrategy(Schema):
    mode: Literal["protect", "hold", "chase", "free"]
    text: str
    mds_left: int
    captain: Literal["safe", "match", "differential", "best"]


class CaptainCandidate(Schema):
    player_id: int
    name: str
    team: str = ""
    position: str = ""
    ev: float = 0.0  # 2 × xPts
    ceiling: float = 0.0
    floor: float = 0.0
    owned: float = 0.0


class CaptainAnalysis(Schema):
    candidates: list[CaptainCandidate] = []
    safe_pick: CaptainCandidate | None = None
    differential_pick: CaptainCandidate | None = None


class CaptaincyVerdict(Schema):
    """KEEP / CHANGE / SET the armband, given the league position."""

    recommendation: Literal["keep", "change", "set"]
    pick: CaptainCandidate
    current: CaptainCandidate | None
    why: str
    differential: CaptainCandidate | None
    rows: list[CaptainCandidate]


# ---- live matchday (document written by the pipeline) ------------------------------------


class LiveSquadRow(Schema):
    player_id: int
    name: str
    position: str
    team: str = ""
    opp: str | None = None
    home: bool | None = None
    md_day: int | None = None
    kickoff: str | None = None
    match_state: str = "none"  # upcoming | live | finished | none
    minute: int | None = None
    played: bool = False
    actual: float | None = None
    xpts: float = 0.0
    is_starter: bool = False
    is_captain: bool = False
    is_vice: bool = False
    bench_order: int = 0
    dnp: bool = False
    eff_role: str = "start"  # start | bench | auto-in | auto-out
    # the club's published team sheet, once it's out: in the XI or on the bench
    confirmed: Literal["start", "bench"] | None = None


class LiveSub(Schema):
    out_name: str
    out_pos: str = ""
    in_name: str
    in_pos: str = ""
    reason: str | None = None
    out_actual: float | None = None
    out_xpts: float | None = None
    in_xpts: float | None = None
    gain: float | None = None


class LiveFixture(Schema):
    match_id: int
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    status: str = ""
    kickoff: str | None = None


class CaptainSwitch(Schema):
    to_player_id: int
    to_name: str
    to_xpts: float
    from_name: str
    from_xpts: float
    gain: float


class LiveCaptain(Schema):
    player_id: int
    name: str
    actual: float | None = None
    xpts: float = 0.0
    match_state: str = ""
    locked: bool = False
    effective_player_id: int | None = None
    effective_name: str | None = None
    vice_name: str | None = None
    recommendation: Literal["keep", "switch", "locked"] | None = None
    switch: CaptainSwitch | None = None
    note: str | None = None


class LiveState(Schema):
    matchday: int
    generated_at: str = ""
    state: Literal["live", "finished"] = "live"
    starters: int = 0
    played: int = 0
    to_play: int = 0
    secured_points: float = 0.0
    projected_finish: float = 0.0
    pre_match_projection: float = 0.0
    bench_slots: int = 0
    in_play_open: bool = True  # false on a single-slot matchday: no subs, no armband move
    max_manual_subs: int = 0
    fixtures: list[LiveFixture] = []
    squad: list[LiveSquadRow] = []
    auto_subs: list[LiveSub] = []
    manual_subs: list[LiveSub] = []
    captain: LiveCaptain | None = None


class LiveRivalRow(Schema):
    entry_id: str
    manager_name: str = ""
    team_name: str = ""
    rank: int = 0
    total_points: float = 0.0
    mine: bool = False
    secured: float = 0.0
    projected: float = 0.0
    played: int = 0
    live_gap_vs_me: float | None = None


class LiveRivals(Schema):
    ready: bool = True
    matchday: int
    state: Literal["live", "finished"] = "live"
    my_entry_id: str | None = None
    rows: list[LiveRivalRow] = []


class LiveSnapshotPoint(Schema):
    captured_at: str
    secured: float
    projected: float
    pre_match: float
    state: str


# ---- overview ----------------------------------------------------------------------------


class OverviewCards(Schema):
    proj_total: float
    captain_pick_name: str | None
    captain_pick_xpts: float | None
    squad_value: float
    rank: int | None
    league_size: int


class UclOverview(Schema):
    matchday: int
    deadline_iso: str | None
    has_squad: bool
    cards: OverviewCards | None
    live: LiveState | None
    live_history: list[LiveSnapshotPoint]
    live_rivals: LiveRivals | None
    strategy: LeagueStrategy | None
    captaincy: CaptaincyVerdict | None
    checklist: list[CheckItem]
    squad: list[SquadTableRow]
    fixtures_matchday: int
    fixtures: list[FixtureRow]


# ---- optimizer (document written by the pipeline) -------------------------------------------


class FixtureContext(Schema):
    opp: str | None = None
    home: bool | None = None
    fdr: int | None = None
    md_day: int | None = None


class OptPlayer(FixtureContext):
    player_id: int
    name: str
    team: str = ""
    position: str = ""
    xpts: float = 0.0
    is_captain: bool | None = None
    is_vice: bool | None = None
    order: int | None = None
    price: float | None = None


class Transfer(Schema):
    out: OptPlayer
    in_: OptPlayer = Field(alias="in")  # `in` is a Python keyword
    horizon_gain: float = 0.0
    hit_cost: float = 0.0
    net_gain: float = 0.0


class SquadPick(FixtureContext):
    player_id: int
    name: str
    team: str = ""
    position: str = ""
    price: float = 0.0
    horizon_xpts: float = 0.0
    is_starter: bool = False
    is_captain: bool | None = None
    is_vice: bool | None = None


class IdealSquad(Schema):
    matchday: int | None = None
    horizon: int | None = None
    formation: str = ""
    total_cost: float = 0.0
    budget: float = 100.0
    xi_xpts: float = 0.0
    horizon_xpts: float = 0.0
    squad: list[SquadPick] = []
    changes_from_current: int | None = None
    keep_from_current: int | None = None


class ChipMatchday(Schema):
    matchday: int
    current_xi_xpts: float = 0.0
    free_transfer_xi_xpts: float | None = None
    limitless: float = 0.0
    wildcard: float = 0.0


class ChipRecommendation(Schema):
    matchday: int
    gain: float
    why: str | None = None


class ChipEval(Schema):
    per_matchday: list[ChipMatchday] = []
    recommend: dict[str, ChipRecommendation | None] = {}
    note: str = ""


class PlanRow(FixtureContext):
    player_id: int
    name: str
    team: str = ""
    position: str = ""
    price: float = 0.0
    xpts: float = 0.0
    owned: bool = False


class MatchdayPlan(Schema):
    matchday: int
    xi_xpts: float = 0.0
    start_for_md: list[PlanRow] = []
    bench_for_md: list[PlanRow] = []
    targets: list[PlanRow] = []


class TimingRow(FixtureContext):
    player_id: int
    name: str
    position: str = ""
    xpts: float = 0.0
    p_start: float | None = None


class MatchdayTiming(Schema):
    days: int = 1
    players: list[TimingRow] = []
    live_options: list[str] = []


class OptimizerOutput(Schema):
    generated_at: str = ""
    matchday: int = 0
    horizon: int = 1
    formation: str = ""
    baseline_xpts: float = 0.0
    optimised_xpts: float = 0.0
    best_xi: list[OptPlayer] = Field(default=[], alias="bestXI")
    bench: list[OptPlayer] = []
    transfers: list[Transfer] = []
    captains: CaptainAnalysis | None = None
    chips: ChipEval | None = None
    matchday_plan: list[MatchdayPlan] = []
    matchday_timing: MatchdayTiming | None = None
    pre_season: bool = False
    deadline_open: bool = False
    free_transfers: int | None = None
    ideal_squad: IdealSquad | None = None
    # pre-season shape: the ideal squad's fields at top level
    total_cost: float | None = None
    budget: float | None = None
    xi_xpts: float | None = None
    horizon_xpts: float | None = None
    squad: list[SquadPick] = []
    changes_from_current: int | None = None
    keep_from_current: int | None = None


class UclOptimizerResponse(Schema):
    available: bool
    output: OptimizerOutput | None = None


# ---- rivals + league -------------------------------------------------------------------------


class RivalPlayer(Schema):
    player_id: int
    name: str
    position: str
    team: str
    xpts: float
    mine: bool


class RivalRow(Schema):
    entry_id: str
    manager_name: str
    team_name: str
    rank: int
    total_points: int
    projected_points: float
    gap_vs_me: float  # rival projected − mine (positive: they out-project me)
    overlap: int  # shared players out of 15
    their_differentials: list[RivalPlayer]
    my_edges: list[RivalPlayer]


class OwnedPlayer(Schema):
    player_id: int
    name: str
    xpts: float
    owned_by_rivals: int


class UclEffectiveOwnership(Schema):
    player_id: int
    name: str
    team: str
    xpts: float
    owned_pct: int
    mine: bool


class CaptainCount(Schema):
    player_id: int
    name: str
    count: int
    mine: bool


class RivalReport(Schema):
    ready: bool
    my_projected_points: float
    my_rank: int | None
    rivals: list[RivalRow]
    template_risk: list[OwnedPlayer]
    common_threats: list[OwnedPlayer]
    effective_ownership: list[UclEffectiveOwnership]
    captain_picks: list[CaptainCount]
    strategy: LeagueStrategy | None
    rival_count: int
    squads_as_of: str | None
    squads_matchday: int | None
    stale: bool


class UclRivalsResponse(Schema):
    matchday: int
    report: RivalReport
    live: LiveRivals | None


class UclStandingRow(Schema):
    entry_id: str
    manager_name: str
    team_name: str
    rank: int
    prev_rank: int
    points: int
    total_points: int
    mine: bool


class EntryAggregate(Schema):
    entry_id: str
    name: str
    team: str
    matchdays: int
    total: int
    avg: float
    best: int
    worst: int
    stdev: float
    form3: int
    last_rank: int
    mine: bool


class FinishOdds(Schema):
    entry_id: str
    name: str
    now: int
    proj_points: int
    mean_rank: float
    first_pct: float
    top_half_pct: float
    mine: bool


class CalStat(Schema):
    n: int = 0
    mae: float | None = None
    me: float | None = None
    rmse: float | None = None
    r: float | None = None
    mean_pred: float | None = None
    mean_act: float | None = None
    band: float | None = None


class Calibration(Schema):
    generated_at: str = ""
    matchdays: list[int] = []
    player_matchdays: int = 0
    overall: CalStat = CalStat()
    by_position: dict[str, CalStat] = {}
    by_matchday: dict[str, CalStat] = {}
    verdict: str = ""


class LeagueResponse(Schema):
    matchday: int
    league_id: str | None
    standings: list[UclStandingRow]
    leader_points: int
    power_ranking: list[EntryAggregate]
    mds_left: int
    finish: list[FinishOdds]
    calibration: Calibration | None


# ---- settings ----------------------------------------------------------------------------


class XgMiss(Schema):
    id: int
    name: str
    team: str
    price: float
    reason: str


class XgCoverage(Schema):
    generated_at: str = ""
    source: str = ""
    total: int = 0
    matched: int = 0
    unmatched: int = 0
    by_reason: dict[str, int] = {}
    notable_missing: list[XgMiss] = []
    top_missing: list[XgMiss] = []
