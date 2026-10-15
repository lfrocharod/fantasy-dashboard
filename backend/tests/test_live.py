from datetime import UTC, datetime

from fantasy.leagues.ucl.model.live import build_live_rivals, build_live_state
from fantasy.leagues.ucl.types import (
    Fixture,
    LeagueEntry,
    Player,
    Projection,
    SquadPick,
    Team,
    TeamSheet,
)

# 6 clubs: 1&2 play "day 1" (finished), 3&4 "day 1" (finished), 5&6 "day 2" (upcoming)
TEAMS = {i: Team(uefa_team_id=i, name=f"C{i}", code=f"C{i}") for i in range(1, 7)}

_D1 = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
_D2 = datetime(2026, 9, 9, 19, 0, tzinfo=UTC)


def _fx(status_15, status_36, status_56):
    return [
        Fixture(uefa_match_id=1, matchday=1, home_team_id=1, away_team_id=2,
                kickoff=_D1, status=status_15),
        Fixture(uefa_match_id=2, matchday=1, home_team_id=3, away_team_id=4,
                kickoff=_D1, status=status_36),
        Fixture(uefa_match_id=3, matchday=1, home_team_id=5, away_team_id=6,
                kickoff=_D2, status=status_56),
    ]


def _squad_players():
    # 1 GK + 5 DEF + 5 MID + 3 FWD across the 6 clubs
    plan = [("GK", 1), ("DEF", 1), ("DEF", 2), ("DEF", 3), ("MID", 1), ("MID", 2),
            ("MID", 3), ("MID", 4), ("FWD", 1), ("FWD", 2), ("FWD", 5),   # XI
            ("GK", 3), ("DEF", 4), ("MID", 6), ("FWD", 6)]                # bench
    out = []
    for i, (pos, club) in enumerate(plan, start=10):
        out.append(Player(uefa_player_id=i, name=f"P{i}", team_id=club, position=pos))
    return out


def _picks(players):
    picks = []
    for idx, p in enumerate(players):
        starter = idx < 11
        picks.append(SquadPick(player_id=p.uefa_player_id, is_starter=starter,
                               is_captain=(idx == 8), is_vice=(idx == 4),
                               bench_order=0 if starter else idx - 10))
    return picks


def _proj(players, xpts=4.0):
    return [Projection(player_id=p.uefa_player_id, matchday=1, p_start=0.9,
                       exp_minutes=80, xpts=xpts, xpts_captain=xpts * 2, value=1.0,
                       xpts_high=xpts + 3, xpts_low=xpts - 2, components={})
            for p in players]


def test_none_until_a_game_kicks_off():
    players = _squad_players()
    out = build_live_state(players, TEAMS, _fx("upcoming", "upcoming", "upcoming"),
                           _proj(players), _picks(players), 1)
    assert out is None


def test_secured_and_projected_points_with_captain_double():
    players = _squad_players()
    # matches for clubs 1-4 are finished, clubs 5-6 upcoming. 10 of the XI are in
    # clubs 1-4 (all bar the FWD5 at club 5); the captain (idx 8) is a club-1 FWD.
    for p in players[:11]:
        if p.team_id <= 4:
            p.live_points, p.live_played = 5, True
    picks = _picks(players)
    fx = _fx("finished", "finished", "upcoming")
    out = build_live_state(players, TEAMS, fx, _proj(players, xpts=4.0), picks, 1)
    assert out["state"] == "live"
    assert out["played"] == 10
    assert out["toPlay"] == 1
    # secured: 10 finished starters * 5  + captain double (finished, 5)
    assert out["securedPoints"] == 55.0
    # projected: 50 finished + 1 upcoming xpts (4) + captain double (5)
    assert out["projectedFinish"] == 59.0


def test_auto_sub_replaces_a_did_not_play_starter():
    players = _squad_players()
    for p in players:
        p.live_points, p.live_played = 3, True
    # starter P13 (index 3, DEF club 3) did NOT play; its game is finished
    dnp = next(p for p in players if p.uefa_player_id == 13)
    dnp.live_points, dnp.live_played = 0, False
    fx = _fx("finished", "finished", "finished")
    out = build_live_state(players, TEAMS, fx, _proj(players), _picks(players), 1)
    assert out["state"] == "finished"
    assert len(out["autoSubs"]) == 1
    assert out["autoSubs"][0]["outName"] == "P13"
    # the bench DEF (P22) is the only formation-legal cover
    assert out["autoSubs"][0]["inName"] == "P22"
    roles = {r["name"]: r["effRole"] for r in out["squad"]}
    assert roles["P13"] == "auto-out" and roles["P22"] == "auto-in"


