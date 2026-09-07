from fantasy_ingest.draft.nfl_season import (
    _matchup_rating,
    _rank_to_pts,
    _vor,
    parse_league,
    parse_standings,
)
from fantasy_ingest.draft.types import DraftRow


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


def test_rank_to_pts_monotonic_and_qb_bonus():
    assert _rank_to_pts(1, "RB") > _rank_to_pts(50, "RB") > _rank_to_pts(150, "RB")
    assert _rank_to_pts(5, "QB") > _rank_to_pts(5, "RB")


def test_vor_replacement_by_position():
    rows = [
        DraftRow(sport="nfl", ext_id=str(i), name=f"RB{i}", primary_pos="RB", positions=["RB"],
                 raw={"rosProj": 200 - i * 5})
        for i in range(20)
    ]
    _vor(rows, {"RB": 2, "FLEX": 1}, teams=10)
    assert rows[0].vbd > 0 and rows[-1].vbd < rows[0].vbd
