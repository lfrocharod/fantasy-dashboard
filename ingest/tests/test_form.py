from fantasy_ingest.mapping.form_match import build_player_form
from fantasy_ingest.sources.recent_form import FormRow, normalise
from fantasy_ingest.sources.understat_form import aggregate_match_rows
from fantasy_ingest.types import Player


def _fr(name, team, *, role="MID", matches=5, starts=5, minutes=None, source="sofascore"):
    return FormRow(
        name=name, norm_name=normalise(name), team=team, norm_team=normalise(team),
        role=role, recent_matches=matches, recent_starts=starts,
        recent_minutes=minutes if minutes is not None else 90.0 * matches,
        source=source,
    )


def _mr(player, team, date, minutes, pos, g=0, a=0, npxg=0.0, xa=0.0, shots=0):
    return {"player": player, "team": team, "date": date, "minutes": minutes,
            "pos": pos, "goals": g, "assists": a, "npxg": npxg, "xa": xa, "shots": shots}


def test_aggregate_recent_window_and_role():
    recs = [
        _mr("Raphinha", "Barcelona", "2026-08-01", 90, "MC", g=0, npxg=0.2),  # old, dropped by window=4
        _mr("Raphinha", "Barcelona", "2026-08-08", 90, "FW", g=2, npxg=1.4, shots=6),
        _mr("Raphinha", "Barcelona", "2026-08-15", 90, "FW", g=1, npxg=0.9, shots=4),
        _mr("Raphinha", "Barcelona", "2026-08-22", 80, "FW", g=0, npxg=0.6, shots=3),
        _mr("Raphinha", "Barcelona", "2026-08-29", 90, "FW", g=2, npxg=1.5, shots=7),
    ]
    [fr] = aggregate_match_rows(recs, last_n=4)
    assert fr.recent_matches == 4
    assert fr.recent_starts == 4
    assert fr.recent_goals == 5
    assert fr.role == "FWD"  # last 4 all forward, ignores the old MC game


def test_build_player_form_flags_transfer_and_role():
    players = [
        Player(uefa_player_id=1, name="Raphinha", team_id=10, position="MID", price=9.5),
        Player(uefa_player_id=2, name="Gabriel Martinelli", team_id=20, position="MID", price=7.5),
        Player(uefa_player_id=3, name="Nobody Match", team_id=10, position="DEF", price=4.0),
    ]
    team_names = {10: "Barcelona", 20: "Arsenal"}
    recs = []
    for i in range(4):
        recs.append(_mr("Raphinha", "Barcelona", f"2026-08-1{i}", 90, "FW", g=1, npxg=1.0, shots=5))
        recs.append(_mr("Gabriel Martinelli", "Bayern Munich", f"2026-08-1{i}", 80, "AML", g=0, npxg=0.4))
    rows = aggregate_match_rows(recs, last_n=4)
    form, unmatched = build_player_form(players, team_names, rows)
    by_id = {f.player_id: f for f in form}

    assert by_id[1].team_ok is True
    assert by_id[1].role == "FWD"
    assert "playing FWD" in by_id[1].role_note
    assert by_id[1].start_prob > 0.8
    assert by_id[1].hot_score > 0

    assert by_id[2].team_ok is False  # Understat has them at Bayern, UEFA says Arsenal
    assert "Bayern" in by_id[2].role_note

    assert 3 in [pid for pid, _ in unmatched]


def test_one_to_one_youth_does_not_steal_starters_form_row():
    # A real starter and a cheap academy filler share a surname at the same club.
    # Only one Sofascore row exists (the starter's). Global assignment must give
    # it to the starter; the youth is left unmatched, not handed senior form.
    players = [
        Player(uefa_player_id=1, name="Dean Huijsen", team_id=10, position="DEF", price=6.0),
        Player(uefa_player_id=2, name="Huijsen", team_id=10, position="DEF", price=3.8,
               minutes_prior=0.0),
    ]
    team_names = {10: "Real Madrid"}
    rows = [_fr("Dean Huijsen", "Real Madrid", role="DEF")]
    form, unmatched = build_player_form(players, team_names, rows)
    by_id = {f.player_id: f for f in form}
    assert by_id[1].recent_starts == 5
    assert 2 in [pid for pid, _ in unmatched]


def test_fringe_filler_cannot_inherit_senior_sample_on_fuzzy_name():
    players = [
        Player(uefa_player_id=9, name="Karim Abdelghani", team_id=20, position="FWD",
               price=3.9, minutes_prior=0.0),
    ]
    team_names = {20: "Barcelona"}
    # a different first-teamer who shares the surname bucket and has real minutes
    rows = [_fr("Youssef Abdelghani", "Barcelona", role="FWD", starts=4, matches=4)]
    _form, unmatched = build_player_form(players, team_names, rows)
    assert 9 in [pid for pid, _ in unmatched]


def test_sofascore_row_preferred_over_understat_for_same_player():
    players = [Player(uefa_player_id=1, name="Pedri", team_id=10, position="MID", price=8.0)]
    team_names = {10: "Barcelona"}
    rows = [
        _fr("Pedri", "Barcelona", matches=3, starts=3, source="understat"),
        _fr("Pedri", "Barcelona", matches=5, starts=5, source="sofascore"),
    ]
    [pf] = build_player_form(players, team_names, rows)[0]
    assert pf.source == "sofascore"
    assert pf.recent_matches == 5
