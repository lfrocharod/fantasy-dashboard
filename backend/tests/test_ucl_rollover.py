"""From one Champions League matchday's final whistle to the next one's first
kickoff, the finished matchday stays on screen while the sync already works
on the next. Its result must come from the squad that played it, and the
tables built on it must not count the matchday that hasn't started."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from fantasy.config import Docs, Keys
from fantasy.leagues.ucl.pipeline import _live_stage
from fantasy.leagues.ucl.types import Fixture, Player, SquadPick, Team

TEAMS = {i: Team(uefa_team_id=i, name=f"C{i}", code=f"C{i}") for i in range(1, 7)}
# 11 starters, then the bench
PLAN = [("GK", 1), ("DEF", 1), ("DEF", 2), ("DEF", 3), ("MID", 1), ("MID", 2), ("MID", 3),
        ("MID", 4), ("FWD", 1), ("FWD", 2), ("FWD", 5),
        ("GK", 3), ("DEF", 4), ("MID", 6), ("FWD", 6)]


def _fixtures() -> list[Fixture]:
    """MD1 finished this afternoon; MD2, the current matchday, is next week."""
    now = datetime.now(UTC)
    out = []
    for md, kickoff, status in ((1, now - timedelta(hours=5), "finished"),
                                (2, now + timedelta(days=6), "upcoming")):
        for i, (home, away) in enumerate(((1, 2), (3, 4), (5, 6))):
            out.append(Fixture(uefa_match_id=10 * md + i, matchday=md, home_team_id=home,
                               away_team_id=away, kickoff=kickoff, status=status))
    return out


def _players() -> list[Player]:
    return [Player(uefa_player_id=pid, name=f"P{pid}", team_id=club, position=pos)
            for pid, (pos, club) in enumerate(PLAN, start=10)]


def _squad(captain: int) -> list[SquadPick]:
    return [SquadPick(player_id=10 + i, is_starter=i < 11, is_captain=10 + i == captain,
                      is_vice=False, bench_order=0 if i < 11 else i - 10)
            for i in range(15)]


class _DB:
    """The slice of DB the live stage touches: squads stored per matchday, the
    archived MD1 points (everyone played; P18 hauled 12), and what was written."""

    def __init__(self, squads: dict[int, list[SquadPick]]) -> None:
        self.squads = squads
        self.scores = {1: {pid: (12 if pid == 18 else 2, True, True) for pid in range(10, 25)}}
        self.docs: dict[str, object] = {}
        self.snapshots: list[tuple[object, ...]] = []

    def load_my_squad(self, md: int) -> list[SquadPick]:
        return self.squads.get(md, [])

    def load_projections(self, md: int) -> list[object]:
        return []

    def load_player_scores(self, md: int) -> dict[int, tuple[int, bool, bool]]:
        return self.scores.get(md, {})

    def load_league_standings(self, league_id: str, md: int) -> list[object]:
        return []

    def upsert_player_scores(self, rows: object) -> None:
        pass

    def upsert_fixtures(self, fixtures: object) -> None:
        pass

    def put_document(self, key: str, doc: object) -> None:
        self.docs[key] = doc

    def insert_live_snapshot(self, *row: object) -> None:
        self.snapshots.append(row)


class _QuietFeeds:
    """UEFA's live scoring feeds with nothing new in them."""

    def get_live_player_points(self) -> dict[str, object]:
        return {"data": {"value": {"totalPoints": {}, "scores": {}}}}

    def get_live_match(self, match_id: int) -> dict[str, object]:
        return {}


def _sync_after_the_roll_over(squads: dict[int, list[SquadPick]]) -> _DB:
    db = _DB(squads)
    # `picks` is what this sync fetched for MD2: a new captain, P10
    _live_stage(db, SimpleNamespace(dry_run=False), _QuietFeeds(), _players(), TEAMS,
                _fixtures(), [], _squad(captain=10), 2, "L1", "me", [])
    return db


def test_a_finished_matchday_is_scored_with_the_squad_that_played_it() -> None:
    db = _sync_after_the_roll_over({1: _squad(captain=18), 2: _squad(captain=10)})
    live = db.docs[Docs.UCL_LIVE_STATE]
    assert isinstance(live, dict)
    assert (live["matchday"], live["state"]) == (1, "finished")
    # ten starters on 2 and P18's 12, doubled as MD1's captain (MD2's: 34)
    assert live["securedPoints"] == live["projectedFinish"] == 44.0


def test_the_kept_result_adds_nothing_to_the_matchday_history() -> None:
    db = _sync_after_the_roll_over({1: _squad(captain=18), 2: _squad(captain=10)})
    assert db.snapshots == []


def test_without_the_finished_matchdays_squad_there_is_no_result() -> None:
    db = _sync_after_the_roll_over({2: _squad(captain=10)})
    assert db.docs[Docs.UCL_LIVE_STATE] is None


# ---- the pages -----------------------------------------------------------------------


@pytest.mark.db
def test_league_tables_count_only_matchdays_that_have_kicked_off(migrated_db: str) -> None:
    from fantasy.core import models as M
    from fantasy.core.database import session_factory
    from fantasy.leagues.ucl import views

    with session_factory()() as s:
        s.add_all([M.Team(uefa_team_id=i, name=f"C{i}") for i in (1, 2)])
        s.flush()
        s.add_all([
            M.Fixture(uefa_match_id=1, matchday=1, home_team_id=1, away_team_id=2,
                      status="finished"),
            M.Fixture(uefa_match_id=2, matchday=2, home_team_id=2, away_team_id=1,
                      status="upcoming"),
        ])
        for row in (M.League(sport="ucl", current_round=2),
                    M.Setting(key=Keys.LEAGUE_ID, value="L1"),
                    M.Setting(key=Keys.ENTRY_ID, value="me")):
            s.merge(row)
        # the sync files a table under MD2 as soon as it's current, before a ball is kicked
        for md, points in ((1, {"me": 60, "you": 40}), (2, {"me": 0, "you": 0})):
            for rank, (entry, total) in enumerate((("me", 60), ("you", 40)), start=1):
                s.add(M.LeagueStanding(league_id="L1", entry_id=entry, manager_name=entry,
                                       matchday=md, points=points[entry], total_points=total,
                                       rank=rank))
        s.commit()
        page = views.league_page(s)

    assert page.matchday == 1  # "standings after matchday 1"
    assert [r.points for r in page.standings] == [60, 40]
    assert page.mds_left == 7
    assert {a.entry_id: (a.matchdays, a.avg) for a in page.power_ranking} == {
        "me": (1, 60.0), "you": (1, 40.0),
    }


@pytest.mark.db
def test_the_matchday_graph_ends_at_the_final_whistle(migrated_db: str) -> None:
    from fantasy.core import models as M
    from fantasy.core.database import session_factory
    from fantasy.leagues.ucl import views

    t0 = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)
    with session_factory()() as s:
        for i, (secured, state) in enumerate(((30, "live"), (80, "finished"), (80, "finished"),
                                              (43, "finished"))):
            s.add(M.LiveSnapshot(matchday=2, captured_at=t0 + timedelta(minutes=30 * i),
                                 secured=secured, projected=secured, pre_match=60,
                                 state=state))
        s.commit()
        points = views.live_history(s, 2)

    assert [(p.secured, p.state) for p in points] == [(30, "live"), (80, "finished")]
