from fantasy_ingest.mapping.form_match import build_player_form
from fantasy_ingest.sources.understat_form import aggregate_match_rows
from fantasy_ingest.types import Player


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
