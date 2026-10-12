"""ESPN fantasy basketball (head-to-head points) response models."""

from __future__ import annotations

from typing import Literal

from fantasy.api.schemas.common import CheckItem, Schema

NbaSort = Literal["fppg", "week", "ros", "trend"]
NbaShow = Literal["free", "all"]
TodayCall = Literal["start", "bench", "no game", "IR", "out"]


class NbaLine(Schema):
    """Per-game box score: this season's once he's played five games, else
    ESPN's projection (or last season)."""

    pts: float = 0.0
    reb: float = 0.0
    ast: float = 0.0
    stl: float = 0.0
    blk: float = 0.0
    tpm: float = 0.0
    to: float = 0.0
    min: float = 0.0
    fg_pct: float = 0.0
    ft_pct: float = 0.0


class NbaPlayer(Schema):
    ext_id: str
    name: str
    team: str
    pos: str
    positions: list[str]
    slots: list[str]
    fppg: float
    fppg_proj: float
    fppg_now: float
    gp_now: int
    fppg_last: float
    fppg_l15: float
    gp_l15: int
    line: NbaLine
    line_source: str
    injury: str
    pct_owned: float
    pct_started: float
    pct_change: float
    status: str
    owner_team_id: int | None
    owner_name: str
    slot: str
    adp: float
    # in context
    games_left: int = 0  # games over the rest of this matchup
    games_next: int = 0  # games in the next matchup
    week_points: float = 0.0  # expected points over the rest of this matchup, every game started
    ros: float = 0.0  # rest-of-season points: per game × games left × share expected played
    playoff_games: int = 0
    today: str = ""  # tonight's game: "vs LAL" / "@ BOS", "" if none


class NbaScore(Schema):
    my_points: float  # banked this matchup
    my_remaining: float
    my_proj: float
    opp_name: str | None
    opp_points: float
    opp_remaining: float
    opp_proj: float
    win_pct: int | None


class NbaRosterRow(Schema):
    player: NbaPlayer
    starts: int  # projected starts over the days left
    lost: int  # games he'd sit through on a full day
    today: TodayCall


class NbaStream(Schema):
    add: NbaPlayer
    drop: NbaPlayer
    gain: float
    games: int
    ros_delta: float


class NbaMoves(Schema):
    limit: int | None  # pickups allowed this matchup (None = unlimited)
    per_day: bool  # the league's limit is per NBA game day, so the cap varies
    game_days: int  # NBA game days in this matchup
    used: int
    left: int | None
    waiver_note: str


class NbaOverview(Schema):
    league_name: str
    period: int
    first_date: str | None
    last_date: str | None
    today_date: str | None
    days_left: int
    is_playoffs: bool
    season_over: bool
    has_roster: bool
    score: NbaScore | None
    checklist: list[CheckItem]
    roster: list[NbaRosterRow]
    streams: list[NbaStream]
    moves: NbaMoves
    warnings: list[str]


class NbaSeat(Schema):
    slot: str
    player: NbaPlayer | None
    opp: str


class NbaDay(Schema):
    day: int
    date: str
    weekday: str
    seats: list[NbaSeat]
    benched: list[NbaPlayer]
    idle: list[NbaPlayer]
    points: float
    open_slots: int


class NbaLineup(Schema):
    period: int
    has_roster: bool
    days: list[NbaDay]
    total: float
    games: int
    lost: int
    open_slots: int
    today_start: list[NbaPlayer]
    today_bench: list[NbaPlayer]


class NbaFreeAgent(Schema):
    player: NbaPlayer
    value: float


class NbaPlayersResponse(Schema):
    period: int
    sort: NbaSort
    position: str
    show: NbaShow
    rows: list[NbaFreeAgent]
    streams: list[NbaStream]


class NbaPeriod(Schema):
    period: int
    first_date: str
    last_date: str
    days: int
    playoffs: bool


class NbaTeamGames(Schema):
    team: str
    name: str
    games: list[int]  # per period, in `periods` order
    mine: int  # your players on this team


class NbaDayCount(Schema):
    day: int
    date: str
    weekday: str
    games: int  # NBA games that day
    my_games: int  # your players with a game
    light: bool  # few games around the league: the streaming days


class NbaScheduleResponse(Schema):
    periods: list[NbaPeriod]
    teams: list[NbaTeamGames]
    days: list[NbaDayCount]


class NbaStandingRow(Schema):
    team_id: int
    name: str
    wins: int
    losses: int
    ties: int
    pf: float
    pa: float
    mine: bool
    in_line: bool
    playoff_pct: float | None
    top_seed_pct: float | None
    proj_wins: float | None


class NbaUpcoming(Schema):
    period: int
    opp_name: str
    my_proj: float
    opp_proj: float
    win_pct: int | None


class NbaPlayoffGames(Schema):
    player: NbaPlayer
    by_period: list[int]
    total: int


class NbaStandingsResponse(Schema):
    rows: list[NbaStandingRow]
    playoff_teams: int
    reg_periods: int
    playoff_periods: list[int]
    upcoming: list[NbaUpcoming]
    playoff_games: list[NbaPlayoffGames]
    trade_deadline: str | None


class NbaTeam(Schema):
    team_id: int
    name: str
    is_mine: bool
    wins: int
    losses: int
    ties: int
    pf: float
    week_proj: float
    players: list[NbaPlayer]


class NbaRivalsResponse(Schema):
    period: int
    teams: list[NbaTeam]


class NbaTradeIdea(Schema):
    rival_id: int
    rival_name: str
    give: NbaPlayer
    get: NbaPlayer
    my_gain: float
    their_gain: float


class NbaTradeLab(Schema):
    me: NbaTeam | None
    rivals: list[NbaTeam]
    rival: NbaTeam | None
    ideas: list[NbaTradeIdea]
    weeks_left: float
    trade_deadline: str | None


class NbaTradeRequest(Schema):
    give: list[str]
    get: list[str]


class NbaTradeEvaluation(Schema):
    my_ros: float
    my_week: float
    their_ros: float
    my_playoff_games: int
    roster_moves: list[str]
    warnings: list[str]
    verdict: str
