"""The NBA player board: one row per player in the pool (ESPN's most-owned
players plus anyone on a fantasy roster), with a per-game fantasy points
estimate in the league's own scoring.

The estimate leans on ESPN's preseason projection, nudged by last season, and
hands over to the player's actual average as games accumulate: at
`PRIOR_GAMES` games played the two weigh the same. A small recent-form tilt
(the last 15 days) applies once there's enough of a season to tilt.
"""

from __future__ import annotations

from typing import Any

from fantasy.leagues.draft.types import DraftRow
from fantasy.leagues.nba.league import POS, RESERVE, SLOT, FantasyTeam, ProTeam, Rules

PRIOR_GAMES = 12
# ESPN stat splits are keyed f"{source}{split}{season}": source 0 = actual,
# 1 = projected; split 0 = season, 1 / 2 / 3 = last 7 / 15 / 30 days.
SEASON, LAST15 = "00", "02"
PROJECTED = "10"
LINE = {"pts": "0", "reb": "6", "ast": "3", "stl": "2", "blk": "1", "tpm": "17", "to": "11",
        "min": "40", "fgPct": "19", "ftPct": "20"}


def _num(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def split(stats: list[dict[str, Any]], key: str, scoring: dict[int, float]) -> tuple[float, int, dict[str, Any]]:
    """(fantasy points per game, games, per-game averages) for one stat split.
    ESPN's `appliedAverage` is already in the league's scoring; it's recomputed
    from the averages only when missing."""
    s = next((x for x in stats if x.get("id") == key), None)
    if not s:
        return 0.0, 0, {}
    avg: dict[str, Any] = s.get("averageStats") or {}
    fppg = _num(s.get("appliedAverage"))
    if not fppg and avg and scoring:
        fppg = sum(_num(avg.get(str(k))) * v for k, v in scoring.items())
    games = int(_num(avg.get("42")))
    if not games and fppg:
        games = round(_num(s.get("appliedTotal")) / fppg)
    return round(fppg, 2), games, avg


def blend(proj: float, last: float, last_gp: int, now: float, now_gp: int,
          l15: float, l15_gp: int) -> float:
    """Per-game fantasy points the app plans with (see the module docstring)."""
    prior = proj
    if last and last_gp >= 20:
        prior = 0.8 * proj + 0.2 * last if proj else last
    if not prior:
        prior = now
    base = (prior * PRIOR_GAMES + now * now_gp) / (PRIOR_GAMES + now_gp) if now_gp else prior
    if now_gp >= 8 and l15_gp >= 4:
        base = 0.85 * base + 0.15 * l15
    return round(max(0.0, base), 2)


def _line(avg: dict[str, Any]) -> dict[str, float]:
    return {k: round(_num(avg.get(sid)), 3 if k.endswith("Pct") else 1) for k, sid in LINE.items()}


def build_rows(
    pool: list[dict[str, Any]],
    teams: list[FantasyTeam],
    rules: Rules,
    pro: dict[int, ProTeam],
    season: int,
    rostered: dict[int, dict[str, Any]] | None = None,
) -> list[DraftRow]:
    """`pool`: kona_player_info entries; `rostered`: player id → roster entry
    (`playerPoolEntry`) for anyone on a fantasy team the pool missed."""
    owner: dict[int, tuple[FantasyTeam, str]] = {
        pid: (t, slot) for t in teams for pid, slot in t.roster
    }
    entries = {int(e["player"]["id"]): e for e in pool if e.get("player", {}).get("id")}
    for pid, e in (rostered or {}).items():
        entries.setdefault(pid, e)

    rows = []
    for pid, e in entries.items():
        p = e.get("player", {}) or {}
        stats = p.get("stats", []) or []
        proj, proj_gp, proj_avg = split(stats, f"{PROJECTED}{season}", rules.scoring)
        now, now_gp, now_avg = split(stats, f"{SEASON}{season}", rules.scoring)
        last, last_gp, last_avg = split(stats, f"{SEASON}{season - 1}", rules.scoring)
        l15, l15_gp, _ = split(stats, f"{LAST15}{season}", rules.scoring)
        fppg = blend(proj, last, last_gp, now, now_gp, l15, l15_gp)
        if now_gp >= 5:
            line, source = _line(now_avg), "season"
        elif proj_avg:
            line, source = _line(proj_avg), "projection"
        elif last_avg:
            line, source = _line(last_avg), "last season"
        else:
            line, source = {}, ""

        slots = [SLOT[s] for s in p.get("eligibleSlots", []) or []
                 if s in SLOT and SLOT[s] not in RESERVE]
        positions: list[str] = [x for x in ("PG", "SG", "SF", "PF", "C") if x in slots]
        team_id = int(p.get("proTeamId") or 0)
        team = pro.get(team_id)
        own = p.get("ownership", {}) or {}
        mine = owner.get(pid)
        injury = str(p.get("injuryStatus") or "ACTIVE")
        rows.append(DraftRow(
            sport="nba", ext_id=str(pid), name=str(p.get("fullName") or ""),
            team=team.abbrev if team else "",
            positions=positions or [POS.get(int(p.get("defaultPositionId") or 0), "")],
            primary_pos=POS.get(int(p.get("defaultPositionId") or 0), positions[0] if positions else ""),
            proj_points=fppg,
            adp=round(_num(own.get("averageDraftPosition")), 1),
            injury_status=injury,
            owner=str(mine[0].id) if mine else "",
            owner_name=mine[0].name if mine else "",
            available=mine is None,
            raw={
                "proTeamId": team_id, "slots": slots, "status": str(e.get("status") or ""),
                "fppg": fppg, "fppgProj": proj, "projGames": proj_gp,
                "fppgNow": now, "gpNow": now_gp, "fppgLast": last, "gpLast": last_gp,
                "fppgL15": l15, "gpL15": l15_gp,
                "line": line, "lineSource": source, "injury": injury,
                "pctOwned": round(_num(own.get("percentOwned")), 1),
                "pctStarted": round(_num(own.get("percentStarted")), 1),
                "pctChange": round(_num(own.get("percentChange")), 1),
                "ownerTeamId": mine[0].id if mine else None,
                "ownerName": mine[0].name if mine else "",
                "slot": mine[1] if mine else "",
                "droppable": p.get("droppable") is not False,
            },
        ))
    rows.sort(key=lambda r: -r.proj_points)
    return rows
