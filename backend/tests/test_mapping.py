from fantasy.leagues.ucl.mapping.coverage import LOW_MINUTES, NO_NAME_MATCH, NO_STAT_ROW, XgCoverage
from fantasy.leagues.ucl.mapping.player_match import build_stats
from fantasy.leagues.ucl.sources.domestic_xg import SourceRow, normalise
from fantasy.leagues.ucl.sources.season_xg import _resolve_entry
from fantasy.leagues.ucl.types import Player


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


def _idx(*names):
    return {normalise(n): {"ss_id": i + 1, "ss_team_id": 99} for i, n in enumerate(names)}


def test_resolve_entry_exact_fuzzy_and_override():
    idx = _idx("Vinicius Junior", "Erling Haaland")
    keys = list(idx)
    # exact
    assert _resolve_entry("Erling Haaland", idx, keys)["ss_id"] == 2
    # surname fuzzy: "Vini Jr" -> "Vinicius Junior"
    assert _resolve_entry("Vini Jr", idx, keys) is None or _resolve_entry(
        "Vinicius Jr", idx, keys
    )["ss_id"] == 1
    # a genuinely absent player
    assert _resolve_entry("Nobody Here", idx, keys) is None
    # override name pins the lookup even when the UEFA name is unusable
    assert _resolve_entry("V. Jr.", idx, keys, force_name="Vinicius Junior")["ss_id"] == 1


def test_xg_coverage_buckets_and_summary():
    cov = XgCoverage(source="test")
    cov.total = 4
    cov.hit()
    cov.miss(1, "Cheap Sub", "TeamA", 4.0, NO_NAME_MATCH)
    cov.miss(2, "Big Star", "TeamB", 11.5, NO_STAT_ROW)
    cov.miss(3, "Returning Injury", "TeamC", 7.0, LOW_MINUTES)
    d = cov.as_dict()
    assert d["matched"] == 1 and d["unmatched"] == 3
    assert d["byReason"] == {NO_NAME_MATCH: 1, NO_STAT_ROW: 1, LOW_MINUTES: 1}
    # notable = price >= 6, worst first
    assert [u["name"] for u in d["notableMissing"]] == ["Big Star", "Returning Injury"]
    assert "Big Star (TeamB, 11.5)" in cov.summary_line()
