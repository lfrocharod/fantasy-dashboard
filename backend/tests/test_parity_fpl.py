"""The Python FPL analysis must reproduce the original TypeScript (the old web
app's app/fpl/lib.ts) on the same inputs. Goldens were recorded from that code
before it was retired (the one-off recorder, tests/parity/record_goldens.ts, is
in git history); inputs come from tests/parity/generate_inputs.py."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fantasy.leagues.fpl import analysis as A
from fantasy.leagues.fpl.players import FplPlayer

HERE = Path(__file__).parent / "parity"
INPUTS = json.loads((HERE / "inputs.json").read_text())["fpl"]
GOLD = json.loads((HERE / "goldens.json").read_text())["fpl"]


@pytest.fixture(autouse=True)
def typescript_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """The goldens prove the port is faithful, so they run under the rule the
    TypeScript had: at least three midfielders. The app has since followed FPL
    Draft's real minimum of two (see test_fpl_draft.py)."""
    monkeypatch.setitem(A.XI_MIN, "MID", 3)


H = ("short", "medium", "season")


def row(d: dict[str, Any]) -> SimpleNamespace:
    """An inputs.json player (camelCase, as the old API returned it) in the
    shape of a DraftPlayer ORM row."""
    return SimpleNamespace(
        ext_id=d["extId"], name=d["name"], team=d.get("team"), primary_pos=d.get("primaryPos"),
        proj_points=d.get("projPoints"), provider_rank=d.get("providerRank"), vbd=d.get("vbd"),
        injury_status=d.get("injuryStatus"), outlook=d.get("outlook"), raw=d.get("raw"),
    )


PLAYERS = [FplPlayer.from_row(row(d)) for d in INPUTS["players"]]
BY_ID = {p.ext_id: p for p in PLAYERS}
MANAGERS = A.group_by_manager(PLAYERS, INPUTS["myEntryId"], INPUTS["fallbackNames"])
ME = next(m for m in MANAGERS if m.is_mine)
RIVALS = [m for m in MANAGERS if not m.is_mine]


def ids(ps: list[FplPlayer]) -> list[str]:
    return [p.ext_id for p in ps]


def approx(x: Any) -> Any:
    return pytest.approx(x, rel=1e-9, abs=1e-9)


def test_per_player_values() -> None:
    for got, want in zip(PLAYERS, GOLD["players"], strict=True):
        assert got.ext_id == want["extId"]
        assert got.status == want["status"] and got.available == want["available"]
        assert A.opp_factor(got) == approx(want["oppFactor"])
        assert A.opp_tag(got) == want["oppTag"]
        assert [A.value_for(got, h) for h in H] == approx(want["value"])
        assert [A.neutral_value(got, h) for h in H] == approx(want["neutral"])
        assert [A.claimable(got, h) for h in H] == want["claimable"]
        assert A.rosterable(got) == want["rosterable"]


def test_best_xi_and_horizon() -> None:
    xi = A.best_xi(ME.players)
    ros = A.best_xi(ME.players, lambda p: p.ros)
    g = GOLD["bestXI"]
    assert (ids(xi.xi), ids(xi.bench), xi.formation) == (g["xi"], g["bench"], g["formation"])
    assert (ids(ros.xi), ids(ros.bench), ros.formation) == (
        g["rosXi"], g["rosBench"], g["rosFormation"]
    )
    assert A.squad_horizon(ME.players, range(6)) == approx(GOLD["squadHorizon"])
    assert [A.xi_value(ME.players, h) for h in H] == approx(GOLD["xiValue"])


def test_group_by_manager() -> None:
    got = [
        {
            "entryId": m.entry_id, "name": m.name, "isMine": m.is_mine, "players": ids(m.players),
            "byPos": {k: ids(v) for k, v in m.by_pos.items()},
            "totalMedium": m.total_medium, "totalSeason": m.total_season,
        }
        for m in MANAGERS
    ]
    assert got == GOLD["managers"]


def _gain_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**r, "gain": approx(r["gain"])} for r in rows]