def test_captain_switch_suggested_when_captain_has_not_kicked_off():
    players = _squad_players()
    proj = _proj(players, xpts=3.0)
    # captain is idx 8 (a club-1 FWD). Boost a club-5/6 XI player (not started).
    ids = [p.uefa_player_id for p in players]
    hi_pid = ids[10]  # FWD5 at club 5 — its match is 'upcoming'
    for pr in proj:
        if pr.player_id == hi_pid:
            pr.xpts = 9.0
    # clubs 1-4 finished, 5-6 upcoming
    fx = _fx("finished", "finished", "upcoming")
    for p in players[:11]:
        if p.team_id <= 4:
            p.live_points, p.live_played = 2, True
    # make the captain's club upcoming so a switch is legal
    cap_p = next(p for p in players if p.uefa_player_id == ids[8])
    cap_p.team_id = 5
    out = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)
    sw = out["captain"]["switch"]
    assert sw and sw["toXpts"] == 9.0 and sw["gain"] > 0
    assert out["captain"]["locked"] is False
    assert out["captain"]["recommendation"] == "switch"
    assert "CHANGE the (C)" in out["captain"]["note"]


def test_captain_locked_once_they_have_played():
    players = _squad_players()
    for p in players:
        p.live_points, p.live_played = 4, True
    fx = _fx("finished", "finished", "finished")
    out = build_live_state(players, TEAMS, fx, _proj(players), _picks(players), 1)
    assert out["captain"]["locked"] is True
    assert out["captain"]["switch"] is None
    assert "×2" in out["captain"]["note"]


def test_armband_can_move_off_a_played_captain_to_a_later_game():
    # (C) played on day 1 and banked 4; a day-2 XI player projects 9 -> switching
    # keeps the 4 as base and doubles the 9 instead (+5).
    players = _squad_players()
    proj = _proj(players, xpts=3.0)
    ids = [p.uefa_player_id for p in players]
    for pr in proj:
        if pr.player_id == ids[10]:  # FWD5 @ club 5, day 2, still upcoming
            pr.xpts = 9.0
    fx = _fx("finished", "finished", "upcoming")
    for p in players[:11]:
        if p.team_id <= 4:
            p.live_points, p.live_played = 4, True  # captain (club 1) banked 4
    cap = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)["captain"]
    assert cap["locked"] is False
    assert cap["recommendation"] == "switch"
    assert cap["switch"]["toXpts"] == 9.0 and cap["switch"]["gain"] == 5.0
    assert "keeps 4 as base" in cap["note"]


def test_keep_the_played_captain_when_the_haul_beats_the_later_option():
    players = _squad_players()
    proj = _proj(players, xpts=3.0)  # the only day-2 XI player projects just 3
    fx = _fx("finished", "finished", "upcoming")
    for p in players[:11]:
        if p.team_id <= 4:
            p.live_points, p.live_played = 12, True  # captain hauled
    cap = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)["captain"]
    assert cap["recommendation"] == "keep"
    assert cap["switch"] is None
    assert "already beats" in cap["note"]


def test_captain_blank_loses_the_double_no_vice():
    # UCL Fantasy 2025/26 has no vice-captain: a blanked (C) that wasn't moved
    # before kick-off just forfeits the double — nobody inherits it.
    players = _squad_players()
    for p in players:
        p.live_points, p.live_played = 2, True
    cap = next(p for p in players if p.uefa_player_id == 18)  # index 8, captain
    cap.live_points, cap.live_played = 0, False
    fx = _fx("finished", "finished", "finished")
    out = build_live_state(players, TEAMS, fx, _proj(players), _picks(players), 1)
    assert out["captain"]["effectiveName"] is None
    assert out["captain"]["recommendation"] == "locked"
    assert "no captain double" in out["captain"]["note"]
    # 11 effective starters * 2 pts, and no doubled contribution from anyone
    assert out["securedPoints"] == 22.0
    assert out["projectedFinish"] == 22.0


