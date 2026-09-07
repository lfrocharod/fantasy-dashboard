"""In-season NFL: current rosters, weekly + rest-of-season projections, matchup
ratings, schedule and standings from the ESPN Fantasy API (+ FantasyPros weekly
and ROS expert-consensus ranks).

Reuses the draft cookies. Writes a `draft_players` board (sport=nfl) whose `raw`
carries the in-season fields, plus `draft.nfl.*` settings for schedule /
standings / my roster / current week.
"""

from __future__ import annotations

import httpx

from ..sources.domestic_xg import normalise
from . import espn_nfl, fantasypros
from .types import ESPN_POS, ESPN_SLOT, DraftRow

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"

# NFL team id -> (pass-defence, rush-defence) generosity multipliers, mean ~1.0.
# >1 = gives up more fantasy points than average (good to attack). Eyeballed
# pre-season; refined by live results as the season goes (see blend_dvp).
NFL_DEF: dict[int, tuple[float, float]] = {
    1: (1.05, 1.10), 2: (0.95, 0.92), 3: (0.90, 0.95), 4: (1.02, 1.08), 5: (1.10, 1.05),
    6: (0.98, 1.00), 7: (1.05, 1.02), 8: (1.00, 0.95), 9: (0.92, 0.90), 10: (1.08, 1.10),
    11: (1.00, 1.05), 12: (0.95, 0.98), 13: (1.02, 1.00), 14: (1.05, 1.08), 15: (1.10, 1.12),
    16: (1.05, 1.02), 17: (1.08, 1.10), 18: (1.00, 0.95), 19: (0.90, 0.88), 20: (1.05, 1.05),
    21: (0.95, 0.92), 22: (1.08, 1.05), 23: (1.00, 1.02), 24: (0.92, 0.95), 25: (1.05, 1.10),
    26: (0.95, 0.90), 27: (1.10, 1.08), 28: (1.02, 1.00), 29: (0.98, 0.95), 30: (1.05, 1.05),
    33: (1.08, 1.10), 34: (1.00, 0.98),
}
_POS_USES_RUSH = {"RB"}


def _client(espn_s2: str, swid: str) -> httpx.Client:
    swid = swid if swid.startswith("{") else "{" + swid + "}"
    return httpx.Client(headers={"User-Agent": _UA}, cookies={"espn_s2": espn_s2, "SWID": swid},
                        timeout=45, follow_redirects=True)