def test_per_manager_lineups_waivers_and_trades() -> None:
    by_entry = {m.entry_id: m for m in MANAGERS}
    for want in GOLD["perManager"]:
        me = by_entry[want["entryId"]]
        others = [m for m in MANAGERS if m.entry_id != me.entry_id]
        owners = {m.entry_id: (m.name, {p.ext_id for p in m.players}) for m in others}
        mine = {p.ext_id for p in me.players}
        fa = [p for p in PLAYERS if p.available and p.ext_id not in mine]
        xi = A.best_xi(me.players)
        assert (ids(xi.xi), ids(xi.bench), xi.formation) == (
            want["xi"], want["bench"], want["formation"]
        )
        assert [A.xi_value(me.players, h) for h in H] == approx(want["xiValue"])
        for h, w in zip(H, want["weakSpots"], strict=True):
            got = [{"out": u.out.ext_id, "in": u.in_.ext_id, "gain": u.gain}
                   for u in A.weak_spots(xi.xi, fa, h)]
            assert got == _gain_rows(w)
        for h, w in zip(H, want["tradeIdeas"], strict=True):
            got = [
                {"rival": t.rival_name, "give": ids(t.give), "get": ids(t.get),
                 "myGain": t.my_gain, "theirGain": t.their_gain}
                for t in A.trade_ideas(me.players, PLAYERS, owners, 4, h)
            ]
            assert got == w


def test_evaluate_trade() -> None:
    by_entry = {m.entry_id: m for m in MANAGERS}
    for t, want in zip(INPUTS["trades"], GOLD["evaluateTrade"], strict=True):
        squad = by_entry.get(t.get("owner", INPUTS["myEntryId"]), ME).players
        ev = A.evaluate_trade([BY_ID[x] for x in t["give"]], [BY_ID[x] for x in t["get"]], squad)
        d = asdict(ev)
        got = {
            "balanced": d["balanced"], "posGive": d["pos_give"], "posGet": d["pos_get"],
            "meShort": d["me_short"], "meMedium": d["me_medium"], "meSeason": d["me_season"],
            "themShort": d["them_short"], "themMedium": d["them_medium"],
            "themSeason": d["them_season"], "warnings": d["warnings"], "verdict": d["verdict"],
        }
        assert got == want


def test_stash_and_claims() -> None:
    assert ids(A.stash_candidates(PLAYERS, {p.ext_id for p in ME.players})) == GOLD["stash"]
    got = [
        {"rival": c.rival_name, "weakPos": c.weak_pos, "weakStarter": c.weak_starter,
         "target": c.target.ext_id, "gain": c.gain}
        for c in A.predict_claims(MANAGERS, PLAYERS, INPUTS["myEntryId"])
    ]
    assert got == GOLD["predictClaims"]


def test_clubs() -> None:
    fx = A.club_fixtures(PLAYERS)
    want_fx = GOLD["clubFixtures"]
    assert [c.team for c in fx] == [c["team"] for c in want_fx]
    for c, w in zip(fx, want_fx, strict=True):
        assert c.avg_fdr == approx(w["avgFdr"])
        assert [
            {"gw": x.gw, "opp": x.opp, "home": x.home, "fdr": x.fdr, "fdrAtt": x.fdr_att,
             "fdrDef": x.fdr_def}
            for x in c.cells
        ] == w["cells"]
    got = [
        {"team": d.team, "avgFdr": d.avg_fdr, "probableXI": ids(d.probable_xi),
         "bench": ids(d.bench), "pk": ids(d.set_pieces["pk"]), "fk": ids(d.set_pieces["fk"]),
         "ck": ids(d.set_pieces["ck"]), "doubts": ids(d.doubts), "keyPlayers": ids(d.key_players)}
        for d in A.club_dossiers(PLAYERS)
    ]
    assert got == GOLD["clubDossiers"]


def test_sort_players() -> None:
    assert ids(A.sort_players(PLAYERS, "horizon")) == GOLD["sortHorizon"]