def test_manual_sub_flagged_for_a_yet_to_play_starter():
    # day-1 games done; the club-5/6 game is still to come, so a weak day-2
    # starter can be swapped for a stronger day-2 bench player.
    players = _squad_players()
    for p in players[:11]:
        if p.team_id <= 4:
            p.live_points, p.live_played = 6, True
    proj = _proj(players, xpts=5.0)
    for pr in proj:
        if pr.player_id == 23:      # bench MID at club 6 — hasn't kicked off
            pr.xpts = 9.0
    fx = _fx("finished", "finished", "upcoming")
    out = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)
    assert any(s["outName"] == "P20" and s["inName"] == "P23"
               for s in out["manualSubs"])
    assert out["maxManualSubs"] == 4
    assert out["inPlayOpen"] is True


def test_no_manual_subs_or_captain_move_on_single_slot_matchday():
    players = _squad_players()
    for p in players[:11]:
        p.live_points, p.live_played = 3, True
    proj = _proj(players, xpts=5.0)
    for pr in proj:
        if pr.player_id == 23:
            pr.xpts = 9.0
    # every game the same day -> no between-day window
    fx = _fx("live", "upcoming", "upcoming")
    for f in fx:
        f.kickoff = _D1
    out = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)
    assert out["inPlayOpen"] is False
    assert out["manualSubs"] == []
    assert out["captain"]["recommendation"] == "locked"
    assert out["captain"]["switch"] is None


def test_live_rivals_ranks_by_projection_and_uses_my_live_row():
    players = _squad_players()
    for p in players:
        p.live_points, p.live_played = 4, True
    proj = _proj(players, xpts=3.0)
    scores = {p.uefa_player_id: (4, True, True) for p in players}
    ids = [p.uefa_player_id for p in players]
    ents = [
        LeagueEntry(entry_id="me", manager_name="Me", team_name="X", matchday=1,
                    points=0, total_points=100, rank=2, prev_rank=2),
        LeagueEntry(entry_id="riv", manager_name="Riv", team_name="Y", matchday=1,
                    points=0, total_points=99, rank=1, prev_rank=1),
    ]
    ents[0].squad = [{"id": i, "s": idx < 11, "c": idx == 8} for idx, i in enumerate(ids)]
    ents[1].squad = [{"id": i, "s": idx < 11, "c": idx == 0} for idx, i in enumerate(ids)]
    my_live = {"securedPoints": 77.0, "projectedFinish": 77.0, "played": 11}
    out = build_live_rivals(ents, "me", players, TEAMS, proj, scores, 1, my_live=my_live)
    assert out["ready"] and out["myEntryId"] == "me"
    mine = next(r for r in out["rows"] if r["mine"])
    assert mine["projected"] == 77.0                 # taken from my_live, not recomputed
    assert out["rows"][0]["mine"]                     # sorted desc by projection -> I'm on top
    assert all("liveGapVsMe" in r for r in out["rows"])


def test_a_published_team_sheet_revalues_a_player_still_to_play():
    """Projections freeze at the first kickoff; a later team sheet benching
    a day-2 starter still reaches the live advice through the re-projection."""
    players = _squad_players()
    for p in players:
        if p.team_id <= 4:
            p.live_points, p.live_played = 2, True
    fwd5 = next(p for p in players if p.team_id == 5 and p.position == "FWD")
    bench_fwd = next(p for p in players if p.team_id == 6 and p.position == "FWD")
    fresh = _proj(players, xpts=4.0)
    for pr in fresh:
        if pr.player_id == fwd5.uefa_player_id:
            pr.xpts = 0.4  # confirmed on the bench
    out = build_live_state(players, TEAMS, _fx("finished", "finished", "upcoming"),
                           _proj(players, xpts=4.0), _picks(players), 1,
                           confirmed={fwd5.uefa_player_id: "bench",
                                      bench_fwd.uefa_player_id: "start"},
                           reprojected=fresh)
    row = next(r for r in out["squad"] if r["playerId"] == fwd5.uefa_player_id)
    assert row["confirmed"] == "bench" and row["xpts"] == 0.4
    assert out["preMatchProjection"] == 11 * 4.0 + 4.0  # still the frozen numbers
    assert [s["outName"] for s in out["manualSubs"]] == [fwd5.name]


# ---- UEFA's in-play rules --------------------------------------------------------------


def _day_one_done(dnp_index: int):
    """Clubs 1-4 have played (2 points each), 5-6 are still to play; one
    starter at a club that played never featured."""
    players = _squad_players()
    for p in players:
        if p.team_id <= 4:
            p.live_points, p.live_played = 2, True
    players[dnp_index].live_points, players[dnp_index].live_played = 0, False
    return players


