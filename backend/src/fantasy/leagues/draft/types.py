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
    # FPL-Draft extras (kept in `raw` on write; the sport-agnostic columns above
    # cover NFL). owner "" = free agent in your league.
    owner: str = ""
    owner_name: str = ""
    available: bool = True
    set_piece: str = ""  # "P" pens, "F" free-kicks, "C" corners (order == 1)
    next_opp: str = ""
    next_fdr: int = 0
    form: float = 0.0
    minutes: int = 0


# ESPN slotId / positionId -> label
ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
ESPN_SLOT = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DST", 17: "K",
    23: "FLEX", 20: "BE", 21: "IR", 7: "OP", 3: "RB/WR", 5: "WR/TE",
}

# 12-team PPR replacement baselines: starters * teams, roughly.
DEFAULT_ROSTER = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1, "BE": 6}

# ---- FPL Draft --------------------------------------------------------------
FPL_POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
# FPL Draft standard squad: 2/5/5/3, 11 starters (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD).
FPL_ROSTER = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}

# Rough PL club attack / defence multipliers (mean ~1.0). attack >1 scores more,
# defence >1 concedes more. Eyeballed from recent seasons; the board tunes itself
# as results come in via `blend`.
# (attack, defence) multipliers, competition mean ~1.0.
#   attack  > 1  => scores more than an average side
#   defence < 1  => concedes LESS than average (a strong back line)
FPL_CLUB_STRENGTH: dict[str, tuple[float, float]] = {
    "ARS": (1.28, 0.56), "MCI": (1.42, 0.66), "LIV": (1.38, 0.74), "CHE": (1.20, 0.82),
    "NEW": (1.12, 0.80), "MUN": (1.10, 0.94), "TOT": (1.18, 0.98), "AVL": (1.10, 0.90),
    "BHA": (1.08, 0.98), "CRY": (1.02, 0.84), "FUL": (0.98, 0.98), "BOU": (1.04, 1.02),
    "BRE": (1.06, 1.06), "NFO": (0.98, 1.00), "EVE": (0.92, 0.90),
    # promoted 2025/26 -> 2026/27
    "SUN": (0.86, 1.12), "LEE": (0.86, 1.16), "COV": (0.82, 1.18),
    "HUL": (0.80, 1.20), "IPS": (0.82, 1.18),
}
