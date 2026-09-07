from fantasy_ingest.model.captains import analyse_captains
from fantasy_ingest.model.chips import evaluate_chips
from fantasy_ingest.model.optimizer import OptPlayer


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
    squad_by_md = {1: _squad(1.0), 2: _squad(1.3)}
    pool_by_md = {1: _squad(1.0) + _squad(2.0), 2: _squad(1.3) + _squad(2.5)}
    # give pool distinct ids so it's a real superset
    for k, extra in ((1, 100), (2, 200)):
        for j, p in enumerate(pool_by_md[k][15:]):
            p.player_id = k * 1000 + j
            p.club_id = 10 + (j % 5)
    out = evaluate_chips(squad_by_md, pool_by_md, start_md=1)
    assert [r["matchday"] for r in out["perMatchday"]] == [1, 2]
    for r in out["perMatchday"]:
        assert r["benchBoost"] >= 0
        assert r["wildcard"] >= 0
        assert r["limitless"] >= 0
    assert set(out["recommend"]) == {"wildcard", "limitless", "benchBoost", "tripleCaptain"}


def test_evaluate_chips_marks_used_chip_unavailable():
    squad_by_md = {3: _squad()}
    pool_by_md = {3: _squad()}
    out = evaluate_chips(squad_by_md, pool_by_md, start_md=3, used={"wildcard": True})
    assert out["recommend"]["wildcard"] is None
