"""Record the public snapshots the demo dataset is built from.

    fantasy demo record      # -> backend/samples/demo/

* FPL: the public FPL Draft bootstrap, the season's fixture list, and the last
  three gameweeks' live points — exactly what the board builder fetches, so the
  demo runs the real builder offline.
* NFL: compact per-player aggregates from nflverse's weekly stats (this season
  and last), plus this season's schedule. nflverse data is CC-BY 4.0.

Run from a normal (residential) connection; the files are committed so the
seed itself never touches the network.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEMO_DIR = Path(__file__).resolve().parents[3] / "samples" / "demo"
_FPL_DRAFT = "https://draft.premierleague.com/api"
_FPL_CLASSIC = "https://fantasy.premierleague.com/api"
_NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
_GAMES = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
_UA = {"User-Agent": "Mozilla/5.0 (fantasy-dashboard demo recorder)"}
TEAM_FIX = {"LA": "LAR", "JAC": "JAX", "WAS": "WSH"}


def _save_gz(name: str, payload: Any) -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(DEMO_DIR / name, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))


def record_fpl(client: httpx.Client) -> dict[str, Any]:
    boot = client.get(f"{_FPL_DRAFT}/bootstrap-static").raise_for_status().json()
    fixtures = client.get(f"{_FPL_CLASSIC}/fixtures/").raise_for_status().json()
    current = int((boot.get("events") or {}).get("current") or 1)
    _save_gz("fpl_bootstrap.json.gz", boot)
    _save_gz("fpl_fixtures.json.gz", fixtures)
    lives = []
    for gw in range(max(1, current - 2), current + 1):
        live = client.get(f"{_FPL_DRAFT}/event/{gw}/live").raise_for_status().json()
        _save_gz(f"fpl_live_{gw}.json.gz", live)
        lives.append(gw)
    return {"current_gw": current, "live_gws": lives, "players": len(boot.get("elements", []))}


def _csv(client: httpx.Client, url: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(client.get(url).raise_for_status().text)))


def _f(v: str | None) -> float:
    try:
        return float(v) if v not in (None, "", "NA") else 0.0
    except ValueError:
        return 0.0


def _team(a: str) -> str:
    a = (a or "").upper()
    return TEAM_FIX.get(a, a)


def record_nfl(client: httpx.Client, season: int) -> dict[str, Any]:
    cur = _csv(client, f"{_NFLVERSE}/stats_player/stats_player_week_{season}.csv")
    prev = _csv(client, f"{_NFLVERSE}/stats_player/stats_player_week_{season - 1}.csv")
    games = [g for g in _csv(client, _GAMES) if g.get("season") == str(season) and g.get("game_type") == "REG"]

    # a week counts as played once it has ~a full slate of player rows
    per_week: dict[int, int] = defaultdict(int)
    for r in cur:
        per_week[int(r["week"])] += 1
    full = max(per_week.values(), default=0)
    complete = sorted(w for w, n in per_week.items() if n >= 0.85 * full)
    current_week = (max(complete) + 1) if complete else 1

    skill = {"QB", "RB", "WR", "TE", "K"}

    def aggregate(rows: list[dict[str, str]], weeks: set[int] | None) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            if r.get("season_type") != "REG" or r.get("position") not in skill:
                continue
            wk = int(r["week"])
            if weeks is not None and wk not in weeks:
                continue
            a = out.setdefault(r["player_id"], {
                "id": r["player_id"], "name": r["player_display_name"], "pos": r["position"],
                "team": _team(r["team"]), "games": 0, "ppr": 0.0, "weeks": {},
                "targets": 0.0, "touches": 0.0, "wopr": 0.0, "tshare": 0.0,
            })
            ppr = _f(r.get("fantasy_points_ppr"))
            if r["position"] == "K":  # kickers: nflverse has no fantasy points column for K
                ppr = 3 * _f(r.get("fg_made")) + _f(r.get("pat_made")) - _f(r.get("fg_missed"))
            a["games"] += 1
            a["ppr"] += ppr
            a["weeks"][wk] = round(ppr, 1)
            a["team"] = _team(r["team"])  # latest team wins (trades)
            a["targets"] += _f(r.get("targets"))
            a["touches"] += _f(r.get("carries")) + _f(r.get("receptions"))
            a["wopr"] += _f(r.get("wopr"))
            a["tshare"] += _f(r.get("target_share"))
        return out

    cur_agg = aggregate(cur, set(complete))
    prev_agg = aggregate(prev, None)
    players = []
    for pid in set(cur_agg) | set(prev_agg):
        c, p = cur_agg.get(pid), prev_agg.get(pid)
        base = c or p
        if base is None:
            continue
        g = c["games"] if c else 0
        players.append({
            "id": pid, "name": base["name"], "pos": base["pos"],
            "team": c["team"] if c else p["team"],  # type: ignore[index]
            "games": g,
            "ppg": round(c["ppr"] / g, 2) if c and g else 0.0,
            "prev_ppg": round(p["ppr"] / p["games"], 2) if p and p["games"] else 0.0,
            "last": [c["weeks"].get(w, 0.0) for w in complete[-4:]] if c else [],
            "tshare": round(c["tshare"] / g, 3) if c and g else 0.0,
            "wopr": round(c["wopr"] / g, 3) if c and g else 0.0,
            "touches": round(c["touches"] / g, 1) if c and g else 0.0,
        })
    # keep the fantasy-relevant pool
    players.sort(key=lambda x: -(0.6 * x["ppg"] + 0.4 * x["prev_ppg"]))
    keep: list[dict[str, Any]] = []
    caps = {"QB": 40, "RB": 90, "WR": 120, "TE": 45, "K": 32}
    count: dict[str, int] = defaultdict(int)
    for x in players:
        if count[x["pos"]] < caps[x["pos"]] and x["team"]:
            keep.append(x)
            count[x["pos"]] += 1

    # fantasy points allowed per game by each defence, by position (for matchup difficulty)
    allowed: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in cur:
        if r.get("position") in skill and int(r["week"]) in complete:
            allowed[_team(r.get("opponent_team", ""))][r["position"]].append(_f(r.get("fantasy_points_ppr")))
    weeks_played = max(1, len(complete))
    defense = {
        t: {pos: round(sum(v) / weeks_played, 2) for pos, v in by.items()} for t, by in allowed.items()
    }
    schedule = [
        {"week": int(g["week"]), "away": _team(g["away_team"]), "home": _team(g["home_team"])}
        for g in games
    ]
    payload = {"season": season, "current_week": current_week, "complete_weeks": complete,
               "players": keep, "defense": defense, "schedule": schedule}
    _save_gz("nfl_snapshot.json.gz", payload)
    return {"current_week": current_week, "players": len(keep), "games": len(schedule)}


# ESPN basketball stat ids kept per split: the scoring stats, the box score, GP
_NBA_STATS = ("0", "1", "2", "3", "6", "11", "13", "14", "15", "16", "17", "19", "20", "40", "42")


def record_nba(client: httpx.Client, season: int) -> dict[str, Any]:
    """ESPN's public basketball data (no login): the most-owned players with
    their projection and last season, and every NBA team's schedule."""
    from fantasy.leagues.nba import espn

    pool = espn.fetch_players(client, season, None, limit=400)
    keep_splits = {f"10{season}", f"00{season - 1}"}
    players = []
    for e in pool:
        p = e.get("player", {}) or {}
        if not p.get("proTeamId"):
            continue
        own = p.get("ownership", {}) or {}
        players.append({
            "id": p["id"], "fullName": p.get("fullName", ""),
            "defaultPositionId": p.get("defaultPositionId"), "eligibleSlots": p.get("eligibleSlots", []),
            "proTeamId": p["proTeamId"], "injuryStatus": p.get("injuryStatus") or "ACTIVE",
            "ownership": {k: own.get(k) for k in ("percentOwned", "percentStarted", "percentChange",
                                                  "averageDraftPosition")},
            "stats": [
                {"id": st["id"], "appliedAverage": st.get("appliedAverage"),
                 "averageStats": {k: v for k, v in (st.get("averageStats") or {}).items()
                                  if k in _NBA_STATS}}
                for st in p.get("stats", []) or [] if st.get("id") in keep_splits
            ],
        })
    sched = espn.fetch_pro_schedule(client, season)
    teams = [
        {"id": t["id"], "abbrev": t.get("abbrev"), "location": t.get("location"), "name": t.get("name"),
         "proGamesByScoringPeriod": {
             sp: [{k: g.get(k) for k in ("date", "homeProTeamId", "awayProTeamId", "scoringPeriodId")}
                  for g in games]
             for sp, games in (t.get("proGamesByScoringPeriod") or {}).items()}}
        for t in (sched.get("settings", {}) or {}).get("proTeams", []) if t.get("id")
    ]
    _save_gz("nba_snapshot.json.gz", {"season": season, "players": players,
                                      "schedule": {"settings": {"proTeams": teams}}})
    return {"season": season, "players": len(players), "teams": len(teams)}


def record(season: int | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    nfl_season = season or (now.year if now.month >= 8 else now.year - 1)
    nba_season = now.year + 1 if now.month >= 8 else now.year
    with httpx.Client(headers=_UA, timeout=60, follow_redirects=True) as client:
        meta = {"recorded_at": now.isoformat(), "fpl": record_fpl(client),
                "nfl": record_nfl(client, nfl_season)}
    from fantasy.leagues.nba import espn

    with espn.client() as client:
        meta["nba"] = record_nba(client, nba_season)
    (DEMO_DIR / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta
