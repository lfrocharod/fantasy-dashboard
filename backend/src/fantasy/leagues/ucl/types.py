"""Plain domain types shared across ingestion and the model.

No third-party imports here on purpose — `model/` imports this and nothing else
from the package, so the projection maths stays unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Position = Literal["GK", "DEF", "MID", "FWD"]
POSITIONS: tuple[Position, ...] = ("GK", "DEF", "MID", "FWD")


@dataclass(slots=True)
class Team:
    uefa_team_id: int
    name: str
    code: str = ""
    # Multiplicative ratings centred on 1.0 (1.2 = 20% stronger than average).
    attack_rating: float = 1.0
    defence_rating: float = 1.0


@dataclass(slots=True)
class Player:
    uefa_player_id: int
    name: str
    team_id: int
    position: Position
    price: float = 0.0
    uefa_total_points: int = 0
    uefa_form: float = 0.0
    selected_pct: float = 0.0
    price_momentum: float = 0.0
    status_code: int = 0  # 0 fit, 1 doubt, 2 out
    status_detail: str = ""
    # UEFA-competition minutes as a share (0..1) of a near-ever-present at the
    # same club — a start-probability prior that covers every player, no scrape.
    minutes_prior: float = 0.0
    # set-piece duty best-guess: "", "PK", "PK,CK", "FK", "CK" …
    set_piece: str = ""
    fbref_id: str | None = None
    understat_id: str | None = None
    # --- live matchday state -------------------------------------------------
    # Only meaningful once the player's fixture is live or finished; harmless
    # zeros the rest of the time. `live_points` is UEFA's `curGDPts` (points
    # banked so far this matchday); `live_played` is whether they've featured.
    live_points: int | None = None
    live_played: bool = False


@dataclass(slots=True)
class PlayerStat:
    """Rolling per-90 underlying numbers from FBref / Understat."""

    player_id: int
    scope: str = "combined"
    minutes: float = 0.0
    matches: int = 0
    npxg90: float = 0.0
    xag90: float = 0.0
    shots90: float = 0.0
    sca90: float = 0.0
    save_pct: float = 0.0
    source: str = ""


@dataclass(slots=True)
class Fixture:
    uefa_match_id: int
    matchday: int
    home_team_id: int
    away_team_id: int
    kickoff: datetime | None = None
    status: str = "upcoming"
    home_goals: int | None = None
    away_goals: int | None = None
    home_xg_est: float = 0.0
    away_xg_est: float = 0.0
    # live only: minute the match is at (0 for not-started / full-time). In-memory
    # during a live ingest pass; not persisted.
    live_minute: int = 0


@dataclass(slots=True)
class SquadPick:
    player_id: int
    is_starter: bool = True
    is_captain: bool = False
    is_vice: bool = False
    bench_order: int = 0
    purchase_price: float = 0.0
    # live: has this pick featured in the matchday yet (UEFA `isplayed`)
    is_played: bool = False
    # UEFA's own matchday points for the pick, the captain's already doubled
    # (`overallpoints`); only final once the team's matchday score is
    points: float | None = None
    # in-play changes UEFA records (`autosubflag`): subbed into the XI (1) or
    # out of it (2) between match days, 0 untouched
    sub_flag: int = 0
    # the armband moved this matchday (`capchgflag`): off this pick (1), onto it (2)
    cap_flag: int = 0


@dataclass(slots=True)
class TeamSheet:
    """UEFA's own account of a fantasy team's matchday, from the squad payload."""

    points: float | None = None  # `gdPoints`: the official score, once UEFA has scored it
    in_play_subs: int = 0  # `mdSubstitutions`: subs made between match days (max 4)
    captain_moved: bool = False  # the armband moved mid-matchday

    @property
    def changed(self) -> bool:
        """A manual change this matchday: UEFA then makes no automatic subs."""
        return self.in_play_subs > 0 or self.captain_moved


@dataclass(slots=True)
class LeagueEntry:
    entry_id: str
    manager_name: str
    team_name: str
    matchday: int
    points: int
    total_points: int
    rank: int
    prev_rank: int = 0
    # [{"id": int, "c": bool captain, "s": bool starter, "b": int bench_order}, …]
    # (older rows may still be a bare list[int]; the reader handles both)
    squad: list = field(default_factory=list)


@dataclass(slots=True)
class PlayerForm:
    player_id: int
    source: str = "understat"
    source_team: str = ""
    team_ok: bool = True
    role: str = ""
    role_note: str = ""
    recent_matches: int = 0
    recent_starts: int = 0
    recent_minutes: float = 0.0
    recent_goals: float = 0.0
    recent_assists: float = 0.0
    recent_npxg: float = 0.0
    recent_xa: float = 0.0
    recent_shots: float = 0.0
    season_minutes: float = 0.0
    season_npxg90: float = 0.0
    season_xa90: float = 0.0
    start_prob: float = 0.0
    hot_score: float = 0.0
    avg_rating: float = 0.0
    matches_14d: int = 0
    comps: str = ""


@dataclass(slots=True)
class Projection:
    player_id: int
    matchday: int
    p_start: float
    exp_minutes: float
    xpts: float
    xpts_captain: float
    value: float
    xpts_high: float
    xpts_low: float
    components: dict[str, float]
