from fantasy.leagues.ucl.model.optimizer import OptPlayer, best_xi, captain_pick, optimise


def _squad():
    # 2 GK, 5 DEF, 5 MID, 3 FWD with clearly-ranked xpts inside each position.
    rows = []
    pid = 1
    plan = [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]
    for pos, n in plan:
        for i in range(n):
            rows.append(
                OptPlayer(
                    player_id=pid, name=f"{pos}{i}", team=f"C{pid % 6}", club_id=pid % 6,
                    position=pos, price=5.0 + i, xpts=6.0 - i * 0.9, owned=True,
                )
            )
            pid += 1
    return rows


def test_best_xi_is_legal_and_size_11():
    starters, bench, formation, xi_xpts = best_xi(_squad())
    assert len(starters) == 11
    assert len(bench) == 4
    counts = {p.position: 0 for p in starters}
    for p in starters:
        counts[p.position] += 1
    assert counts["GK"] == 1
    assert 3 <= counts["DEF"] <= 5
    assert 2 <= counts["MID"] <= 5
    assert 1 <= counts["FWD"] <= 3
    assert counts["DEF"] + counts["MID"] + counts["FWD"] == 10
    assert xi_xpts > 0
    assert formation.count("-") == 2


def test_captain_is_highest_xpts_starter():
    starters, *_ = best_xi(_squad())
    cap, vice = captain_pick(starters)
    ranked = sorted(starters, key=lambda p: -p.xpts)
    assert cap == ranked[0].player_id
    assert vice == ranked[1].player_id


def test_transfer_planner_takes_obvious_upgrade():
    squad = _squad()
    # A cheap, clearly better MID free agent than our worst MID.
    worst_mid = min((p for p in squad if p.position == "MID"), key=lambda p: p.xpts)
    upgrade = OptPlayer(
        player_id=999, name="Superstar", team="C5", club_id=5, position="MID",
        price=worst_mid.price, xpts=worst_mid.xpts + 4.0,
    )
    out = optimise(squad, squad + [upgrade], matchday=5, bank=5.0, free_transfers=1, horizon=2)
    assert out["transfers"], "expected at least one transfer suggestion"
    first = out["transfers"][0]
    assert first["in"]["playerId"] == 999
    assert first["netGain"] > 0


def test_no_transfer_when_squad_already_optimal():
    squad = _squad()
    # Pool = just the squad, nothing better available.
    out = optimise(squad, list(squad), matchday=5, bank=0.0, free_transfers=1, horizon=2)
    assert out["transfers"] == []
    assert out["formation"]
    assert len(out["bestXI"]) == 11
