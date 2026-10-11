"""ESPN NFL player as the views work with it: a `draft_players` row (in-season
board) with the extras unpacked from its `raw` JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OUT_STATUS = frozenset({"OUT", "IR", "SUSPENSION", "DOUBTFUL"})
FLEX_POS = frozenset({"RB", "WR", "TE"})


def _num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class WeekOpp:
    week: int
    opp: str  # "BYE", "" (unknown) or the opponent's abbreviation
    home: bool | None
    fdr: int  # 1 easy … 5 hard, 0 = bye/unknown


@dataclass(slots=True)
class NflPlayer:
    ext_id: str
    name: str
    pos: str  # QB RB WR TE K DST
    team: str
    week_proj: float
    ros_proj: float
    vor: float
    ecr_rank: int | None
    ecr_tier: int | None
    bye: int
    on_bye: bool
    injury: str  # ACTIVE / QUESTIONABLE / DOUBTFUL / OUT / IR / SUSPENSION
    pct_owned: float
    pct_started: float
    slot: str  # current lineup slot (QB/RB/WR/TE/FLEX/DST/K/BE/IR)
    owner_team_id: int | None
    owner_name: str
    available: bool
    next_opp: str
    next_fdr: int
    snap_pct: float  # 0..1 offensive snap share (nflverse, last ~4 games)
    snap_trend: float  # last game vs prior mean
    target_share: float
    wopr: float  # weighted opportunity rating
    touches: float  # carries + receptions per game
    usage_games: int
    usage_stale: bool  # last season's numbers, shown as a prior
    xfp_g: float  # expected fantasy points per game (ffopportunity)
    xtd_g: float  # expected touchdowns per game
    fp_oe: float  # fantasy points over/under expected per game
    exp_games: int
    matchups: list[WeekOpp] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: Any) -> NflPlayer:
        raw: dict[str, Any] = row.raw or {}
        owner = raw.get("ownerTeamId")
        return cls(
            ext_id=str(row.ext_id),
            name=str(row.name),
            pos=str(row.primary_pos or ""),
            team=str(row.team or ""),
            week_proj=_num(raw.get("weekProj"), _num(row.proj_points)),
            ros_proj=_num(raw.get("rosProj")),
            vor=_num(row.vbd),
            ecr_rank=row.ecr_rank,
            ecr_tier=row.ecr_tier,
            bye=int(_num(raw.get("bye"))),
            on_bye=raw.get("onBye") is True,
            injury=str(raw.get("injury") if raw.get("injury") is not None else "ACTIVE"),
            pct_owned=_num(raw.get("pctOwned")),
            pct_started=_num(raw.get("pctStarted")),
            slot=str(raw.get("slot") or ""),
            owner_team_id=int(owner) if owner is not None else None,
            owner_name=str(raw.get("ownerName") or ""),
            available=raw.get("available") is not False and not raw.get("ownerName"),
            next_opp=str(raw.get("next_opp") or ""),
            next_fdr=int(_num(raw.get("next_fdr"))),
            snap_pct=_num(raw.get("snapPct")),
            snap_trend=_num(raw.get("snapTrend")),
            target_share=_num(raw.get("targetShare")),
            wopr=_num(raw.get("wopr")),
            touches=_num(raw.get("touches")),
            usage_games=int(_num(raw.get("usageGames"))),
            usage_stale=raw.get("usageStale") is True,
            xfp_g=_num(raw.get("xfpG")),
            xtd_g=_num(raw.get("xtdG")),
            fp_oe=_num(raw.get("fpOE")),
            exp_games=int(_num(raw.get("expGames"))),
            matchups=[
                WeekOpp(
                    week=int(_num(m.get("week"))),
                    opp=str(m.get("opp") or ""),
                    home=m.get("home") if isinstance(m.get("home"), bool) else None,
                    fdr=int(_num(m.get("fdr"))),
                )
                for m in (raw.get("matchups") or [])
                if isinstance(m, dict)
            ],
        )
