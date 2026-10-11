from fantasy.leagues.ucl.model.captains import analyse_captains
from fantasy.leagues.ucl.model.chips import evaluate_chips
from fantasy.leagues.ucl.model.optimizer import OptPlayer


def _squad(scale=1.0):
    rows = []
    pid = 1
    for pos, n in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for i in range(n):
            rows.append(
                OptPlayer(
                    player_id=pid, name=f"{pos}{i}", team=f"C{pid % 6}", club_id=pid % 6,
                    position=pos, price=5.0 + i, xpts=(6.0 - i * 0.8) * scale, owned=True,
                )
            )
            pid += 1
    return rows


def test_analyse_captains_picks_top_ev_and_differential():
    rows = [
        {"playerId": 1, "name": "Star", "team": "A", "position": "FWD",
         "xpts": 7.0, "xptsHigh": 12.0, "xptsLow": 3.0, "selectedPct": 60.0},
        {"playerId": 2, "name": "Punt", "team": "B", "position": "MID",
         "xpts": 5.0, "xptsHigh": 14.0, "xptsLow": 1.0, "selectedPct": 4.0},
        {"playerId": 3, "name": "Bench", "team": "C", "position": "DEF",
         "xpts": 0.0, "xptsHigh": 0.0, "xptsLow": 0.0, "selectedPct": 1.0},
    ]
    out = analyse_captains(rows)
    assert {c["playerId"] for c in out["candidates"]} == {1, 2}  # zero-xpts dropped
    assert out["safePick"]["playerId"] == 1
    assert out["differentialPick"]["playerId"] == 2  # low owned, huge ceiling


def test_evaluate_chips_returns_per_md_and_recommendations():
    # weak owned squad; the pool has a much stronger set of distinct players
    squad_by_md = {6: _squad(1.0), 7: _squad(1.0), 8: _squad(1.0)}
    pool_by_md = {}
    for md in (6, 7, 8):
        extra = _squad(2.2)
        for j, p in enumerate(extra):
            p.player_id = md * 1000 + j
            p.club_id = 20 + (j % 6)
        pool_by_md[md] = extra
    out = evaluate_chips(squad_by_md, pool_by_md, start_md=6)
    assert [r["matchday"] for r in out["perMatchday"]] == [6, 7, 8]
    for r in out["perMatchday"]:
        assert r["limitless"] >= 0 and r["wildcard"] >= 0
        assert "benchBoost" not in r and "tripleCaptain" not in r
    assert set(out["recommend"]) == {"wildcard", "limitless"}
    # a squad this far below the pool -> Limitless should be recommended
    assert out["recommend"]["limitless"] is not None
    # Wildcard defaults to the last league-phase matchday (8)
    assert out["recommend"]["wildcard"]["matchday"] == 8


def test_evaluate_chips_marks_used_chip_unavailable():
    squad_by_md = {3: _squad()}
    pool_by_md = {3: _squad()}
    out = evaluate_chips(squad_by_md, pool_by_md, start_md=3, used={"wildcard": True})
    assert out["recommend"]["wildcard"] is None
