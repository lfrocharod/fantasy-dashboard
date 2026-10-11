"""Position-aware fixture difficulty (1 easy … 5 hard).

Two underlying axes per fixture:
  attack difficulty  — how hard to get goals / assists: the opponent's
    defensive solidity (a stingy back line is red for your attackers);
  defence difficulty — how hard to keep a clean sheet: the opponent's attack.

The blend that matters depends on position AND the game's scoring: GK is pure
clean sheet, DEF mostly clean sheet with real set-piece/overlap upside, MID
mostly attacking with a little clean-sheet/DefCon weight, FWD pure attacking.

Rating convention (matches the pipeline): attack > 1 scores more than average;
defence > 1 concedes MORE than average (leakier). Home sides get a small ease.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fantasy.football.jsmath import js_round

League = Literal["ucl", "fpl"]

# per-game DEF / MID weights — tuned to scoring:
#  UCL: DEF goal = 6 (= GK, > MID's 5), CS = 4 -> defenders' attacking upside is
#       worth relatively more; a MID clean sheet is only 1pt.
#  FPL: DEF goal = 6, CS = 4, DefCon +2 (defenders hit it often) -> the clean
#       sheet is the more reliable route; def-mids get DefCon too.
WEIGHTS: dict[str, dict[str, tuple[float, float]]] = {
    "ucl": {"def": (0.58, 0.42), "mid": (0.82, 0.18)},
    "fpl": {"def": (0.66, 0.34), "mid": (0.76, 0.24)},
}


def scale(raw: float) -> int:
    return max(1, min(5, js_round(3 + 2.2 * raw)))


@dataclass(frozen=True, slots=True)
class PosFdr:
    att: int  # difficulty of attacking returns
    def_: int  # difficulty of a clean sheet
    pos: int  # the number to colour by for this position


def pos_fdr(
    opp_attack: float,
    opp_defence: float,
    is_home: bool,
    pos: str,
    league: League,
    own_attack: float = 1.0,
    own_defence: float = 1.0,
) -> PosFdr:
    # venue swing is ~1/3 of an FDR point
    ha = -0.15 if is_home else 0.15
    # your own side's quality shifts the fixture: a strong attack finds any
    # defence easier; a strong defence keeps more clean sheets
    raw_att = 1.25 * (1 - opp_defence) - 0.45 * (own_attack - 1) + ha
    raw_def = 1.25 * (opp_attack - 1) + 0.45 * (own_defence - 1) + ha
    w = WEIGHTS[league]
    if pos in ("GK", "GKP"):
        blend = raw_def
    elif pos == "DEF":
        blend = w["def"][0] * raw_def + w["def"][1] * raw_att
    elif pos == "MID":
        blend = w["mid"][0] * raw_att + w["mid"][1] * raw_def
    else:  # FWD
        blend = raw_att
    return PosFdr(att=scale(raw_att), def_=scale(raw_def), pos=scale(blend))


def blended_rate(opp_attack: float, opp_defence: float, is_home: bool) -> int:
    """The position-neutral 1-5 fixture rating used by the UCL ticker's
    "blended" view and the optimizer's opponent colouring."""
    raw = 0.55 * (opp_attack - 1) + 0.55 * (1 - opp_defence) + (-0.15 if is_home else 0.15)
    return max(1, min(5, js_round(3 + 2.2 * raw)))
