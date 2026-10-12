"""The private league table in the UCL pipeline: paging, and recovering when
UEFA refuses a stale league id."""

from __future__ import annotations

from typing import Any

from fantasy.leagues.ucl import pipeline
from fantasy.leagues.ucl.client import UefaAuthError


def member(i: int) -> dict:
    return {"guid": f"g{i}", "fullName": f"M{i}", "teamName": f"T{i}", "rank": i,
            "currentGamedayPoints": 40, "overallPoints": 100 - i}


class FakeClient:
    """Refuses `bad_id`; serves the table for `good_id` 2 rows a page."""

    def __init__(self, good_id: str, members: int, bad_id: str | None = None) -> None:
        self.good, self.bad, self.members = good_id, bad_id, members
        self.calls: list[tuple[str, int]] = []

    def get_league_standings(self, league_id: str, *, page: int = 1, **_: Any) -> dict:
        self.calls.append((league_id, page))
        if league_id != self.good:
            raise UefaAuthError("Not Authorized")
        rows = [member(i) for i in range(1, self.members + 1)][(page - 1) * 2: page * 2]
        return {"data": {"value": {"totalMembers": self.members, "rest": rows}}}

    def get_private_leagues(self, guid: str) -> dict:
        return {"data": {"value": [{"leagueId": int(self.good), "leagueName": "L",
                                    "leagueCode": "CODE42", "memberCount": self.members}]}}


def test_league_table_reads_every_page() -> None:
    client = FakeClient("7", members=5)
    entries, problem = pipeline._league_table(client, "7", matchday=2)  # type: ignore[arg-type]
    assert problem == "" and [e.entry_id for e in entries] == ["g1", "g2", "g3", "g4", "g5"]
    assert client.calls == [("7", 1), ("7", 2), ("7", 3)]


def test_league_table_reports_a_refusal() -> None:
    entries, problem = pipeline._league_table(FakeClient("7", 3), "8", matchday=2)  # type: ignore[arg-type]
    assert entries == [] and problem == "refused"


def test_stale_league_id_is_re_resolved_from_the_code() -> None:
    notes: list[str] = []
    found = pipeline._resolve_league_id(FakeClient("7", 3), "me", "code42", notes)  # type: ignore[arg-type]
    assert found == "7" and notes == []
    missing = pipeline._resolve_league_id(FakeClient("7", 3), "me", "NOPE", notes)  # type: ignore[arg-type]
    assert missing is None and "not found" in notes[0]
