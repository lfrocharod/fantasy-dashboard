from types import SimpleNamespace

from fantasy.leagues.draft.types import DraftRow
from fantasy.leagues.nfl import analysis as A
from fantasy.leagues.nfl.players import NflPlayer
from fantasy.leagues.nfl.season import (
    _fp_index,
    _fp_key,
    _matchup_rating,
    _pos_rank,
    _rank_points,
    _vor,
    _weekly_projs,
    parse_league,
    parse_standings,
)


def _lg():
    return {
        "status": {"currentMatchupPeriod": 3},
        "settings": {
            "scheduleSettings": {"matchupPeriodCount": 15, "playoffTeamCount": 4},
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "20": 6}},
        },
        "teams": [
            {"id": 8, "name": "Edelman MVP", "record": {"overall": {"wins": 2, "losses": 1, "pointsFor": 300}},
             "roster": {"entries": [
                 {"playerId": 111, "lineupSlotId": 2}, {"playerId": 222, "lineupSlotId": 20},
             ]}},
            {"id": 3, "name": "Rival", "record": {"overall": {"wins": 1, "losses": 2, "pointsFor": 250}},
             "roster": {"entries": [{"playerId": 333, "lineupSlotId": 0}]}},
        ],
        "schedule": [
            {"matchupPeriodId": 3, "home": {"teamId": 8, "totalPoints": 0},
             "away": {"teamId": 3, "totalPoints": 0}},
        ],
    }


def test_parse_league_week_playoffs_slots():
    L = parse_league(_lg())
    assert L["week"] == 3
    assert L["reg_weeks"] == 15
    assert L["playoff_weeks"] == [16, 17]
    assert L["slots"]["RB"] == 2 and L["slots"]["FLEX"] == 1
    assert L["owner_of"][111] == 8 and 333 in L["owner_of"]
    assert L["rosters"][8] == [111, 222]


def test_parse_standings_sorted_by_wins():
    st = parse_standings(_lg())
    assert st[0]["name"] == "Edelman MVP" and st[0]["wins"] == 2


def test_matchup_rating_easy_vs_generous_defence():
    # team id 15 is a generous rush defence in NFL_DEF (1.12)
    _opp, fdr_easy = _matchup_rating("MIA", uses_rush=True, sched_ids={"MIA": 15})
    _opp, fdr_hard = _matchup_rating("DEN", uses_rush=True, sched_ids={"DEN": 7})
    assert 1 <= fdr_easy <= fdr_hard <= 5


def test_weekly_projections_are_this_seasons():
    """ESPN lists last season's weeks under the same numbers: a QB who sat out
    last year's week 6 still has this year's projection for it."""
    stats = [
        {"seasonId": 2025, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 6, "appliedTotal": 0},
        {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 6, "appliedTotal": 21.4},
        {"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": 5, "appliedTotal": 16.2},
        {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 0, "scoringPeriodId": 0, "appliedTotal": 241.7},
    ]
    assert _weekly_projs({"stats": stats}, 2026) == {6: 21.4}


def test_fantasypros_names_match_espns():
    rows = [
        {"player_name": "Patrick Mahomes II", "player_position_id": "QB", "player_team_id": "KC"},
        {"player_name": "Washington Commanders", "player_position_id": "DST", "player_team_id": "WAS"},
    ]
    idx = _fp_index(rows)
    assert _fp_key("Patrick Mahomes", "QB", "KC") in idx
    assert _fp_key("Commanders D/ST", "DST", "WSH") in idx


def test_expert_ranks_are_priced_within_the_position():
    by_pos = {"QB": [25.1, 22.6, 21.4, 19.9]}
    assert _pos_rank({"pos_rank": "QB2"}) == 2 and _pos_rank({"pos_rank": ""}) is None
    assert _rank_points(by_pos, "QB", 2) == 22.6
    assert _rank_points(by_pos, "QB", 9) is None and _rank_points(by_pos, "RB", 1) is None


def _qb(week_projs: dict[str, float] | None) -> NflPlayer:
    raw = {"weekProj": 21.4, "rosProj": 180.0, "matchups": [
        {"week": 6, "opp": "WSH", "home": True, "fdr": 5},
        {"week": 7, "opp": "LAR", "home": False, "fdr": 1},
    ]}
    if week_projs is not None:
        raw["weekProjs"] = week_projs
    return NflPlayer.from_row(SimpleNamespace(
        ext_id="1", name="QB", team="SF", primary_pos="QB", proj_points=21.4, vbd=0,
        ecr_rank=None, ecr_tier=None, raw=raw))


def test_espns_weekly_projection_is_not_nudged_again_for_the_matchup():
    qb = _qb({"6": 21.4, "7": 19.6})
    assert A.week_points(qb, 0) == 21.4 and A.week_points(qb, 1) == 19.6
    # without ESPN's weekly numbers the static matchup table still adjusts
    assert A.week_points(_qb(None), 0) == 21.4 * (1 + (3 - 5) * 0.05)


def test_vor_replacement_by_position():
    rows = [
        DraftRow(sport="nfl", ext_id=str(i), name=f"RB{i}", primary_pos="RB", positions=["RB"],
                 raw={"rosProj": 200 - i * 5})
        for i in range(20)
    ]
    _vor(rows, {"RB": 2, "FLEX": 1}, teams=10)
    assert rows[0].vbd > 0 and rows[-1].vbd < rows[0].vbd


def test_game_state_from_the_scoreboard():
    from fantasy.leagues.nfl.season import game_state

    assert game_state({"date": "2026-10-18T17:00Z", "status": {"type": {"state": "pre"}}})["left"] == 1.0
    mid = game_state({"status": {"type": {"state": "in"}, "period": 3, "clock": 450.0}})
    assert mid["state"] == "in" and mid["left"] == 0.375  # the 4th quarter + half the 3rd
    assert game_state({"status": {"type": {"state": "post"}}})["left"] == 0.0


def test_a_matchup_side_reads_espns_running_total():
    from fantasy.leagues.nfl.season import _side_points

    assert _side_points({"totalPoints": 0, "totalPointsLive": 87.46}) == 87.5
    assert _side_points({"totalPoints": 112.3}) == 112.3


def _starter(pid: str, proj: float, state: str, left: float) -> NflPlayer:
    raw = {"weekProj": proj, "slot": "WR", "matchups": [{"week": 6, "opp": "SF", "fdr": 3}],
           "weekProjs": {"6": proj}, "game": {"state": state, "left": left}}
    return NflPlayer.from_row(SimpleNamespace(
        ext_id=pid, name=pid, team="X", primary_pos="WR", proj_points=proj, vbd=0,
        ecr_rank=None, ecr_tier=None, raw=raw))


def test_the_win_chance_mid_week_counts_points_already_scored():
    """Up 100-80 with every one of your starters done and one of theirs (25
    projected) still to play: behind on the projection, but not by much."""
    mine = [_starter("a", 20, "post", 0.0), _starter("b", 20, "post", 0.0)]
    theirs = [_starter("c", 20, "post", 0.0), _starter("d", 25, "pre", 1.0)]
    chance = A.live_win_prob(100, 80, mine, theirs)
    assert 0 < chance < 50
    # with that starter halfway through his game, half his projection is left
    theirs[1].game_state, theirs[1].game_left = "in", 0.5
    assert A.live_win_prob(100, 80, mine, theirs) > 50
    # nothing left to play: the score decides it
    theirs[1].game_state = "post"
    assert A.live_win_prob(100, 80, mine, theirs) == 100
