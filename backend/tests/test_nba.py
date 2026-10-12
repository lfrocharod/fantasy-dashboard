"""ESPN basketball: parsing, the calendar, projections and the lineup maths."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from fantasy.leagues.nba import analysis as A
from fantasy.leagues.nba import board
from fantasy.leagues.nba import league as L
from fantasy.leagues.nba.players import NbaPlayer


def player(pid: str, fppg: float, slots: list[str], team: int = 1, injury: str = "ACTIVE",
           pos: str = "", slot: str = "BE", proj_games: int = 70, droppable: bool = True,
           status: str = "FREEAGENT") -> NbaPlayer:
    return NbaPlayer(
        ext_id=pid, name=f"P{pid}", team=f"T{team}", pro_team_id=team, pos=pos or slots[0],
        positions=[s for s in slots if s in ("PG", "SG", "SF", "PF", "C")], slots=[*slots, "UT"],
        fppg=fppg, fppg_proj=fppg, proj_games=proj_games, fppg_now=0.0, gp_now=0,
        fppg_last=0.0, gp_last=0, fppg_l15=0.0, gp_l15=0, line={}, line_source="",
        injury=injury, pct_owned=0.0, pct_started=0.0, pct_change=0.0, status=status,
        owner_team_id=None, owner_name="", slot=slot, droppable=droppable, adp=0.0,
    )


def every_day(*teams: int, days: range = range(1, 8)) -> dict[int, dict[int, tuple[int, bool]]]:
    return {t: {d: (99, True) for d in days} for t in teams}


# ---- rules and calendar ------------------------------------------------------------------


def league_payload() -> dict:
    units = {str(mp): [mp] for mp in range(1, 20)}
    units.update({"20": [20, 21], "21": [22, 23]})
    return {
        "settings": {
            "name": "Test",
            "scoringSettings": {"scoringType": "H2H_POINTS", "scoringItems": [
                {"statId": 0, "points": 1}, {"statId": 11, "points": -2}]},
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "5": 1, "11": 3, "12": 3, "13": 1},
                               "positionLimits": {"5": 4, "1": -1}},
            "scheduleSettings": {"matchupPeriodCount": 19, "matchupPeriods": units,
                                 "playoffTeamCount": 4, "playoffSeedingRule": "H2H_RECORD"},
            "acquisitionSettings": {"matchupAcquisitionLimit": -1},
            "tradeSettings": {"deadlineDate": 1803661200000},
        },
        "status": {"currentMatchupPeriod": 3, "firstScoringPeriod": 1, "finalScoringPeriod": 167},
    }


def test_parse_rules() -> None:
    r = L.parse_rules(league_payload())
    assert r.slots == {"PG": 1, "G": 1, "UT": 3} and (r.bench, r.ir) == (3, 1)
    assert r.position_limits == {"C": 4}
    assert r.scoring == {0: 1.0, 11: -2.0} and r.is_points
    assert r.reg_periods == 19 and r.playoff_periods == [20, 21]
    assert r.acquisition_limit is None  # -1 = unlimited
    assert r.trade_deadline and r.trade_deadline.startswith("2027-02-26")


def test_calendar_stretches_the_opening_week() -> None:
    """167 days in 23 week units: the opening week runs Tuesday to the Sunday
    after next (13 days) so every later unit is a Monday-to-Sunday week."""
    opening = date(2026, 10, 20)  # a Tuesday
    day_dates = {d: opening + timedelta(days=d - 1) for d in range(1, 175) if d % 9}
    cal = L.build_calendar(L.parse_rules(league_payload()), day_dates)
    assert cal.periods[1] == (1, 13)
    assert cal.periods[2] == (14, 20) and cal.day_dates[14].weekday() == 0
    assert cal.periods[19] == (133, 139)
    assert cal.periods[20] == (140, 153) and cal.periods[21] == (154, 167)
    assert not cal.warnings
    assert cal.period_of(13) == 1 and cal.period_of(14) == 2 and cal.period_of(500) == 21
    assert cal.day_of(date(2026, 10, 1)) == 1  # preseason: opening night


def test_pro_schedule_dates_are_eastern() -> None:
    """A 10:30pm Eastern tip is the next day in UTC; the scoring period is the
    Eastern date."""
    late = int(datetime(2026, 10, 22, 2, 30, tzinfo=UTC).timestamp() * 1000)
    sched = {"settings": {"proTeams": [
        {"id": 1, "abbrev": "aaa", "proGamesByScoringPeriod": {"2": [
            {"date": late, "homeProTeamId": 1, "awayProTeamId": 2, "scoringPeriodId": 2}]}},
        {"id": 0, "abbrev": "FA"},
    ]}}
    teams, dates = L.pro_teams(sched)
    assert set(teams) == {1} and teams[1].abbrev == "AAA"
    assert teams[1].games == {2: (2, True)} and dates[2] == date(2026, 10, 21)


# ---- projections -------------------------------------------------------------------------


def test_blend_hands_over_to_the_season_average() -> None:
    assert board.blend(40, 0, 0, 0, 0, 0, 0) == 40
    assert board.blend(40, 30, 60, 0, 0, 0, 0) == pytest.approx(38)  # 0.8 proj + 0.2 last
    at_prior = board.blend(40, 0, 0, 30, board.PRIOR_GAMES, 0, 0)
    assert at_prior == pytest.approx(35)  # equal weight at PRIOR_GAMES games
    assert board.blend(0, 0, 0, 25, 3, 0, 0) == 25  # no projection: the season so far


def test_split_recomputes_when_espn_leaves_the_average_out() -> None:
    stats = [{"id": "102027", "appliedAverage": None,
              "averageStats": {"0": 20.0, "11": 2.0, "42": 70.0}}]
    fppg, games, _ = board.split(stats, "102027", {0: 1.0, 11: -2.0})
    assert (fppg, games) == (16.0, 70)


def test_injury_tags_fade_with_the_days_ahead() -> None:
    dtd = player("1", 30, ["PG"], injury="DAY_TO_DAY")
    out = player("2", 30, ["PG"], injury="OUT")
    assert A.availability(dtd, 0) == pytest.approx(0.75)
    assert A.availability(dtd, 3) > 0.9
    assert A.availability(out, 0) == 0 and 0.3 < A.availability(out, 7) < A.availability(out, 14) < 1
    assert A.availability(player("3", 30, ["PG"]), 0) == 1


# ---- the daily lineup --------------------------------------------------------------------


def test_best_lineup_reseats_to_fit_everyone() -> None:
    """A flexible player first takes PG; the PG-only player arriving next is
    seated by moving him to SG — the augmenting path."""
    flexible = player("1", 40, ["PG", "SG"])
    pg_only = player("2", 35, ["PG"])
    seats, benched = A.best_lineup([flexible, pg_only], A.game_value, ["PG", "SG"])
    assert {s.slot: s.player.ext_id for s in seats if s.player} == {"PG": "2", "SG": "1"}
    assert benched == []


def test_best_lineup_benches_the_lowest() -> None:
    ps = [player(str(i), 50 - i, ["C"]) for i in range(4)]
    seats, benched = A.best_lineup(ps, A.game_value, ["C", "UT"])
    assert sorted(s.player.ext_id for s in seats if s.player) == ["0", "1"]
    assert [p.ext_id for p in benched] == ["2", "3"]


def test_slot_list_follows_espn_order() -> None:
    assert A.slot_list({"UT": 3, "C": 1, "PG": 1, "G": 1}) == ["PG", "C", "G", "UT", "UT", "UT"]


def test_plan_days_skips_ir_and_off_days() -> None:
    games = {1: {1: (9, True), 3: (9, False)}, 2: {2: (9, True)}}
    a = player("1", 30, ["PG"], team=1)
    b = player("2", 20, ["PG"], team=2)
    hurt = player("3", 60, ["PG"], team=1, slot="IR")
    plan = A.plan_days([a, b, hurt], [1, 2, 3], games, ["PG"])
    assert [d.points for d in plan.days] == [30, 20, 30] and plan.total == 80
    assert plan.games == 3 and plan.lost == 0


def test_win_prob() -> None:
    plan = A.plan_days([player("1", 30, ["PG"])], [1, 2], every_day(1), ["PG"])
    assert A.win_prob(0, plan, 0, plan) == 50
    assert A.win_prob(40, plan, 0, plan) > 75
    empty = A.WeekPlan([])
    assert A.win_prob(10, empty, 5, empty) == 100


# ---- streaming, trades, the playoff race ---------------------------------------------------


def test_streams_fill_empty_days_and_respect_position_limits() -> None:
    games = {1: {1: (9, True)}, 2: {d: (9, True) for d in range(1, 8)}, 3: {d: (9, True) for d in range(1, 8)}}
    roster = [player("1", 30, ["PG"], team=1, slot="PG"), player("2", 10, ["C"], team=1, pos="C")]
    fa = [player("9", 20, ["SG"], team=2), player("8", 25, ["C"], team=3, pos="C")]
    days = list(range(1, 8))
    out = A.streams(roster, fa, days, games, ["PG", "SG", "C"],
                    lambda p: A.ros_value(p, days, games), limits={"C": 1})
    assert out and out[0].add.ext_id in ("8", "9") and out[0].drop.ext_id == "2"
    assert out[0].gain > 100 and out[0].games == 7
    capped = A.streams(roster, [fa[1]], days, games, ["PG", "SG", "C"],
                       lambda p: 0.0, limits={"C": 0})
    assert capped == []  # can't take a centre past the limit


def test_trade_moves_and_verdict() -> None:
    games = every_day(1, 2, days=range(1, 100))
    mine = [player(str(i), 30 - i, ["PG"], team=1) for i in range(5)]
    star = player("50", 45, ["PG"], team=2)
    days = list(range(1, 100))
    ev = A.evaluate_trade(mine, mine[3:], [star], [player("90", 18, ["SG"], team=2)],
                          [1, 2], days, [], games, ["PG", "UT"])
    assert ev.roster_moves == ["add P90 with the open spot"]
    assert ev.my_ros > 0
    assert "propose" in ev.verdict or "counter" in ev.verdict


def test_sim_playoffs_shares_add_up() -> None:
    standings = [A.Standing(t, 0, 0, 0, 0.0) for t in range(1, 7)]
    remaining = [(1, 1, 2), (1, 3, 4), (1, 5, 6), (2, 1, 3), (2, 2, 5), (2, 4, 6)]
    strength = {(t, mp): (1000.0 + 50 * t, 90.0**2) for t in range(1, 7) for mp in (1, 2)}
    odds = A.sim_playoffs(standings, remaining, strength, playoff_teams=4, strength_sd=0.05, sims=2000)
    assert sum(o.playoff_pct for o in odds) == pytest.approx(400, abs=1)
    assert sum(o.top_seed_pct for o in odds) == pytest.approx(100, abs=1)
    by = {o.team_id: o for o in odds}
    assert by[6].playoff_pct > by[1].playoff_pct  # the stronger team, more often


def test_pickup_cap_scales_with_game_days() -> None:
    """A per-game-day limit gives seven pickups in an ordinary week, more in the
    long opening matchup, fewer around the All-Star break; a per-matchup limit
    is flat."""
    assert A.pickup_cap(1, True, 7) == 7
    assert A.pickup_cap(1, True, 13) == 13
    assert A.pickup_cap(1, True, 4) == 4
    assert A.pickup_cap(7, False, 4) == 7
    assert A.pickup_cap(None, True, 7) is None
