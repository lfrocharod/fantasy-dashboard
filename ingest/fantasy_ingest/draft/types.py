from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DraftRow:
    sport: str
    ext_id: str
    name: str
    team: str = ""
    positions: list[str] = field(default_factory=list)
    primary_pos: str = ""
    proj_points: float = 0.0
    adp: float = 0.0
    provider_rank: int | None = None
    ecr_rank: int | None = None
    ecr_tier: int | None = None
    ecr_pos_rank: str = ""
    ecr_std: float = 0.0
    vbd: float = 0.0
    bye_week: int | None = None
    injury_status: str = ""
    outlook: str = ""
    raw: dict | None = None


# ESPN slotId / positionId -> label
ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
ESPN_SLOT = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DST", 17: "K",
    23: "FLEX", 20: "BE", 21: "IR", 7: "OP", 3: "RB/WR", 5: "WR/TE",
}

# 12-team PPR replacement baselines: starters * teams, roughly.
DEFAULT_ROSTER = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1, "BE": 6}
