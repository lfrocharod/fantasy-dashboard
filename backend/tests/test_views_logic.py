"""Unit tests for decision logic that used to live inline in the page
components: the league-phase strategy, the captaincy verdict, FPL auto-subs."""

from __future__ import annotations

from types import SimpleNamespace

from fantasy.api.schemas.ucl import CaptainAnalysis, CaptainCandidate, LeagueStrategy
from fantasy.leagues.fpl.players import FplPlayer
from fantasy.leagues.fpl.views import Board, live_view
from fantasy.leagues.ucl.views import captaincy_verdict, league_phase_strategy


def _st(entry: str, rank: int, total: int, name: str = "") -> SimpleNamespace:
    return SimpleNamespace(entry_id=entry, rank=rank, total_points=total, manager_name=name)


def test_strategy_modes() -> None:
    # MD7 of 8: 2 matchdays left -> ~28 points of realistic swing
    lead = [_st("me", 1, 300), _st("b", 2, 250)]
    assert league_phase_strategy(lead, "me", 7).mode == "protect"
    narrow = [_st("me", 1, 300), _st("b", 2, 290)]
    s = league_phase_strategy(narrow, "me", 7)
    assert s.mode == "hold" and s.captain == "match"
    chase = [_st("a", 1, 310, "Alex"), _st("me", 2, 300)]
    s = league_phase_strategy(chase, "me", 7)
    assert s.mode == "chase" and s.captain == "differential" and "Alex" in s.text
    gone = [_st("a", 1, 400), _st("me", 2, 300)]
    assert league_phase_strategy(gone, "me", 7).mode == "free"
    assert league_phase_strategy(gone, "nobody", 7) is None


def _cand(pid: int, ev: float, floor: float = 0, ceiling: float = 0) -> CaptainCandidate:
    return CaptainCandidate(player_id=pid, name=f"P{pid}", ev=ev, floor=floor, ceiling=ceiling)


def test_captaincy_keep_change_set() -> None:
    caps = CaptainAnalysis(
        candidates=[_cand(1, 12.0, 4, 20), _cand(2, 11.0, 7, 15), _cand(3, 10.0, 2, 24)],
        safe_pick=_cand(2, 11.0, 7, 15),
        differential_pick=_cand(3, 10.0, 2, 24),
    )
    squad = {1, 2, 3}
    best = LeagueStrategy(mode="free", text="", mds_left=3, captain="best")
    assert captaincy_verdict(caps, squad, 1, best).recommendation == "keep"
    v = captaincy_verdict(caps, squad, 3, best)
    assert v.recommendation == "change" and v.pick.player_id == 1  # +2.0 EV > 0.6 bar
    assert captaincy_verdict(caps, squad, None, best).recommendation == "set"
    safe = LeagueStrategy(mode="protect", text="", mds_left=3, captain="safe")
    assert captaincy_verdict(caps, squad, 1, safe).pick.player_id == 2
    chase = LeagueStrategy(mode="chase", text="", mds_left=3, captain="differential")
    assert captaincy_verdict(caps, squad, 1, chase).pick.player_id == 3
    # a captain the model didn't shortlist is still judged, not reported as "unset"
    outsider = _cand(9, 4.0)
    v = captaincy_verdict(caps, squad | {9}, 9, best, current_captain=outsider)
    assert v.recommendation == "change" and v.current.player_id == 9


def _fpl(ext: str, pos: str) -> FplPlayer:
    raw = {"gws": [{"gw": 8, "opp": "X (H)", "home": True, "fdr": 3, "xpts": 4.0, "cs": 0.3}]}
    row = SimpleNamespace(ext_id=ext, name=f"N{ext}", team="T", primary_pos=pos, proj_points=4.0,
                          provider_rank=100, vbd=0, injury_status="a", outlook="", raw=raw)
    return FplPlayer.from_row(row)


