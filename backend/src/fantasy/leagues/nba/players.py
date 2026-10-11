"""An NBA player as the views work with it: a `draft_players` row (sport
"nba") with the extras unpacked from its `raw` JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GAMES_IN_SEASON = 82
# Chance a player suits up for a given game, by ESPN injury designation.
PLAY_PROB = {"ACTIVE": 1.0, "DAY_TO_DAY": 0.75, "QUESTIONABLE": 0.75, "PROBABLE": 0.9,
             "DOUBTFUL": 0.25, "OUT": 0.0, "SUSPENSION": 0.0, "INJURY_RESERVE": 0.0}
OUT_STATUS = frozenset({"OUT", "SUSPENSION", "INJURY_RESERVE"})


def _num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class NbaPlayer:
    ext_id: str
    name: str
    team: str  # NBA team abbreviation
    pro_team_id: int
    pos: str  # default position: PG SG SF PF C
    positions: list[str]  # eligible positions
    slots: list[str]  # eligible starting slots (PG … UT)
    fppg: float  # the per-game estimate everything plans with
    fppg_proj: float  # ESPN's preseason projection
    proj_games: int  # games ESPN projects them to play
    fppg_now: float  # this season's average
    gp_now: int
    fppg_last: float  # last season's average
    gp_last: int
    fppg_l15: float  # last 15 days
    gp_l15: int
    line: dict[str, float]  # per-game box score (pts, reb, ast, stl, blk, tpm, to, min, …)
    line_source: str  # "season" | "projection" | "last season" | ""
    injury: str  # ACTIVE | DAY_TO_DAY | OUT | SUSPENSION …
    pct_owned: float
    pct_started: float
    pct_change: float
    status: str  # FREEAGENT | WAIVERS | ONTEAM
    owner_team_id: int | None
    owner_name: str
    slot: str  # current lineup slot for a rostered player (PG … UT, BE, IR)
    droppable: bool
    adp: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.owner_team_id is None

    @property
    def play_prob(self) -> float:
        return PLAY_PROB.get(self.injury, 1.0)

    @property
    def durability(self) -> float:
        """Share of the remaining games they're expected to play: ESPN's
        projected games over a full season, clipped to a sane band."""
        if self.proj_games <= 0:
            return 0.85
        return max(0.55, min(1.0, self.proj_games / GAMES_IN_SEASON))

    @classmethod
    def from_row(cls, row: Any) -> NbaPlayer:
        raw: dict[str, Any] = row.raw or {}
        owner = raw.get("ownerTeamId")
        return cls(
            ext_id=str(row.ext_id),
            name=str(row.name),
            team=str(row.team or ""),
            pro_team_id=int(_num(raw.get("proTeamId"))),
            pos=str(row.primary_pos or ""),
            positions=[x for x in str(row.positions or "").split(",") if x],
            slots=[str(x) for x in raw.get("slots") or []],
            fppg=_num(raw.get("fppg"), _num(row.proj_points)),
            fppg_proj=_num(raw.get("fppgProj")),
            proj_games=int(_num(raw.get("projGames"))),
            fppg_now=_num(raw.get("fppgNow")),
            gp_now=int(_num(raw.get("gpNow"))),
            fppg_last=_num(raw.get("fppgLast")),
            gp_last=int(_num(raw.get("gpLast"))),
            fppg_l15=_num(raw.get("fppgL15")),
            gp_l15=int(_num(raw.get("gpL15"))),
            line={str(k): _num(v) for k, v in (raw.get("line") or {}).items()},
            line_source=str(raw.get("lineSource") or ""),
            injury=str(raw.get("injury") or row.injury_status or "ACTIVE"),
            pct_owned=_num(raw.get("pctOwned")),
            pct_started=_num(raw.get("pctStarted")),
            pct_change=_num(raw.get("pctChange")),
            status=str(raw.get("status") or ""),
            owner_team_id=int(owner) if owner is not None else None,
            owner_name=str(raw.get("ownerName") or ""),
            slot=str(raw.get("slot") or ""),
            droppable=raw.get("droppable") is not False,
            adp=_num(row.adp),
        )