def _num(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def fetch_league(year: int, league_id: str, espn_s2: str, swid: str) -> dict:  # pragma: no cover - network
    with _client(espn_s2, swid) as c:
        r = c.get(
            f"{_BASE}/{year}/segments/0/leagues/{league_id}",
            params=[("view", v) for v in
                    ("mSettings", "mTeam", "mRoster", "mMatchup", "mStatus")],
        )
        r.raise_for_status()
        return r.json()


def _team_name(t: dict) -> str:
    return t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or f"Team {t.get('id')}"


def parse_league(data: dict) -> dict:
    status = data.get("status", {})
    week = status.get("currentMatchupPeriod") or status.get("latestScoringPeriod") or 1
    sett = data.get("settings", {})
    ss = sett.get("scheduleSettings", {})
    reg = int(ss.get("matchupPeriodCount") or 14)
    rounds = 2 if (ss.get("playoffTeamCount") or 4) <= 4 else 3
    playoff_weeks = list(range(reg + 1, reg + 1 + rounds))

    slots: dict[str, int] = {}
    for sid, n in sett.get("rosterSettings", {}).get("lineupSlotCounts", {}).items():
        lbl = ESPN_SLOT.get(int(sid))
        if lbl and n and lbl not in ("BE", "IR"):
            slots[lbl] = slots.get(lbl, 0) + int(n)

    teams = {t["id"]: _team_name(t) for t in data.get("teams", [])}

    rosters: dict[int, list[int]] = {}
    slot_of: dict[int, int] = {}
    owner_of: dict[int, int] = {}
    for t in data.get("teams", []):
        for e in t.get("roster", {}).get("entries", []) or []:
            pid = e.get("playerId") or e.get("playerPoolEntry", {}).get("id")
            if not pid:
                continue
            rosters.setdefault(t["id"], []).append(pid)
            slot_of[pid] = e.get("lineupSlotId")
            owner_of[pid] = t["id"]

    schedule = []
    for m in data.get("schedule", []) or []:
        h, a = m.get("home", {}).get("teamId"), m.get("away", {}).get("teamId")
        if h and a:
            schedule.append({
                "week": m.get("matchupPeriodId"),
                "home": h, "away": a,
                "home_name": teams.get(h, ""), "away_name": teams.get(a, ""),
                "home_pts": round(_num(m.get("home", {}).get("totalPoints")), 1),
                "away_pts": round(_num(m.get("away", {}).get("totalPoints")), 1),
                "winner": m.get("winner"),
            })

    return {
        "week": int(week), "reg_weeks": reg, "playoff_weeks": playoff_weeks,
        "slots": slots, "teams": teams,
        "rosters": rosters, "slot_of": slot_of, "owner_of": owner_of,
        "schedule": schedule,
    }


def parse_standings(data: dict) -> list[dict]:
    out = []
    for t in data.get("teams", []):
        rec = t.get("record", {}).get("overall", {})
        out.append({
            "team_id": t["id"], "name": _team_name(t),
            "wins": rec.get("wins", 0), "losses": rec.get("losses", 0), "ties": rec.get("ties", 0),
            "pf": round(_num(rec.get("pointsFor")), 1), "pa": round(_num(rec.get("pointsAgainst")), 1),
            "streak": rec.get("streakLength", 0), "streak_type": rec.get("streakType", ""),
        })
    return sorted(out, key=lambda r: (-r["wins"], -r["pf"]))


def _weekly_proj(player: dict, week: int) -> float:
    for s in player.get("stats", []) or []:
        if s.get("scoringPeriodId") == week and s.get("statSourceId") == 1:
            return round(_num(s.get("appliedTotal")), 1)
    return 0.0


def _pro_schedule(year: int, weeks: list[int]) -> dict[int, dict[str, tuple[str, bool]]]:  # pragma: no cover - network
    """{week: {team_abbr: (opponent_abbr, is_home)}} from the public scoreboard.
    The site API 403s on a full desktop UA — a short one gets through."""
    out: dict[int, dict[str, tuple[str, bool]]] = {}
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=20, follow_redirects=True) as c:
        for wk in weeks:
            ev = []
            for _try in range(3):
                try:
                    r = c.get(
                        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
                        params={"week": wk, "seasontype": 2, "year": year},
                    )
                    if r.status_code == 200:
                        ev = r.json().get("events", [])
                        break
                except Exception:  # noqa: BLE001,S110
                    pass
            if not ev:
                continue
            wm: dict[str, tuple[str, bool]] = {}
            for e in ev:
                comp = (e.get("competitions") or [{}])[0]
                cs = comp.get("competitors", [])
                if len(cs) != 2:
                    continue
                h = next((x for x in cs if x.get("homeAway") == "home"), cs[0])
                a = next((x for x in cs if x.get("homeAway") == "away"), cs[1])
                ha, aa = h["team"]["abbreviation"], a["team"]["abbreviation"]
                wm[ha] = (aa, True)
                wm[aa] = (ha, False)
            out[wk] = wm
    return out


def _matchup_rating(opp_abbr: str, uses_rush: bool, sched_ids: dict[str, int]) -> tuple[str, int]:
    """(opponent abbr display, 1 easy … 5 hard) from the static defence prior."""
    oid = sched_ids.get(opp_abbr)
    pa, ra = NFL_DEF.get(oid or -1, (1.0, 1.0))
    gen = ra if uses_rush else pa  # >1 = generous defence = good matchup
    raw = (gen - 1.0)
    fdr = max(1, min(5, round(3 - raw * 9)))  # generous D -> low number (easy)
    return opp_abbr, fdr


