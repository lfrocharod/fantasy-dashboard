from fantasy.leagues.ucl import fetch

PLAYERS = {
    "data": {"value": {"playerList": [
        {"id": "250103758", "pDName": "E. Haaland", "latinName": "Erling Haaland",
         "skill": 4, "tId": "52919", "tName": "Man City", "cCode": "MCI",
         "value": 11.0, "totPts": 55, "avgPlayerPts": 6.1, "selPer": 20.0,
         "isActive": 1, "pStatus": "", "qStatus": ""},
        {"id": "250088320", "latinName": "Test Keeper", "skill": 1, "tId": "52747",
         "tName": "Arsenal", "cCode": "ARS", "value": 6.0, "totPts": 30,
         "avgPlayerPts": 3.0, "selPer": 5.0, "isActive": 1, "pStatus": "1"},
        {"id": "9", "latinName": "Injured Guy", "skill": 3, "tId": "52919",
         "value": 5.0, "isActive": 0},
    ]}},
    "meta": {"success": True},
}

TEAMS = {"data": {"value": [
    {"id": 52919, "webName": "Man City", "offName": "Manchester City", "shortName": "MCI", "countryCode": "MCI"},
    {"id": 63405, "webName": "LASK", "shortName": "LASK", "countryCode": "LASK"},
]}}

FIXTURES = {"data": {"value": [
    {"mdId": 1, "phId": 1, "deadline": "09/08/26 06:45:00 PM", "mdIsCurrent": 1,
     "match": [
        {"mId": 2049558, "gdId": "1", "dateTime": "09/08/2026 18:45:00",
         "htId": 52919, "htName": "Man City", "htCCode": "MCI",
         "atId": 63405, "atName": "LASK", "atCCode": "LASK",
         "matchStatus": "0", "htScore": "", "atScore": ""},
     ]},
    {"mdId": 2, "phId": 1, "deadline": "09/30/26 06:45:00 PM", "mdIsCurrent": 0, "match": []},
]}}

MY_TEAM = {"data": {"value": {
    "mdid": 1, "teamValue": 100.0, "teamBalance": 2.5, "substitutionsAllowed": 2,
    "playerid": [
        {"id": 250103758, "benchposition": 0, "teamid": 52919, "value": 11.0, "skill": 4, "iscaptain": 1},
        {"id": 250088320, "benchposition": 1, "teamid": 52747, "value": 6.0, "skill": 1, "iscaptain": 0},
    ],
}}}

PRIVATE = {"data": {"value": [
    {"leagueId": 9911, "leagueName": "Demo League", "leagueCode": "DEMO42", "memberCount": 4},
]}}

STANDINGS = {"data": {"value": [
    {"guid": "g-me", "fullName": "Me", "teamName": "My XI", "rank": 1, "previousRank": 2,
     "gdPoints": 55, "overallPoints": 410},
    {"guid": "g-riv", "fullName": "Riv", "teamName": "Rivals", "rank": 2, "previousRank": 1,
     "gdPoints": 40, "overallPoints": 402},
]}}


def test_parse_players():
    players, teams = fetch.parse_players(PLAYERS)
    assert {p.uefa_player_id for p in players} == {250103758, 250088320, 9}
    hal = next(p for p in players if p.uefa_player_id == 250103758)
    assert hal.position == "FWD" and hal.price == 11.0 and hal.status_code == 0
    # avgPlayerPts 6.1 regressed toward the FWD/€11m price prior (6.55): 0.35/0.65 blend
    assert hal.uefa_form == 6.39
    gk = next(p for p in players if p.uefa_player_id == 250088320)
    assert gk.position == "GK" and gk.status_code == 1  # pStatus "1" -> doubt
    inj = next(p for p in players if p.uefa_player_id == 9)
    assert inj.status_code == 2  # isActive 0 -> out
    assert teams[52919].name == "Man City"


