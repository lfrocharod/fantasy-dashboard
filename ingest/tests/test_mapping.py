from fantasy_ingest.mapping.player_match import build_stats
from fantasy_ingest.sources.domestic_xg import SourceRow, normalise
from fantasy_ingest.types import Player


def _src(name, team, **kw):
    d = {
        "minutes": 1500, "matches": 17, "npxg90": 0.5, "xag90": 0.3, "shots90": 2.5,
        "sca90": 3.0, "recoveries90": 5.0, "save_pct": 0.0, "source": "fbref",
    }
    d.update(kw)
    return SourceRow(name=name, norm_name=normalise(name), team=team, norm_team=normalise(team), **d)


def test_matches_on_fuzzy_name_and_team():
    players = [
        Player(uefa_player_id=1, name="Erling Haaland", team_id=10, position="FWD"),
        Player(uefa_player_id=2, name="Unknown Guy", team_id=10, position="MID"),
    ]
    team_names = {10: "Manchester City"}
    fbref = [
        _src("Erling Haaland", "Manchester City", npxg90=1.1),
        _src("Some Defender", "Arsenal"),
    ]
    report = build_stats(players, team_names, fbref, [], overrides=None)
    assert 1 in report.matched
    assert report.matched[1].npxg90 == 1.1
    assert (2, "Unknown Guy", "Manchester City") in report.unmatched


def test_override_forces_a_match():
    players = [Player(uefa_player_id=7, name="Vini Jr", team_id=5, position="FWD")]
    team_names = {5: "Real Madrid"}
    fbref = [_src("Vinicius Junior", "Real Madrid", npxg90=0.7)]
    # Without override the surname differs enough that we still expect a hit here,
    # but the override guarantees it and pins the exact source row.
    report = build_stats(
        players, team_names, fbref, [], overrides={7: ("Vinicius Junior", "Real Madrid")}
    )
    assert 7 in report.matched
    assert report.matched[7].npxg90 == 0.7
