from fantasy.leagues.ucl.sources.confirmed_xi import _index_players, _pick_event, _resolve
from fantasy.leagues.ucl.types import Player


def _p(pid, name, team_id=10):
    return Player(uefa_player_id=pid, name=name, team_id=team_id, position="MID", price=5.0)


def test_resolve_exact_and_surname_and_shared_surname():
    players = [
        _p(1, "Lamine Yamal"),
        _p(2, "Pedri González"),
        _p(3, "Gavi"),
        _p(4, "Marc Bernal"),
        _p(5, "Ronald Araújo"),
    ]
    idx = _index_players(players, 10)
    assert _resolve(idx, "Pedri González").uefa_player_id == 2
    assert _resolve(idx, "L. Yamal").uefa_player_id == 1          # surname-only
    assert _resolve(idx, "Gavi").uefa_player_id == 3               # mononym
    assert _resolve(idx, "Nobody Here") is None


def test_resolve_disambiguates_shared_surname_by_first_initial():
    players = [_p(1, "Thiago Silva"), _p(2, "André Silva")]
    idx = _index_players(players, 10)
    assert _resolve(idx, "A. Silva").uefa_player_id == 2
    assert _resolve(idx, "T. Silva").uefa_player_id == 1


def test_pick_event_matches_opponent_and_rejects_wrong_competition():
    events = [
        {"id": 1, "homeTeam": {"id": 99}, "awayTeam": {"id": 42},
         "tournament": {"uniqueTournament": {"id": 8}}},   # domestic — reject
        {"id": 2, "homeTeam": {"id": 99}, "awayTeam": {"id": 42},
         "tournament": {"uniqueTournament": {"id": 7}}},   # UCL — take it
    ]
    assert _pick_event(events, 42, None)["id"] == 2
    assert _pick_event(events, 77, None) is None