def test_no_auto_subs_once_the_team_was_changed_in_play():
    players = _day_one_done(1)  # a club-1 defender
    fx = _fx("finished", "finished", "upcoming")
    untouched = build_live_state(players, TEAMS, fx, _proj(players), _picks(players), 1)
    assert [s["outName"] for s in untouched["autoSubs"]] == [players[1].name]
    changed = build_live_state(players, TEAMS, fx, _proj(players), _picks(players), 1,
                               sheet=TeamSheet(in_play_subs=1))
    assert changed["autoSubs"] == [] and changed["autoSubsOff"] and changed["inPlaySubs"] == 1
    assert changed["projectedFinish"] < untouched["projectedFinish"]  # the defender stays on 0


def test_a_manual_sub_has_to_beat_the_auto_sub_it_switches_off():
    """The defender's auto-sub brings in a bench defender who already scored 2;
    any manual change gives those up, so a +2.5 sub isn't worth making."""
    players = _day_one_done(1)
    fx = _fx("finished", "finished", "upcoming")
    proj = _proj(players, xpts=4.0)
    bench_fwd = next(pr for pr in proj if pr.player_id == players[14].uefa_player_id)
    bench_fwd.xpts = 6.5  # +2.5 over the club-5 forward still to play
    out = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)
    assert out["manualSubs"] == []
    bench_fwd.xpts = 8.0  # +4.0: worth it even net of the 2
    out = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)
    assert [(s["outName"], s["inName"]) for s in out["manualSubs"]] == [(players[10].name, players[14].name)]


def test_an_auto_sub_that_can_be_redone_by_hand_is_listed_first():
    players = _day_one_done(4)  # a club-1 midfielder
    players[11].live_points = players[12].live_points = 0  # the bench GK and DEF didn't play
    players[11].live_played = players[12].live_played = False
    fx = _fx("finished", "finished", "upcoming")
    proj = _proj(players, xpts=4.0)
    next(pr for pr in proj if pr.player_id == players[14].uefa_player_id).xpts = 8.0
    out = build_live_state(players, TEAMS, fx, proj, _picks(players), 1)
    redo, sub = out["manualSubs"]
    assert (redo["outName"], redo["inName"]) == (players[4].name, players[13].name)
    assert "auto-sub" in redo["reason"]
    assert (sub["outName"], sub["inName"]) == (players[10].name, players[14].name)


def test_uefas_settled_result_stands_in_for_the_live_one():
    players = _squad_players()
    for p in players:
        p.live_points, p.live_played = 2, True
    picks = _picks(players)
    for pk in picks:
        pk.points = 4.0 if pk.is_captain else 2.0  # UEFA doubles the captain itself
    picks[0].points = 5.0  # a Player of the Match bonus the live feed never had
    out = build_live_state(players, TEAMS, _fx("finished", "finished", "finished"),
                           _proj(players), picks, 1, sheet=TeamSheet(points=27.0))
    assert out["official"] == out["securedPoints"] == out["projectedFinish"] == 27.0
    rows = {r["playerId"]: r for r in out["squad"]}
    assert rows[picks[0].player_id]["actual"] == 5.0
    assert rows[picks[8].player_id]["actual"] == 2.0  # the captain: the page doubles it


def test_rivals_get_auto_subs_and_no_double_for_a_captain_out_of_the_xi():
    players = _squad_players()
    scores = {p.uefa_player_id: (2, True, True) for p in players}
    dnp = players[8].uefa_player_id  # their captain, a club-1 forward, never featured
    scores[dnp] = (0, False, True)
    squad = [{"id": p.uefa_player_id, "c": i == 8, "s": i < 11, "b": 0 if i < 11 else i - 10}
             for i, p in enumerate(players)]
    rival = LeagueEntry(entry_id="r1", manager_name="Rival", team_name="R", matchday=1,
                        points=0, total_points=0, rank=2, squad=squad)
    out = build_live_rivals([rival], "me", players, TEAMS, _proj(players), scores, 1)
    row = out["rows"][0]
    # ten starters on 2, plus the first bench player who keeps the formation
    # legal (a defender) on for him, and no captain double
    assert row["secured"] == 22.0 and not row["official"]
    settled_squad = [{**x, "p": 3.0} for x in squad]
    rival.squad = settled_squad
    out = build_live_rivals([rival], "me", players, TEAMS, _proj(players), scores, 1, settled=True)
    assert out["rows"][0]["secured"] == 33.0 and out["rows"][0]["official"]
