"""UEFA Champions League Fantasy scoring rules.

These mirror the public rules for the 2024/25+ ruleset. Exact wording shifts
season to season; keep the values here and let `model.params` override the ones
the projection is sensitive to. What matters for projections is the *relative*
structure (a MID goal beats a FWD goal, defenders live off clean sheets, etc.).
"""

from __future__ import annotations

from ..types import Position

# Appearance
PTS_PLAYED_UP_TO_60 = 1
PTS_PLAYED_60_PLUS = 2

# Goals, by position of the scorer
GOAL_POINTS: dict[Position, int] = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}

ASSIST_POINTS = 3

# Clean sheet (requires 60+ minutes)
CLEAN_SHEET_POINTS: dict[Position, int] = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}

# Every 2 goals conceded costs a GK/DEF one point
GOALS_CONCEDED_PER_PENALTY = 2
GOALS_CONCEDED_PENALTY = -1

# GK: one point per 3 saves
SAVES_PER_POINT = 3
SAVE_POINTS = 1
PENALTY_SAVE_POINTS = 5

# Ball recoveries: 2 points per 6 recoveries (2024/25 addition)
RECOVERIES_PER_BONUS = 6
RECOVERY_BONUS = 2

# Discipline / mistakes
YELLOW_CARD = -1
RED_CARD = -3
OWN_GOAL = -2
PENALTY_MISS = -2

# "Player of the Match" style bonus
MOTM_POINTS = 3

# Rough baseline: average recoveries per 90 by position (used when we have no
# per-player recovery data). Deliberately conservative.
BASELINE_RECOVERIES90: dict[Position, float] = {
    "GK": 3.0,
    "DEF": 7.0,
    "MID": 6.0,
    "FWD": 2.5,
}