def build(year: int, league_id: str, espn_s2: str, swid: str, scoring: str,
          my_team_id: int | None) -> tuple[list[DraftRow], dict]:  # pragma: no cover - network
    lg = fetch_league(year, league_id, espn_s2, swid)
    L = parse_league(lg)
    standings = parse_standings(lg)
    week = L["week"]

    raw_players = espn_nfl.fetch_players(year, total=500, page=200)
    sched = _pro_schedule(year, list(range(week, week + 4)))
    abbr_to_id = {v: k for k, v in _PRO_ABBR.items()}

    # FantasyPros weekly + ROS ranks
    fp_week, fp_ros = {}, {}
    try:
        fp_week = _fp_index(fantasypros.fetch_weekly(scoring, week))
    except Exception as e:  # noqa: BLE001
        print(f"[draft] FP weekly skipped: {e}", flush=True)
    try:
        fp_ros = _fp_index(fantasypros.fetch_ros(scoring))
    except Exception as e:  # noqa: BLE001
        print(f"[draft] FP ROS skipped: {e}", flush=True)

    weeks_left = max(1, L["reg_weeks"] - week + 1)
    rows: list[DraftRow] = []
    for pe in raw_players:
        p = pe.get("player", pe)
        pid = p.get("id")
        pos = ESPN_POS.get(p.get("defaultPositionId"), "")
        if not pid or pos not in ("QB", "RB", "WR", "TE", "K", "DST"):
            continue
        name = p.get("fullName", "")
        pro_team = p.get("proTeamId")
        own = p.get("ownership", {}) or {}
        season_proj = espn_nfl._season_proj(p.get("stats", []), year)
        espn_wk = _weekly_proj(p, week)
        wk_proj = espn_wk or round(season_proj / 17.0, 1)
        rec_w = fp_week.get(normalise(name))
        rec_r = fp_ros.get(normalise(name))
        if rec_w and _num(rec_w.get("rank_ecr")):
            wk_proj = round(0.6 * wk_proj + 0.4 * _rank_to_pts(int(_num(rec_w["rank_ecr"])), pos), 1)
        # ROS: reconcile ESPN's season projection with the (FP-blended) weekly
        # rate — ESPN's two numbers often disagree, and the weekly one carries
        # the expert-consensus signal.
        ros_from_season = season_proj * weeks_left / 17.0 if season_proj else 0.0
        ros_from_week = wk_proj * weeks_left * 0.95  # slight taper for byes/injuries
        ros_proj = round(max(ros_from_season, ros_from_week) if ros_from_season else ros_from_week, 1)
        if rec_r and _num(rec_r.get("rank_ecr")):
            ros_proj = round(
                0.55 * ros_proj + 0.45 * _rank_to_pts(int(_num(rec_r["rank_ecr"])), pos) * weeks_left, 1
            )

        bye = p.get("byeWeek") or _bye_for(pro_team)
        team_abbr = _PRO_ABBR.get(pro_team, "")
        uses_rush = pos in _POS_USES_RUSH
        # this week's opponent + a run of the next few weeks' matchups
        wk_opps = []
        for wk in range(week, week + 4):
            m = sched.get(wk, {}).get(team_abbr)
            if wk == bye:
                wk_opps.append({"week": wk, "opp": "BYE", "home": None, "fdr": 0})
            elif m:
                opp, fdr = _matchup_rating(m[0], uses_rush, abbr_to_id)
                wk_opps.append({"week": wk, "opp": opp, "home": m[1], "fdr": fdr})
            else:
                wk_opps.append({"week": wk, "opp": "", "home": None, "fdr": 0})
        this_wk = wk_opps[0]
        rows.append(DraftRow(
            sport="nfl", ext_id=str(pid), name=name, team=team_abbr,
            positions=[pos], primary_pos=pos,
            proj_points=wk_proj, adp=_num(pe.get("draftAuctionValue")) or 0.0,
            provider_rank=int(_num((rec_r or {}).get("rank_ecr"))) or None,
            ecr_rank=int(_num((rec_r or {}).get("rank_ecr"))) or None,
            ecr_tier=int(_num((rec_r or {}).get("tier"))) or None,
            injury_status=p.get("injuryStatus", "ACTIVE"),
            outlook="",
            owner=str(L["owner_of"].get(pid, "")) if L["owner_of"].get(pid) else "",
            owner_name=L["teams"].get(L["owner_of"].get(pid), ""),
            available=pid not in L["owner_of"],
            next_opp=(f"{'vs' if this_wk['home'] else '@'} {this_wk['opp']}"
                      if this_wk["opp"] and this_wk["opp"] not in ("", "BYE") else this_wk["opp"]),
            next_fdr=this_wk["fdr"],
            form=round(own.get("percentOwned", 0.0), 1),
            minutes=0,
            raw={
                "weekProj": wk_proj, "rosProj": ros_proj, "seasonProj": season_proj,
                "bye": bye, "pctOwned": round(own.get("percentOwned", 0.0), 1),
                "pctStarted": round(own.get("percentStarted", 0.0), 1),
                "injury": p.get("injuryStatus", "ACTIVE"),
                "slot": ESPN_SLOT.get(L["slot_of"].get(pid), ""),
                "ownerTeamId": L["owner_of"].get(pid),
                "ownerName": L["teams"].get(L["owner_of"].get(pid), ""),
                "week": week, "onBye": bye == week,
                "matchups": wk_opps, "usesRush": uses_rush,
            },
        ))

    _vor(rows, L["slots"], len(L["teams"]) or 10)
    rows.sort(key=lambda r: (-(r.raw or {}).get("rosProj", 0), -(r.proj_points or 0)))

    meta = {
        "week": week, "reg_weeks": L["reg_weeks"], "playoff_weeks": L["playoff_weeks"],
        "slots": L["slots"], "teams": L["teams"], "schedule": L["schedule"],
        "standings": standings,
        "my_roster": [str(x) for x in L["rosters"].get(my_team_id or -1, [])],
        "my_team_id": my_team_id,
    }
    return rows, meta


