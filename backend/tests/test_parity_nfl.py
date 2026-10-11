"""The Python NFL analysis must reproduce the original TypeScript (the old web
app's app/nfl/lib.ts) on the same inputs; see tests/parity/."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from fantasy.leagues.nfl import analysis as A
from fantasy.leagues.nfl.players import NflPlayer

HERE = Path(__file__).parent / "parity"
INPUTS = json.loads((HERE / "inputs.json").read_text())["nfl"]
GOLD = json.loads((HERE / "goldens.json").read_text())["nfl"]


def row(d: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        ext_id=d["extId"], name=d["name"], team=d.get("team"), primary_pos=d.get("primaryPos"),
        proj_points=d.get("projPoints"), vbd=d.get("vbd"), ecr_rank=d.get("ecrRank"),
        ecr_tier=d.get("ecrTier"), raw=d.get("raw"),
    )


PLAYERS = [NflPlayer.from_row(row(d)) for d in INPUTS["players"]]
TEAMS = A.group_teams(PLAYERS, INPUTS["myTeamId"])
ME = next(t for t in TEAMS if t.is_mine)
RIVALS = [t for t in TEAMS if not t.is_mine]
SLOTS: dict[str, int] = INPUTS["slots"]


def ids(ps: list[NflPlayer]) -> list[str]:
    return [p.ext_id for p in ps]


def approx(x: Any) -> Any:
    return pytest.approx(x, rel=1e-9, abs=1e-9)


def test_per_player_values() -> None:
    for p, w in zip(PLAYERS, GOLD["players"], strict=True):
        assert p.ext_id == w["extId"] and p.available == w["available"]
        assert A.usage_tag(p) == w["usageTag"]
        assert A.opp_factor(p) == approx(w["oppFactor"])
        assert A.adj_ros(p) == approx(w["adjRos"])
        assert A.opp_tag(p) == w["oppTag"]
        assert [A.week_points(p, i) for i in range(4)] == approx(w["weekPoints"])
        assert [A.week_points(p, i, 7) for i in (1, 2, 5)] == approx(w["weekPointsWl"])
        assert [
            {"lo": lo, "hi": hi} for lo, hi in (A.week_range(p, i) for i in (0, 1))
        ] == [approx(r) for r in w["weekRange"]]
        assert [A.mode_score(m)(p) for m in ("floor", "mean", "ceiling")] == approx(w["modeScores"])


def test_modes_and_win_probability() -> None:
    got = [A.lineup_mode(w, by) for w in (10, 40, 41, 61.9, 62, 90) for by in (False, True)]
    assert got == GOLD["lineupModes"]
    assert [A.win_prob_from_margin(m) for m in (-60, -19, -0.5, 0, 0.5, 7, 19, 60)] == GOLD["winProb"]


def test_group_teams() -> None:
    got = [
        {"teamId": t.team_id, "name": t.name, "isMine": t.is_mine, "players": ids(t.players),
         "rosTotal": t.ros_total, "byPos": {k: ids(v) for k, v in t.by_pos.items()}}
        for t in TEAMS
    ]
    assert got == GOLD["teams"]


def _lineup(lu: A.Lineup) -> dict[str, Any]:
    return {
        "starters": [[s.slot, s.player.ext_id if s.player else None] for s in lu.starters],
        "bench": ids(lu.bench),
        "total": approx(lu.total),
    }


def test_optimal_lineups_and_calls() -> None:
    got = [
        _lineup(A.optimal_lineup(ME.players, SLOTS, 0)),
        _lineup(A.optimal_lineup(ME.players, SLOTS, 2)),
        _lineup(A.optimal_lineup(ME.players, SLOTS, 0, A.mode_score("ceiling"))),
        _lineup(A.optimal_lineup(ME.players, SLOTS, 0, A.mode_score("floor"))),
        _lineup(A.optimal_lineup(RIVALS[0].players, SLOTS, 0)),
    ]
    for g, w in zip(got, GOLD["lineups"], strict=True):
        assert g["starters"] == w["starters"] and g["bench"] == w["bench"]
        assert w["total"] == g["total"]
    starters = {
        s.player.ext_id for s in A.optimal_lineup(ME.players, SLOTS, 0).starters if s.player
    }
    assert [[p.ext_id, A.start_sit_call(p, starters)] for p in ME.players] == GOLD["startSit"]


def test_trade_ideas() -> None:
    got = [
        {"rival": t.rival_name, "rivalTeamId": t.rival_team_id, "give": t.give.ext_id,
         "get": t.get.ext_id, "myGain": t.my_gain, "theirGain": t.their_gain}
        for t in A.nfl_trade_ideas(ME, RIVALS, SLOTS)
    ]
    assert got == GOLD["tradeIdeas"]


def test_clubs() -> None:
    fx = A.nfl_club_fixtures(PLAYERS)
    assert [{"team": c.team, "avgFdr": approx(c.avg_fdr)} for c in fx] == GOLD["clubFixtures"]
    got = [
        {"team": d.team, "avgFdr": approx(d.avg_fdr), "starters": ids(d.starters),
         "bench": ids(d.bench), "doubts": ids(d.doubts), "bye": d.bye}
        for d in A.nfl_club_dossiers(PLAYERS)
    ]
    assert got == GOLD["clubDossiers"]


@pytest.mark.parametrize(
    ("rule", "key"), [("H2H_RECORD", "playoffs"), ("TOTAL_POINTS_SCORED", "playoffsByPoints")]
)
def test_playoff_simulation_agrees_statistically(rule: str, key: str) -> None:
    # Monte Carlo on both sides (20k iterations each): compare within noise.
    standings = [A.Standing(**s) for s in INPUTS["standings"]]
    schedule = [A.Game(**g) for g in INPUTS["schedule"]]
    got = A.sim_playoffs(
        TEAMS, standings, schedule, SLOTS, INPUTS["week"], INPUTS["regWeeks"],
        INPUTS["playoffTeams"], INPUTS["myTeamId"], rule, iters=20000,
        rng=np.random.default_rng(7),
    )
    want = {w["teamId"]: w for w in GOLD[key]}
    assert {o.team_id for o in got} == set(want)
    for o in got:
        w = want[o.team_id]
        assert o.playoff_pct == pytest.approx(w["playoffPct"], abs=2.5)
        assert o.bye_pct == pytest.approx(w["byePct"], abs=2.5)
        assert o.proj_wins == pytest.approx(w["projWins"], abs=0.1)
        assert o.proj_pf == pytest.approx(w["projPf"], rel=0.005)
