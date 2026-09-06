"""Per-player expected-points (xPts) model for one matchday.

Pure function of plain dataclasses + params, so it unit-tests without a DB or
network. See tests/test_projections.py.
"""

from __future__ import annotations

import math
import random

from .. import MODEL_VERSION
from ..types import Player, PlayerStat, Position, Projection, Team
from ..ucl import scoring
from .params import ModelParams


def _poisson(rng: random.Random, mu: float) -> int:
    """Knuth's Poisson sampler — fine for the small means we deal with."""
    if mu <= 0:
        return 0
    limit = math.exp(-mu)
    k, prod = 0, 1.0
    while True:
        prod *= rng.random()
        if prod <= limit:
            return k
        k += 1


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q / 100.0 * (len(s) - 1))))
    return s[idx]


def _minutes_model(p_start: float, params: ModelParams) -> tuple[float, float, float]:
    """Return (exp_minutes, p_any_appearance, p_60_plus)."""
    p_any = min(1.0, p_start + params.sub_appearance_prob * (1.0 - p_start))
    p60 = p_start * 0.86
    exp_minutes = p_start * params.starter_minutes + (p_any - p_start) * params.sub_minutes
    return exp_minutes, p_any, p60


def start_probability(player: Player, stat: PlayerStat | None) -> float:
    """Crude P(starts) from availability + how much they've been playing."""
    if player.status_code >= 2:
        return 0.0
    base = 0.75
    if stat and stat.matches > 0:
        share = stat.minutes / (stat.matches * 90.0)
        base = max(0.05, min(0.98, share))
    if player.status_code == 1:  # knock / doubt
        base *= 0.55
    return round(base, 3)


def _opponent_factor(opp: Team, is_home: bool, params: ModelParams) -> float:
    """How much this fixture inflates/deflates attacking output: leaky opponent
    and home advantage push it up."""
    ha = params.home_adv if is_home else 1.0 / params.home_adv
    return max(0.2, opp.defence_rating * ha)


def _team_conceded_xg(team: Team, opp: Team, is_home: bool, params: ModelParams) -> float:
    ha = (1.0 / params.home_adv) if is_home else params.home_adv
    return max(0.05, params.league_avg_goals * opp.attack_rating * team.defence_rating * ha)