def _fp_index(rows: list[dict]) -> dict[str, dict]:
    return {normalise(r.get("player_name", "")): r for r in rows}


def _rank_to_pts(rank: int, pos: str) -> float:
    """Very rough weekly PPR points implied by an overall/flex ECR rank."""
    if rank <= 3:
        base = 22
    elif rank <= 10:
        base = 18
    elif rank <= 24:
        base = 15
    elif rank <= 40:
        base = 12
    elif rank <= 60:
        base = 9
    elif rank <= 100:
        base = 6.5
    else:
        base = 4
    return base * ({"QB": 1.15, "TE": 0.85, "K": 0.5, "DST": 0.5}.get(pos, 1.0))


def _vor(rows: list[DraftRow], slots: dict[str, int], teams: int) -> None:
    by_pos: dict[str, list[DraftRow]] = {}
    for r in rows:
        by_pos.setdefault(r.primary_pos, []).append(r)
    flex = slots.get("FLEX", 0) * teams
    for pos, lst in by_pos.items():
        lst.sort(key=lambda r: -(r.raw or {}).get("rosProj", 0))
        if pos in ("K", "DST"):
            demand = teams * 1.7  # streamed weekly — replacement is well past the starters
        else:
            demand = slots.get(pos, 0) * teams + (
                flex * 0.4 if pos in ("RB", "WR") else flex * 0.2 if pos == "TE" else 0
            )
        idx = max(0, min(len(lst) - 1, round(demand) - 1))
        repl = (lst[idx].raw or {}).get("rosProj", 0.0) if lst else 0.0
        for r in lst:
            r.vbd = round((r.raw or {}).get("rosProj", 0.0) - repl, 1)


_PRO_ABBR = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
    17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}
# 2025/26 bye weeks by proTeamId (fallback when ESPN omits byeWeek)
_BYE = {
    1: 5, 2: 7, 3: 5, 4: 10, 5: 9, 6: 10, 7: 12, 8: 8, 9: 5, 10: 10, 11: 11, 12: 10,
    13: 8, 14: 8, 15: 12, 16: 6, 17: 14, 18: 11, 19: 14, 20: 9, 21: 9, 22: 8, 23: 5,
    24: 12, 25: 14, 26: 8, 27: 9, 28: 12, 29: 14, 30: 8, 33: 7, 34: 6,
}


def _bye_for(pro_team: int | None) -> int:
    return _BYE.get(pro_team or -1, 0)
