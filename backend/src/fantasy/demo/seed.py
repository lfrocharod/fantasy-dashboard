"""Seed an anonymised, three-league demo database — offline and deterministic.

    fantasy demo seed            # into $DATABASE_URL (a dedicated demo database!)

* UCL: the real pipeline runs on the committed sample feeds, then a finished
  matchday 1 (scores, rival squads, standings) is simulated so every page —
  rivals, league, calibration — has something to show.
* FPL Draft: the real board builder runs against recorded public FPL data;
  a 5-manager league is drafted around it.
* NFL: an in-season board built from nflverse aggregates and this season's
  schedule; a 10-team league is drafted and played to date.

Manager and team names are invented. It wipes league data first, so never
point it at a real database.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

import httpx

from fantasy.config import Env, Keys
from fantasy.core.db import DB
from fantasy.demo.record import DEMO_DIR
from fantasy.leagues.draft.types import FPL_ROSTER, DraftRow

SAMPLES = DEMO_DIR.parent
SEED = 20261011
ME_UCL = "00000000-0000-4000-8000-000000000001"  # the sample feeds' "You"

LEAGUE_TABLES = (
    "projections", "player_scores", "player_stats", "player_form", "my_squad",
    "league_standings", "live_snapshots", "set_piece_roles", "player_id_overrides", "players",
    "fixtures", "teams", "draft_picks", "draft_players", "my_lineup", "matchups",
    "league_entries", "leagues", "documents", "ingest_runs", "settings",
)


def _load_gz(name: str) -> Any:
    with gzip.open(DEMO_DIR / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _wipe(db: DB) -> None:
    with db.conn() as c:
        c.execute("TRUNCATE " + ", ".join(LEAGUE_TABLES) + " RESTART IDENTITY CASCADE")


# ---- UCL ------------------------------------------------------------------------------


def seed_ucl(db: DB, rng: random.Random) -> None:
    from fantasy.leagues.ucl import calibrate, pipeline

    db.set_setting(Keys.LEAGUE_ID, "demo-league")
    db.set_setting(Keys.LEAGUE_CODE, "DEMO42")
    db.set_setting(Keys.ENTRY_ID, ME_UCL)
    db.set_setting(Keys.UEFA_AUTH_STATE, "authed")

    def run(md: int) -> None:
        ns = argparse.Namespace(matchday=md, skip_sources=True, live=False,
                                samples=str(SAMPLES), dry_run=False)
        if pipeline.run(ns) != 0:
            raise RuntimeError(f"UCL sample pipeline failed for MD{md}")

    run(1)  # MD1..8 projections (MD1's stay as the frozen pre-match numbers)
    run(2)  # the current matchday: MD2 squad, projections and optimizer

    # ---- a finished matchday 1 -----------------------------------------------------
    with db.conn() as c:
        fixtures = c.execute("select uefa_match_id from fixtures where matchday = 1").fetchall()
        for (mid,) in fixtures:
            hg, ag = (min(5, int(rng.expovariate(0.75))) for _ in range(2))
            c.execute("update fixtures set status='finished', home_goals=%s, away_goals=%s "
                      "where uefa_match_id=%s", (hg, ag, mid))
        proj = c.execute(
            "select p.player_id, p.xpts, p.p_start, pl.position from projections p "
            "join players pl on pl.uefa_player_id = p.player_id where p.matchday = 1"
        ).fetchall()
    scores = []
    for pid, xpts, p_start, pos in proj:
        played = rng.random() < max(0.05, min(0.97, p_start or 0.0))
        if not played:
            pts = 0
        else:
            spread = 1.0 + 1.6 * math.sqrt(max(0.1, xpts or 0))
            pts = max(-2, round(rng.gauss((xpts or 0) * 1.03, spread)))
            if pos == "GK" and rng.random() < 0.3:
                pts += 2
        scores.append((pid, 1, int(pts), played, True))
    db.upsert_player_scores(scores)
    calibrate.compute_and_store(db)

    # ---- rival squads + standings for MD1 and MD2 -------------------------------------
    with db.conn() as c:
        pool = c.execute(
            "select p.uefa_player_id, p.position, p.price, coalesce(pr.xpts, 0), p.team_id "
            "from players p left join projections pr on pr.player_id = p.uefa_player_id "
            "and pr.matchday = 2 where p.status_code < 2"
        ).fetchall()
    by_pos: dict[str, list[tuple]] = defaultdict(list)
    for row in pool:
        by_pos[row[1]].append(row)
    for lst in by_pos.values():
        lst.sort(key=lambda r: -r[3])
    pts1 = {pid: p for pid, _, p, _, _ in scores}
    xpts_of = {r[0]: r[3] for r in pool}

    def squad() -> list[dict]:
        picks: list[dict] = []
        for pos, n, start in (("GK", 2, 1), ("DEF", 5, 4), ("MID", 5, 4), ("FWD", 3, 2)):
            top = by_pos[pos][: max(n * 4, 12)]
            chosen = rng.sample(top, n)
            chosen.sort(key=lambda r: -r[3])
            for i, r in enumerate(chosen):
                picks.append({"id": r[0], "c": False, "s": i < start, "b": 0 if i < start else i})
        best = max((p for p in picks if p["s"]), key=lambda p: xpts_of.get(p["id"], 0.0))
        best["c"] = True
        return picks

    managers = [
        (ME_UCL, "You", "Demo XI"), ("rival-1", "Alex", "Gegenpress FC"),
        ("rival-2", "Sam", "Low Block United"), ("rival-3", "Jordan", "False Nine"),
        ("rival-4", "Riley", "Inverted Fullbacks"),
    ]
    my_ids = [r[0] for r in _fetch(db, "select player_id from my_squad where matchday = 2")]
    rows1: list[_UclEntry] = []
    for entry, manager, team in managers:
        sq = [{"id": i, "c": False, "s": True, "b": 0} for i in my_ids] if entry == ME_UCL else squad()
        md1 = sum(pts1.get(p["id"], 0) * (2 if p["c"] else 1) for p in sq if p["s"])
        rows1.append(_UclEntry(entry, manager, team, int(md1), sq))
    rows1.sort(key=lambda r: -r.points)
    me = next(i for i, r in enumerate(rows1) if r.entry_id == ME_UCL)
    if me != 1:  # second place, a few points behind: the "chase" strategy shows
        you = rows1.pop(me)
        you.points = rows1[0].points - rng.randint(2, 6)
        rows1.insert(1, you)
        for r in rows1[2:]:
            r.points = min(r.points, you.points - 1)
    from fantasy.leagues.ucl.types import LeagueEntry

    entries1, entries2 = [], []
    for rank, r in enumerate(rows1, start=1):
        e = LeagueEntry(entry_id=r.entry_id, manager_name=r.manager, team_name=r.team, matchday=1,
                        points=r.points, total_points=r.points, rank=rank, prev_rank=rank)
        e.squad = r.squad
        entries1.append(e)
        e2 = LeagueEntry(entry_id=r.entry_id, manager_name=r.manager, team_name=r.team, matchday=2,
                         points=0, total_points=r.points, rank=rank, prev_rank=rank)
        e2.squad = r.squad if r.entry_id != ME_UCL else []
        entries2.append(e2)
    with db.conn() as c:  # drop the sample feed's own (2-rival) table
        c.execute("delete from league_standings where league_id = 'demo-league'")
    db.upsert_league_standings("demo-league", entries1 + entries2)
    # keep the demo's deadline ahead of "now" (the demo re-seeds daily)
    db.upsert_league("ucl", deadline=datetime.now(UTC) + timedelta(hours=40))


@dataclass(slots=True)
class _UclEntry:
    entry_id: str
    manager: str
    team: str
    points: int
    squad: list[dict[str, Any]]


def _fetch(db: DB, sql: str) -> list[tuple[Any, ...]]:
    with db.conn() as c:
        return c.execute(sql).fetchall()


# ---- FPL Draft -------------------------------------------------------------------------

FPL_MANAGERS = [
    ("101", "Demo FC"), ("202", "Rival United"), ("303", "The Underdogs"),
    ("404", "Expected Goals FC"), ("505", "Set Piece Merchants"),
]


def _fpl_transport() -> httpx.MockTransport:
    boot = _load_gz("fpl_bootstrap.json.gz")
    fixtures = _load_gz("fpl_fixtures.json.gz")

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/bootstrap-static"):
            return httpx.Response(200, json=boot)
        if path.endswith("/fixtures/"):
            return httpx.Response(200, json=fixtures)
        if "/event/" in path and path.endswith("/live"):
            gw = path.split("/event/")[1].split("/")[0]
            f = DEMO_DIR / f"fpl_live_{gw}.json.gz"
            return httpx.Response(200, json=_load_gz(f.name)) if f.exists() else httpx.Response(404)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def seed_fpl(db: DB, rng: random.Random) -> None:
    from fantasy.leagues.fpl import analysis as A
    from fantasy.leagues.fpl import board
    from fantasy.leagues.fpl.players import FplPlayer

    transport = _fpl_transport()
    boot = _load_gz("fpl_bootstrap.json.gz")
    events = boot.get("events", {})
    next_gw = int(events.get("next") or events.get("current") or 1)
    with mock.patch.object(board, "_client", lambda: httpx.Client(transport=transport)):
        rows: list[DraftRow] = board.build(next_gw, dict(FPL_ROSTER), len(FPL_MANAGERS), None, None)

    # a snake draft that looks like week 7: pre-season rank blended with current
    # projection (managers have been working the waiver wire), plus some noise
    by_proj = {r.ext_id: i for i, r in enumerate(sorted(rows, key=lambda r: -(r.raw or {}).get("horizon_xpts", 0)))}
    order = sorted(rows, key=lambda r: 0.5 * min(r.provider_rank or 400, 400)
                   + 0.5 * by_proj[r.ext_id] + rng.gauss(0, 10))
    quota = {m: dict(FPL_ROSTER) for m, _ in FPL_MANAGERS}
    taken: dict[str, str] = {}
    picks: list[dict] = []
    seq = [m for rnd in range(15) for m in (FPL_MANAGERS if rnd % 2 == 0 else FPL_MANAGERS[::-1])]
    for overall, (entry, name) in enumerate(seq, start=1):
        r = next(
            (r for r in order if r.ext_id not in taken and quota[entry].get(r.primary_pos, 0) > 0
             and r.injury_status in ("a", "d")),
            None,
        )
        if r is None:
            continue
        taken[r.ext_id] = entry
        quota[entry][r.primary_pos] -= 1
        picks.append({"overall": overall, "round": (overall - 1) // 5 + 1, "pick_in_round":
                      (overall - 1) % 5 + 1, "team_id": int(entry), "team_name": name,
                      "player_ext_id": r.ext_id, "is_mine": entry == "101", "source": "fpl"})
    names = dict(FPL_MANAGERS)
    for r in rows:
        if r.ext_id in taken:
            r.owner, r.owner_name, r.available = taken[r.ext_id], names[taken[r.ext_id]], False
    db.replace_draft_players("fpl", rows)
    db.replace_draft_picks("fpl", picks, source="fpl")

    db.set_setting("draft.fpl.entry_id", "101")
    db.set_setting("draft.fpl.league_id", "demo")
    db.set_setting("draft.fpl.teams", str(len(FPL_MANAGERS)))
    db.upsert_league("fpl", name="Demo Draft League", n_teams=len(FPL_MANAGERS), scoring="c",
                     current_round=next_gw)

    # standings: season-to-date points of each manager's roster, with noise
    played = max(1, next_gw - 1)
    totals: list[tuple[str, str, int]] = []
    for entry, name in FPL_MANAGERS:
        roster = [r for r in rows if taken.get(r.ext_id) == entry]
        ppg = sorted(((r.raw or {}).get("ppg", 0.0) for r in roster), reverse=True)[:11]
        totals.append((entry, name, round(sum(ppg) * played * rng.uniform(0.85, 1.1))))
    totals.sort(key=lambda t: -t[2])
    me = next(i for i, t in enumerate(totals) if t[0] == "101")
    if me != 1:  # a close second makes the standings page tell a story
        mine = totals.pop(me)
        totals.insert(1, (mine[0], mine[1], totals[0][2] - rng.randint(4, 15)))
        totals = [totals[0], totals[1], *sorted(totals[2:], key=lambda t: -t[2])]
        totals = [(e, n, min(t, totals[1][2] - 1) if i > 1 else t) for i, (e, n, t) in enumerate(totals)]
    db.replace_league_entries("fpl", [
        {"entry_id": e, "name": n, "is_mine": e == "101", "rank": i, "total": t, "points_for": t}
        for i, (e, n, t) in enumerate(totals, start=1)
    ])

    # your set lineup: the model's best XI, then the bench
    squad = [
        FplPlayer.from_row(type("R", (), {
            "ext_id": r.ext_id, "name": r.name, "team": r.team, "primary_pos": r.primary_pos,
            "proj_points": r.proj_points, "provider_rank": r.provider_rank, "vbd": r.vbd,
            "injury_status": r.injury_status, "outlook": r.outlook, "raw": board_raw(r),
        })())
        for r in rows if taken.get(r.ext_id) == "101"
    ]
    lineup = A.best_xi(squad)
    db.replace_my_lineup("fpl", [
        {"ext_id": p.ext_id, "position": i, "starter": i <= 11, "source": "my-team"}
        for i, p in enumerate([*lineup.xi, *lineup.bench], start=1)
    ])


def board_raw(r: DraftRow) -> dict:
    from fantasy.core.db import _draft_raw

    return _draft_raw(r)


# ---- NFL ---------------------------------------------------------------------------------

NFL_TEAMS = [
    (1, "Fourth & Long"), (2, "Air Raid"), (3, "Demo Team"), (4, "Run The Table"),
    (5, "Red Zone Regulars"), (6, "Two-Minute Drill"), (7, "Play Action"),
    (8, "Hail Mary"), (9, "Blitz Package"), (10, "Prevent Defense"),
]
MY_NFL = 3
SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1}
REG_WEEKS, PLAYOFF_WEEKS = 14, [15, 16]
DEFENSE_NAMES = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills", "CAR": "Panthers",
    "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns", "DAL": "Cowboys", "DEN": "Broncos",
    "DET": "Lions", "GB": "Packers", "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars",
    "KC": "Chiefs", "LV": "Raiders", "LAC": "Chargers", "LAR": "Rams", "MIA": "Dolphins",
    "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants", "NYJ": "Jets",
    "PHI": "Eagles", "PIT": "Steelers", "SF": "49ers", "SEA": "Seahawks", "TB": "Buccaneers",
    "TEN": "Titans", "WSH": "Commanders",
}


def _round_robin(teams: list[int], weeks: int) -> list[tuple[int, int, int]]:
    """Circle-method schedule: (week, home, away)."""
    ts = list(teams)
    out = []
    for w in range(1, weeks + 1):
        for i in range(len(ts) // 2):
            a, b = ts[i], ts[-1 - i]
            out.append((w, a, b) if w % 2 else (w, b, a))
        ts = [ts[0], ts[-1], *ts[1:-1]]
    return out


def seed_nfl(db: DB, rng: random.Random) -> None:
    from fantasy.leagues.nfl import analysis as A
    from fantasy.leagues.nfl.players import NflPlayer
    from fantasy.leagues.nfl.season import _vor

    snap = _load_gz("nfl_snapshot.json.gz")
    week = int(snap["current_week"])
    sched: dict[int, dict[str, tuple[str, bool]]] = defaultdict(dict)
    for g in snap["schedule"]:
        sched[g["week"]][g["home"]] = (g["away"], True)
        sched[g["week"]][g["away"]] = (g["home"], False)
    byes = {t: next((w for w in range(1, 19) if t not in sched[w]), 0) for t in DEFENSE_NAMES}
    defense = snap["defense"]
    avg = {pos: (sum(d.get(pos, 0) for d in defense.values()) / max(1, len(defense)))
           for pos in ("QB", "RB", "WR", "TE", "K")}

    def fdr(opp: str, pos: str) -> int:
        if pos == "DST":  # a weak offence is an easy matchup for a defence
            allowed = sum(v for v in defense.get(opp, {}).values()) or 1.0
            return max(1, min(5, 3 + round((allowed - 60) / 12)))
        allowed = defense.get(opp, {}).get(pos, avg.get(pos, 10))
        ratio = allowed / max(0.1, avg.get(pos, 10))
        return max(1, min(5, round(3 - (ratio - 1) * 4)))

    players = list(snap["players"])
    for t, nick in DEFENSE_NAMES.items():
        allowed = sum(defense.get(t, {}).values())
        players.append({"id": f"dst-{t}", "name": f"{nick} D/ST", "pos": "DST", "team": t,
                        "games": week - 1, "ppg": round(max(2.0, 13 - allowed / 9), 2),
                        "prev_ppg": 6.5, "last": [], "tshare": 0, "wopr": 0, "touches": 0})

    rows: list[DraftRow] = []
    for p in players:
        g = p["games"]
        rate = (0.65 * p["ppg"] + 0.35 * p["prev_ppg"]) if g else p["prev_ppg"] * 0.9
        if p["pos"] == "K" and rate <= 0:
            rate = 7.5
        if rate <= 0.5:
            continue
        team, pos = p["team"], p["pos"]
        bye = byes.get(team, 0)
        matchups: list[dict[str, Any]] = []
        for wk in range(week, week + 6):
            m = sched[wk].get(team)
            if wk == bye or m is None:
                matchups.append({"week": wk, "opp": "BYE" if wk == bye else "", "home": None, "fdr": 0})
            else:
                matchups.append({"week": wk, "opp": m[0], "home": m[1], "fdr": fdr(m[0], pos)})
        m0: dict[str, Any] = matchups[0]
        injury = rng.choices(["ACTIVE", "QUESTIONABLE", "DOUBTFUL", "OUT", "IR"], [90, 6, 1, 2, 1])[0]
        week_proj = 0.0 if m0["opp"] in ("BYE", "") else round(
            rate * (1 + (3 - m0["fdr"]) * 0.05) * rng.uniform(0.92, 1.08), 1)
        games_left = sum(1 for w in range(week, REG_WEEKS + 1) if w != bye)
        ros = round(rate * games_left * rng.uniform(0.95, 1.05), 1)
        snap_pct = 0.0 if pos in ("QB", "K", "DST") else round(
            min(0.98, 0.3 + 0.9 * p["wopr"] + 0.02 * p["touches"]), 2)
        xfp = round(max(0.0, p["ppg"] + rng.gauss(0, 1.6)), 1) if g else 0.0
        rows.append(DraftRow(
            sport="nfl", ext_id=str(p["id"]), name=p["name"], team=team, positions=[pos],
            primary_pos=pos, proj_points=week_proj, injury_status=injury,
            next_opp=(f"{'vs' if m0['home'] else '@'} {m0['opp']}"
                      if m0["opp"] not in ("", "BYE") else m0["opp"]),
            next_fdr=m0["fdr"],
            raw={
                "weekProj": week_proj, "rosProj": ros, "bye": bye, "onBye": bye == week,
                "injury": injury, "week": week, "matchups": matchups,
                "snapPct": snap_pct, "snapTrend": round(rng.uniform(-0.1, 0.1), 2) if snap_pct else 0,
                "targetShare": p["tshare"], "wopr": p["wopr"], "touches": p["touches"],
                "usageGames": min(4, g), "usageStale": False,
                "xfpG": xfp, "xtdG": round(max(0.0, xfp / 14), 2) if xfp else 0.0,
                "fpOE": round(p["ppg"] - xfp, 1) if g else 0.0, "expGames": min(4, g),
            },
        ))
    _vor(rows, SLOTS, len(NFL_TEAMS))
    rows.sort(key=lambda r: -(r.raw or {})["rosProj"])
    for i, r in enumerate(rows, start=1):
        r.ecr_rank = r.provider_rank = i
        pct = max(0.5, min(99.5, 100 * math.exp(-i / 140)))
        assert r.raw is not None
        r.raw["pctOwned"] = round(pct, 1)
        r.raw["pctStarted"] = round(pct * rng.uniform(0.55, 0.95), 1)

    # draft: 16 rounds, snake, a starting lineup's worth of positions first
    need = {t: {"QB": 2, "RB": 5, "WR": 5, "TE": 2, "K": 1, "DST": 1} for t, _ in NFL_TEAMS}
    order = sorted(rows, key=lambda r: (r.ecr_rank or 999) + rng.gauss(0, 10))
    owner: dict[str, int] = {}
    seq = [t for rnd in range(16) for t, _ in (NFL_TEAMS if rnd % 2 == 0 else NFL_TEAMS[::-1])]
    for team_id in seq:
        pick = next(
            (r for r in order if r.ext_id not in owner and need[team_id].get(r.primary_pos, 0) > 0), None
        )
        if pick:
            owner[pick.ext_id] = team_id
            need[team_id][pick.primary_pos] -= 1
    names = dict(NFL_TEAMS)

    def as_player(r: DraftRow) -> NflPlayer:
        return NflPlayer.from_row(type("R", (), {
            "ext_id": r.ext_id, "name": r.name, "team": r.team, "primary_pos": r.primary_pos,
            "proj_points": r.proj_points, "vbd": r.vbd, "ecr_rank": r.ecr_rank,
            "ecr_tier": r.ecr_tier, "raw": r.raw,
        })())

    for r in rows:
        tid = owner.get(r.ext_id)
        assert r.raw is not None
        r.raw.update({"ownerTeamId": tid, "ownerName": names.get(tid, "") if tid else "",
                      "available": tid is None, "slot": ""})
        r.available = tid is None
    for team_id, _ in NFL_TEAMS:
        roster = [r for r in rows if owner.get(r.ext_id) == team_id]
        lineup = A.optimal_lineup([as_player(r) for r in roster], SLOTS, 0)
        starters = {s.player.ext_id: s.slot for s in lineup.starters if s.player}
        for r in roster:
            assert r.raw is not None
            r.raw["slot"] = starters.get(r.ext_id, "BE")
        if team_id == MY_NFL:  # leave one fixable mistake for the optimizer to catch
            bench = [r for r in roster if r.ext_id not in starters and r.primary_pos in ("RB", "WR")]
            flex = next((r for r in roster if starters.get(r.ext_id) == "FLEX"), None)
            if bench and flex and flex.raw is not None and bench[0].raw is not None:
                flex.raw["slot"], bench[0].raw["slot"] = "BE", "FLEX"
    db.replace_draft_players("nfl", rows)

    # league: schedule, results to date, standings
    ids = [t for t, _ in NFL_TEAMS]
    games = _round_robin(ids, REG_WEEKS)
    strength = {t: sum(sorted(((r.raw or {})["rosProj"] for r in rows if owner.get(r.ext_id) == t),
                              reverse=True)[:9]) / max(1, REG_WEEKS - week + 1) for t in ids}
    rec = {t: {"wins": 0, "losses": 0, "ties": 0, "pf": 0.0, "pa": 0.0} for t in ids}
    fixtures: list[dict[str, Any]] = []
    for w, h, a in games:
        if w < week:
            hs, as_ = (round(max(50, rng.gauss(strength[t] * 0.92, 22)), 1) for t in (h, a))
            rec[h]["pf"] += hs
            rec[a]["pf"] += as_
            rec[h]["pa"] += as_
            rec[a]["pa"] += hs
            win = "HOME" if hs > as_ else "AWAY" if as_ > hs else "TIE"
            for side, res in ((h, win == "HOME"), (a, win == "AWAY")):
                rec[side]["wins" if res else "ties" if win == "TIE" else "losses"] += 1
        else:
            hs = as_ = 0.0
            win = "UNDECIDED"
        fixtures.append({"round": w, "home_entry": str(h), "away_entry": str(a),
                         "home_name": names[h], "away_name": names[a], "home_points": hs,
                         "away_points": as_, "winner": win, "finished": w < week})
    db.set_setting("draft.nfl.my_team_id", str(MY_NFL))
    db.set_setting("draft.nfl.league_id", "demo")
    db.set_setting("draft.nfl.teams", str(len(NFL_TEAMS)))
    db.set_setting("draft.nfl.scoring", "ppr")
    db.upsert_league("nfl", name="Demo NFL League", current_round=week, n_teams=len(NFL_TEAMS),
                     scoring="ppr", regular_rounds=REG_WEEKS, playoff_rounds=PLAYOFF_WEEKS,
                     playoff_teams=4, seeding_rule="H2H_RECORD", lineup_slots=SLOTS)
    db.replace_matchups("nfl", fixtures)
    db.replace_league_entries("nfl", [
        {"entry_id": str(t), "name": names[t], "is_mine": t == MY_NFL,
         "wins": rec[t]["wins"], "losses": rec[t]["losses"], "draws": rec[t]["ties"],
         "points_for": round(rec[t]["pf"], 1), "points_against": round(rec[t]["pa"], 1)}
        for t in ids
    ])
    mine = [r for r in rows if owner.get(r.ext_id) == MY_NFL]
    db.replace_my_lineup("nfl", [
        {"ext_id": r.ext_id, "starter": (r.raw or {}).get("slot") not in ("BE", "IR", ""),
         "source": "espn"}
        for r in mine
    ])


def seed(database_url: str | None = None, seed: int = SEED) -> None:
    if database_url:
        os.environ["DATABASE_URL"] = database_url  # the UCL pipeline reads it from the env
    env = Env.load()
    db = DB(env.database_url)
    _wipe(db)
    rng = random.Random(seed)
    seed_ucl(db, rng)
    seed_fpl(db, random.Random(seed + 1))
    seed_nfl(db, random.Random(seed + 2))
    db.close()


if __name__ == "__main__":
    seed()