def project_player(
    player: Player,
    stat: PlayerStat | None,
    team: Team,
    opponent: Team,
    is_home: bool,
    matchday: int,
    params: ModelParams,
    *,
    rng: random.Random | None = None,
) -> Projection:
    pos: Position = player.position
    if player.status_code >= 2:
        return blank_projection(player, matchday)

    p_start = start_probability(player, stat)
    exp_minutes, p_any, p60 = _minutes_model(p_start, params)
    minutes_frac = exp_minutes / 90.0

    s = stat or PlayerStat(player_id=player.uefa_player_id)
    opp_factor = _opponent_factor(opponent, is_home, params)

    exp_goals = s.npxg90 * minutes_frac * opp_factor
    exp_assists = s.xag90 * minutes_frac * opp_factor

    goal_pts = exp_goals * scoring.GOAL_POINTS[pos]
    assist_pts = exp_assists * scoring.ASSIST_POINTS
    appearance_pts = p_any * scoring.PTS_PLAYED_UP_TO_60 + p60 * (
        scoring.PTS_PLAYED_60_PLUS - scoring.PTS_PLAYED_UP_TO_60
    )

    conceded_xg = _team_conceded_xg(team, opponent, is_home, params)
    # P(0 goals) under Poisson(conceded_xg).
    cs_prob = math.exp(-conceded_xg)

    clean_sheet_pts = 0.0
    conceded_pts = 0.0
    save_pts = 0.0
    if pos in ("GK", "DEF", "MID"):
        clean_sheet_pts = p60 * cs_prob * scoring.CLEAN_SHEET_POINTS[pos]
    if pos in ("GK", "DEF"):
        # every 2 conceded => -1  ->  -0.5 per conceded goal
        conceded_pts = -p60 * conceded_xg * (
            abs(scoring.GOALS_CONCEDED_PENALTY) / scoring.GOALS_CONCEDED_PER_PENALTY
        )
    if pos == "GK":
        save_pct = s.save_pct or params.gk_save_pct_default
        shots_on_target = conceded_xg * params.sot_per_xg
        exp_saves = shots_on_target * save_pct
        save_pts = p60 * (exp_saves / scoring.SAVES_PER_POINT) * scoring.SAVE_POINTS

    rec90 = scoring.BASELINE_RECOVERIES90[pos]
    recovery_pts = (
        minutes_frac * rec90 / scoring.RECOVERIES_PER_BONUS * scoring.RECOVERY_BONUS
    )

    discipline_pts = -params.discipline_rate * p_any

    motm_pts = scoring.MOTM_POINTS * 0.13 * (exp_goals * 0.9 + exp_assists * 0.5)

    model_xpts = (
        goal_pts
        + assist_pts
        + appearance_pts
        + clean_sheet_pts
        + conceded_pts
        + save_pts
        + recovery_pts
        + discipline_pts
        + motm_pts
    )

    # Blend with UEFA's own recent form (points per match). Only blend when the
    # player is expected to feature, so benched players aren't propped up.
    form_component = player.uefa_form * p_any
    xpts = (1.0 - params.form_weight) * model_xpts + params.form_weight * form_component

    lo, hi = _simulate_range(
        exp_goals, exp_assists, cs_prob if pos in ("GK", "DEF", "MID") else 0.0,
        pos, p60, params, rng,
    )
    # Recentre the simulated spread around the blended mean.
    centre = exp_goals * scoring.GOAL_POINTS[pos] + exp_assists * scoring.ASSIST_POINTS
    shift = xpts - (centre + appearance_pts)
    lo = max(0.0, lo + shift)
    hi = hi + shift

    price = player.price if player.price > 0 else 1e9
    xpts_r = round(xpts, 2)
    return Projection(
        player_id=player.uefa_player_id,
        matchday=matchday,
        p_start=p_start,
        exp_minutes=round(exp_minutes, 1),
        xpts=xpts_r,
        xpts_captain=round(2.0 * xpts_r, 2),
        value=round(xpts / price, 4),
        xpts_high=round(hi, 2),
        xpts_low=round(lo, 2),
        components={
            "goals": round(goal_pts, 2),
            "assists": round(assist_pts, 2),
            "appearance": round(appearance_pts, 2),
            "clean_sheet": round(clean_sheet_pts, 2),
            "conceded": round(conceded_pts, 2),
            "saves": round(save_pts, 2),
            "recoveries": round(recovery_pts, 2),
            "discipline": round(discipline_pts, 2),
            "motm": round(motm_pts, 2),
            "model_xpts": round(model_xpts, 2),
            "form_component": round(form_component, 2),
            "cs_prob": round(cs_prob, 3),
            "opp_factor": round(opp_factor, 3),
        },
    )


def _simulate_range(
    exp_goals: float,
    exp_assists: float,
    cs_prob: float,
    pos: Position,
    p60: float,
    params: ModelParams,
    rng: random.Random | None,
) -> tuple[float, float]:
    rng = rng or random.Random(12345)
    n = max(200, params.sim_n)
    cs_threshold = cs_prob * p60
    pts: list[float] = []
    for _ in range(n):
        g = _poisson(rng, max(exp_goals, 1e-6))
        a = _poisson(rng, max(exp_assists, 1e-6))
        v = g * scoring.GOAL_POINTS[pos] + a * scoring.ASSIST_POINTS
        if cs_threshold > 0 and rng.random() < cs_threshold:
            v += scoring.CLEAN_SHEET_POINTS[pos]
        pts.append(v)
    return _percentile(pts, 15), _percentile(pts, 85)


def blank_projection(player: Player, matchday: int) -> Projection:
    return Projection(
        player_id=player.uefa_player_id,
        matchday=matchday,
        p_start=0.0,
        exp_minutes=0.0,
        xpts=0.0,
        xpts_captain=0.0,
        value=0.0,
        xpts_high=0.0,
        xpts_low=0.0,
        components={"note": 0.0},
    )


def model_version() -> str:
    return MODEL_VERSION


__all__ = ["blank_projection", "model_version", "project_player", "start_probability"]