def test_fpl_live_auto_sub_respects_formation() -> None:
    xi = [("1", "GKP"), *((f"d{i}", "DEF") for i in range(3)), *((f"m{i}", "MID") for i in range(5)),
          ("f0", "FWD"), ("f1", "FWD")]
    bench = [("2", "GKP"), ("bf", "FWD"), ("bd", "DEF"), ("bm", "MID")]
    players = [_fpl(e, p) for e, p in xi + bench]
    lineup = [
        SimpleNamespace(ext_id=e, position=i, starter=i <= 11, source="my-team")
        for i, (e, _) in enumerate(xi + bench, start=1)
    ]
    board = Board(players=players, by_id={p.ext_id: p for p in players}, my_entry_id="1",
                  lineup=lineup, league=None, entries=[])  # type: ignore[arg-type]
    # a defender didn't play: with only 3 DEF the sub has to be the bench defender,
    # even though a forward sits ahead of him on the bench
    elements = {e: [2, 90] for e, _ in xi + bench}
    elements["d0"] = [0, 0]
    view = live_view({"gw": 8, "state": "finished", "secured": 30, "played": 10,
                      "starters": 11, "elements": elements}, board)
    assert view is not None
    assert [(s.out, s.in_) for s in view.auto_subs] == [("Nd0", "Nbd")]
    roles = {r.player.ext_id: r.role for r in view.rows}
    assert roles["d0"] == "auto-out" and roles["bd"] == "auto-in" and roles["bf"] == "bench"
    assert view.projected_finish == 2 * 11


def test_fpl_live_scores_the_lineup_the_gameweek_was_played_with() -> None:
    xi = [("1", "GKP"), *((f"d{i}", "DEF") for i in range(3)), *((f"m{i}", "MID") for i in range(5)),
          ("f0", "FWD"), ("f1", "FWD")]
    bench = [("2", "GKP"), ("bf", "FWD"), ("bd", "DEF"), ("bm", "MID")]
    players = [_fpl(e, p) for e, p in xi + bench]
    # the stored Pick Team is already next gameweek's: bf starts there, f1 sits
    pick_team = [e for e, _ in xi if e != "f1"] + ["bf", "2", "f1", "bd", "bm"]
    board = Board(
        players=players, by_id={p.ext_id: p for p in players}, my_entry_id="1",
        lineup=[SimpleNamespace(ext_id=e, position=i, starter=i <= 11, source="my-team")
                for i, e in enumerate(pick_team, start=1)],
        league=None, entries=[],
    )  # type: ignore[arg-type]
    elements = {e: [2, 90] for e, _ in xi + bench}
    elements["f1"] = [10, 90]
    played = [{"element": e, "slot": i, "starter": i <= 11}
              for i, (e, _) in enumerate(xi + bench, start=1)]
    doc = {"gw": 8, "state": "finished", "secured": 30, "played": 11, "starters": 11,
           "elements": elements, "lineup": played, "lineupSource": "event/8"}

    view = live_view(doc, board)
    assert view is not None
    roles = {r.player.ext_id: r.role for r in view.rows}
    assert roles["f1"] == "start" and roles["bf"] == "bench"
    assert view.secured == 30 and not view.estimated
    # scored with another gameweek's lineup, it says so
    stand_in = live_view({**doc, "state": "live", "lineupSource": "event/7"}, board)
    assert stand_in is not None and stand_in.estimated


def test_fpl_live_values_a_starter_still_to_play_at_this_gameweeks_projection() -> None:
    """Once a gameweek is under way the board projects the next one; a starter
    still to play counts at what was projected for the one being played."""
    xi = [("1", "GKP"), *((f"d{i}", "DEF") for i in range(3)), *((f"m{i}", "MID") for i in range(5)),
          ("f0", "FWD"), ("f1", "FWD")]
    bench = [("2", "GKP"), ("bf", "FWD"), ("bd", "DEF"), ("bm", "MID")]
    players = [_fpl(e, p) for e, p in xi + bench]  # next gameweek: 4.0 each
    board = Board(
        players=players, by_id={p.ext_id: p for p in players}, my_entry_id="1",
        lineup=[SimpleNamespace(ext_id=e, position=i, starter=i <= 11, source="event/7")
                for i, (e, _) in enumerate(xi + bench, start=1)],
        league=None, entries=[],
    )  # type: ignore[arg-type]
    elements = {e: [2, 90] for e, _ in xi + bench}
    elements["f1"] = [0, 0]  # plays Monday
    doc = {"gw": 7, "state": "live", "secured": 20, "played": 10, "starters": 11,
           "elements": elements}
    view = live_view(doc, board, {"f1": 6.5})
    assert view is not None and view.projected_finish == 10 * 2 + 6.5
    stale = live_view(doc, board)
    assert stale is not None and stale.projected_finish == 10 * 2 + 4.0