def test_minutes_prior_from_uefa_minutes():
    feed = {"data": {"value": {"playerList": [
        {"id": "1", "latinName": "Everpresent", "skill": 3, "tId": "10", "tName": "A",
         "value": 8.0, "isActive": 1, "minsPlyd": 1200},
        {"id": "2", "latinName": "Rotation", "skill": 3, "tId": "10", "tName": "A",
         "value": 6.0, "isActive": 1, "minsPlyd": 1150},
        {"id": "3", "latinName": "Regular", "skill": 3, "tId": "10", "tName": "A",
         "value": 6.0, "isActive": 1, "minsPlyd": 1100},
        {"id": "4", "latinName": "Fringe", "skill": 3, "tId": "10", "tName": "A",
         "value": 4.5, "isActive": 1, "minsPlyd": 300},
        {"id": "5", "latinName": "Newbie", "skill": 3, "tId": "10", "tName": "A",
         "value": 4.0, "isActive": 1, "minsPlyd": 0},
    ]}}, "meta": {"success": True}}
    players, _ = fetch.parse_players(feed)
    by = {p.name: p for p in players}
    # club reference = 3rd-highest total (1100), floored at 900
    assert by["Everpresent"].minutes_prior == 1.0  # 1200/1100 capped
    assert by["Regular"].minutes_prior == 1.0
    assert 0.25 < by["Fringe"].minutes_prior < 0.32  # 300/1100
    assert by["Newbie"].minutes_prior == 0.0  # no data -> model falls back


def test_parse_teams():
    teams = fetch.parse_teams(TEAMS)
    assert teams[52919].name == "Man City"
    assert teams[63405].code == "LASK"


def test_parse_fixtures():
    fixtures, teams, md_info = fetch.parse_fixtures(FIXTURES)
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.uefa_match_id == 2049558 and f.matchday == 1
    assert f.home_team_id == 52919 and f.away_team_id == 63405
    assert f.status == "upcoming" and f.kickoff is not None
    # feed says "18:45" (Zurich wall-clock, CEST = UTC+2 in September) -> 16:45 UTC
    assert f.kickoff.utcoffset().total_seconds() == 0
    assert (f.kickoff.hour, f.kickoff.minute) == (16, 45)
    assert teams[52919].name == "Man City"
    assert md_info[0].is_current and md_info[0].deadline is not None
    assert md_info[0].deadline.hour == 16  # "06:45 PM" Zurich -> 16:45 UTC
    assert fetch.current_matchday(md_info) == 1


def test_parse_my_team():
    picks, bank = fetch.parse_my_team(MY_TEAM, matchday=1)
    assert bank == 2.5
    assert len(picks) == 2
    cap = next(p for p in picks if p.player_id == 250103758)
    assert cap.is_captain and cap.is_starter
    sub = next(p for p in picks if p.player_id == 250088320)
    assert not sub.is_starter and sub.bench_order == 1


def test_parse_private_leagues():
    leagues = fetch.parse_private_leagues(PRIVATE)
    assert leagues == [{"id": "9911", "name": "Demo League", "code": "DEMO42", "memberCount": 4}]


def test_parse_league_standings():
    entries = fetch.parse_league_standings(STANDINGS, matchday=3)
    assert [e.entry_id for e in entries] == ["g-me", "g-riv"]
    me = entries[0]
    assert me.points == 55 and me.total_points == 410 and me.rank == 1 and me.prev_rank == 2


def test_unwrap_list_backcompat():
    assert fetch.unwrap_list(PLAYERS, ("value", "playerList")) == PLAYERS["data"]["value"]["playerList"]


def test_md_is_current_is_tri_state():
    # UEFA: 2 = played, 1 = the open matchday, 0 = future. Only 1 is current.
    feed = {"data": {"value": [
        {"mdId": 1, "mdIsCurrent": 2, "deadline": "09/10/26 06:45:00 PM", "match": []},
        {"mdId": 2, "mdIsCurrent": 1, "deadline": "10/13/26 06:45:00 PM", "match": []},
        {"mdId": 3, "mdIsCurrent": 0, "deadline": "10/20/26 06:45:00 PM", "match": []},
    ]}}
    _, _, md_info = fetch.parse_fixtures(feed)
    assert [m.is_current for m in md_info] == [False, True, False]
    assert fetch.current_matchday(md_info) == 2


