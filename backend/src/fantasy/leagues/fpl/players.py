"""FPL Draft player as the views work with it: a `draft_players` row with the
sport-specific extras unpacked from its `raw` JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class GwCell:
    gw: int
    opp: str
    home: bool | None
    fdr: int  # position-aware difficulty, 1 (easy) … 5 (hard)
    xpts: float
    cs: float
    fdr_att: int | None = None  # getting goals/assists (opponent defence)
    fdr_def: int | None = None  # keeping a clean sheet (opponent attack)
    lo: float | None = None  # ~15th-percentile outcome
    hi: float | None = None  # ~85th-percentile outcome

    @classmethod
    def from_raw(cls, g: dict[str, Any]) -> GwCell:
        return cls(
            gw=int(_num(g.get("gw"))),
            opp=str(g.get("opp") or ""),
            home=g.get("home") if isinstance(g.get("home"), bool) else None,
            fdr=int(_num(g.get("fdr"))),
            xpts=_num(g.get("xpts")),
            cs=_num(g.get("cs")),
            fdr_att=int(g["fdrAtt"]) if g.get("fdrAtt") is not None else None,
            fdr_def=int(g["fdrDef"]) if g.get("fdrDef") is not None else None,
            lo=_num(g["lo"]) if g.get("lo") is not None else None,
            hi=_num(g["hi"]) if g.get("hi") is not None else None,
        )


@dataclass(slots=True)
class FplPlayer:
    ext_id: str
    name: str
    team: str
    pos: str  # GKP DEF MID FWD
    proj: float  # next GW
    horizon: float  # sum over the shown GWs
    fit_next: float  # next-GW projection ignoring the injury flag
    fit_horizon: float  # 6-GW projection ignoring the injury flag
    ros: float  # rest-of-season projected points
    ros_ppg: float
    yellows: int
    yc_to_ban: int  # bookings until the next suspension milestone
    susp_risk: bool  # one booking from a ban
    p_start: float
    provider_rank: int  # FPL's own pre-season draft rank (1 = best)
    unavailable: bool  # injured / suspended / <75% to play
    vbd: float
    cs_prob: float
    xgi90: float
    ict90: float
    inf90: float
    cre90: float
    thr90: float
    xgc90: float
    starts: int
    status: str  # a / d / i / s / u / n
    news: str
    owner: str
    owner_name: str
    available: bool  # free agent in the league
    set_piece: str
    next_opp: str
    next_fdr: int
    form: float
    minutes: float
    ppg: float
    total_points: float
    gws: list[GwCell] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)

    def gw_xpts(self, i: int) -> float:
        return self.gws[i].xpts if i < len(self.gws) else 0.0

    @classmethod
    def from_row(cls, row: Any) -> FplPlayer:
        """From a DraftPlayer ORM row (or anything with the same attributes)."""
        raw: dict[str, Any] = row.raw or {}
        return cls(
            ext_id=str(row.ext_id),
            name=str(row.name),
            team=str(row.team or ""),
            pos=str(row.primary_pos or ""),
            proj=_num(row.proj_points),
            horizon=_num(raw.get("horizon_xpts")),
            fit_next=_num(raw.get("fit_next"), _num(row.proj_points)),
            fit_horizon=_num(raw.get("fit_horizon"), _num(raw.get("horizon_xpts"))),
            ros=_num(raw.get("ros_xpts")),
            ros_ppg=_num(raw.get("ros_ppg")),
            yellows=int(_num(raw.get("yellows"))),
            yc_to_ban=int(_num(raw.get("yc_to_ban"), 5)),
            susp_risk=raw.get("susp_risk") is True,
            p_start=_num(raw.get("p_start")),
            provider_rank=int(_num(row.provider_rank, 9999)),
            unavailable=raw.get("unavailable") is True,
            vbd=_num(row.vbd),
            cs_prob=_num(raw.get("cs_prob")),
            xgi90=_num(raw.get("xgi90")),
            ict90=_num(raw.get("ict90")),
            inf90=_num(raw.get("inf90")),
            cre90=_num(raw.get("cre90")),
            thr90=_num(raw.get("thr90")),
            xgc90=_num(raw.get("xgc90")),
            starts=int(_num(raw.get("starts"))),
            status=str(row.injury_status if row.injury_status is not None else "a"),
            news=str(row.outlook or ""),
            owner=str(raw.get("owner") or ""),
            owner_name=str(raw.get("owner_name") or ""),
            available=raw.get("available") is not False and not raw.get("owner"),
            set_piece=str(raw.get("set_piece") or ""),
            next_opp=str(raw.get("next_opp") or ""),
            next_fdr=int(_num(raw.get("next_fdr"))),
            form=_num(raw.get("form")),
            minutes=_num(raw.get("minutes")),
            ppg=_num(raw.get("ppg")),
            total_points=_num(raw.get("total_points")),
            gws=[GwCell.from_raw(g) for g in (raw.get("gws") or []) if isinstance(g, dict)],
            components={k: _num(v) for k, v in (raw.get("components") or {}).items()},
        )
