"""Derive multiplicative attack / defence ratings for each team.

Two inputs are accepted, best first:
  1. Per-team season xG-for / xG-against per 90 (from FBref league tables).
  2. Played UCL fixtures with an xG estimate or, failing that, goals.

Ratings are normalised so the competition mean is 1.0:
    attack_rating  > 1  => scores more than an average side
    defence_rating > 1  => concedes more than an average side (i.e. weaker)
"""

from __future__ import annotations

from collections.abc import Iterable

from ..types import Fixture, Team


def ratings_from_season_xg(
    team_xg: dict[int, tuple[float, float]],
) -> dict[int, tuple[float, float]]:
    """team_xg: {team_id: (xg_for_per90, xg_against_per90)} -> {team_id: (atk, def)}."""
    if not team_xg:
        return {}
    n = len(team_xg)
    mean_for = sum(v[0] for v in team_xg.values()) / n
    mean_against = sum(v[1] for v in team_xg.values()) / n
    mean_for = max(mean_for, 1e-6)
    mean_against = max(mean_against, 1e-6)
    return {
        tid: (xg_for / mean_for, xg_against / mean_against)
        for tid, (xg_for, xg_against) in team_xg.items()
    }


def ratings_from_fixtures(
    fixtures: Iterable[Fixture],
    team_ids: Iterable[int],
    shrink: float = 0.5,
) -> dict[int, tuple[float, float]]:
    """Fallback: average goals (or xG estimate) for/against from finished games,
    shrunk toward 1.0 because early-season samples are tiny."""
    scored: dict[int, list[float]] = {t: [] for t in team_ids}
    conceded: dict[int, list[float]] = {t: [] for t in team_ids}

    for f in fixtures:
        if f.status != "finished":
            continue
        h_for = f.home_xg_est or (f.home_goals if f.home_goals is not None else None)
        a_for = f.away_xg_est or (f.away_goals if f.away_goals is not None else None)
        if h_for is None or a_for is None:
            continue
        scored.setdefault(f.home_team_id, []).append(h_for)
        conceded.setdefault(f.home_team_id, []).append(a_for)
        scored.setdefault(f.away_team_id, []).append(a_for)
        conceded.setdefault(f.away_team_id, []).append(h_for)

    all_for = [x for v in scored.values() for x in v]
    league_mean = (sum(all_for) / len(all_for)) if all_for else 1.4
    league_mean = max(league_mean, 1e-6)

    out: dict[int, tuple[float, float]] = {}
    for tid in scored:
        sf = scored.get(tid) or []
        sc = conceded.get(tid) or []
        atk_raw = (sum(sf) / len(sf) / league_mean) if sf else 1.0
        def_raw = (sum(sc) / len(sc) / league_mean) if sc else 1.0
        out[tid] = (
            1.0 + (atk_raw - 1.0) * (1.0 - shrink),
            1.0 + (def_raw - 1.0) * (1.0 - shrink),
        )
    return out


def apply_ratings(teams: dict[int, Team], ratings: dict[int, tuple[float, float]]) -> None:
    for tid, team in teams.items():
        atk, dfn = ratings.get(tid, (1.0, 1.0))
        team.attack_rating = round(atk, 4)
        team.defence_rating = round(dfn, 4)