LEADERBOARD = {"data": {"value": {
    "totalMembers": 3,
    "initial": [
        {"guid": "me", "fullName": "You", "teamName": "Demo XI", "rank": 2, "trend": 2,
         "currentGamedayPoints": 51, "overallPoints": 120},
    ],
    "rest": [
        {"guid": "me", "fullName": "You", "teamName": "Demo XI", "rank": 2, "trend": 2,
         "currentGamedayPoints": 51, "overallPoints": 120},
        {"guid": "r1", "fullName": "Rival One", "teamName": "FC Rival", "rank": 1, "trend": 1,
         "currentGamedayPoints": 44, "overallPoints": 131},
        {"guid": "r2", "fullName": "Rival Two", "teamName": "Two Utd", "rank": 3, "trend": 3,
         "currentGamedayPoints": 38, "overallPoints": 102},
    ],
}}, "meta": {"success": True}}


def test_league_rows_merge_initial_and_rest():
    rows, total = fetch.league_rows(LEADERBOARD)
    assert [r["guid"] for r in rows] == ["me", "r1", "r2"] and total == 3
    entries = fetch.parse_league_standings(rows, matchday=2)
    me = next(e for e in entries if e.entry_id == "me")
    assert (me.points, me.total_points, me.rank) == (51, 120, 2)


def test_league_rows_still_read_a_plain_list():
    rows, total = fetch.league_rows(STANDINGS)
    assert len(rows) == len(fetch.parse_league_standings(STANDINGS, matchday=3)) and total is None


def test_league_standings_request_matches_the_site():
    """The overall table: matchday 0 and phase 0, as UEFA's own site asks."""
    import httpx

    from fantasy.leagues.ucl.client import UefaClient

    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=LEADERBOARD)

    with UefaClient(token="a=b", transport=httpx.MockTransport(handler)) as c:
        c.get_league_standings("123")
    q = dict(seen[0].params)
    assert seen[0].path.endswith("/Leagues/123/leagueleaderboard")
    assert (q["matchdayId"], q["phaseId"], q["optType"], q["leagueID"]) == ("0", "0", "1", "123")


def test_a_scored_matchday_carries_uefas_own_numbers() -> None:
    """After a matchday the squad payload holds UEFA's result: the score, each
    pick's points (the captain's doubled), and the changes made in play."""
    payload = {"data": {"value": {
        "gdPoints": 83.0, "mdSubstitutions": 4,
        "playerid": [
            {"id": 1, "benchposition": 0, "iscaptain": 1, "overallpoints": 20.0,
             "autosubflag": 0, "capchgflag": 2},
            {"id": 2, "benchposition": 0, "iscaptain": 0, "overallpoints": -1.0,
             "autosubflag": 0, "capchgflag": 1},
            {"id": 3, "benchposition": 0, "iscaptain": 0, "overallpoints": 12.0, "autosubflag": 1},
            {"id": 4, "benchposition": 2, "iscaptain": 0, "overallpoints": 0.0, "autosubflag": 2},
        ],
    }}}
    picks, _bank = fetch.parse_my_team(payload, matchday=2)
    by_id = {p.player_id: p for p in picks}
    assert by_id[1].points == 20.0 and by_id[1].cap_flag == 2
    assert (by_id[3].sub_flag, by_id[4].sub_flag) == (1, 2)
    sheet = fetch.parse_team_sheet(payload)
    assert (sheet.points, sheet.in_play_subs, sheet.captain_moved, sheet.changed) == (83.0, 4, True, True)
    upcoming = fetch.parse_team_sheet({"data": {"value": {"gdPoints": None, "mdSubstitutions": 0,
                                                          "playerid": [{"id": 1, "capchgflag": 0}]}}})
    assert upcoming.points is None and not upcoming.changed
