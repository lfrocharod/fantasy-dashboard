from fantasy_ingest.ucl import fetch

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
