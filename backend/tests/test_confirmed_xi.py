"""Confirmed XIs from UEFA's match centre: team sheets keyed by the same
player ids UEFA Fantasy uses."""

from types import SimpleNamespace

import httpx

from fantasy.leagues.ucl.sources.confirmed_xi import fetch_confirmed_xi, parse_lineups


def _side(start: range, bench: range) -> dict:
    return {
        "field": [{"player": {"id": str(i)}} for i in start],
        "bench": [{"player": {"id": str(i)}} for i in bench],
    }


def _sheet(status: str) -> dict:
    return {"lineupStatus": status,
            "homeTeam": _side(range(100, 111), range(111, 114)),
            "awayTeam": _side(range(200, 211), range(211, 213))}


def test_a_published_team_sheet_names_starters_and_bench() -> None:
    got = parse_lineups(_sheet("TACTICAL_AVAILABLE"))
    assert sum(1 for v in got.values() if v == "start") == 22
    assert got[100] == "start" and got[111] == "bench" and got[212] == "bench"


def test_nothing_before_the_team_sheets_are_out() -> None:
    assert parse_lineups(_sheet("NOT_AVAILABLE")) == {}
    short = _sheet("TACTICAL_AVAILABLE")
    short["awayTeam"]["field"] = short["awayTeam"]["field"][:3]  # not a full XI
    assert set(parse_lineups(short)) == set(range(100, 114))


def test_fetches_each_match_and_skips_one_that_fails() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        mid = req.url.path.split("/")[-2]
        if mid == "1":
            return httpx.Response(200, json=_sheet("TACTICAL_AVAILABLE"))
        if mid == "2":
            return httpx.Response(200, json=_sheet("NOT_AVAILABLE"))
        return httpx.Response(503)

    fixtures = [SimpleNamespace(uefa_match_id=i) for i in (1, 2, 3)]
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        got = fetch_confirmed_xi(fixtures, client=c, log=lambda _m: None)
    assert len(got) == 27 and got[200] == "start"
