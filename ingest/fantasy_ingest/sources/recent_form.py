"""Last-N-matches-overall form for UCL players, from Sofascore (all competitions
— league, UCL, cups, super cups). Produces the same FormRow shape the rest of
the pipeline already consumes.

Efficiency: one squad request per club (transfer + current-role signal), then
per candidate player one "last events" request + one stats request per match in
the window. Everything is disk-cached, so a re-run only pulls new fixtures.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .sofascore import SofaClient, SofaError

# Sofascore position letters -> our buckets
_POS = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}


def _role_of(code: str) -> str:
    return _POS.get((code or "").strip().upper()[:1], "")


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().replace(".", " ").replace("-", " ").split())


@dataclass
class FormRow:
    name: str
    norm_name: str
    team: str
    norm_team: str
    role: str = ""
    season_minutes: float = 0.0
    season_npxg90: float = 0.0
    season_xa90: float = 0.0
    recent_matches: int = 0
    recent_starts: int = 0
    recent_minutes: float = 0.0
    recent_goals: float = 0.0
    recent_assists: float = 0.0
    recent_npxg: float = 0.0
    recent_xa: float = 0.0
    recent_shots: float = 0.0
    avg_rating: float = 0.0
    matches_14d: int = 0
    comps: list[str] = field(default_factory=list)


def _num(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _build_squad_index(client: SofaClient, uefa_teams: dict[int, str], log) -> dict:
    """normalised player name -> {ss_id, pos, ss_team, ss_team_id}.

    `uefa_teams` is {uefa_team_id: name}. We resolve the Sofascore squad from a
    hardcoded id map (search is too unreliable for short UEFA names), falling
    back to search only for a club not in the map.
    """
    from ..model.club_strength import SS_TEAM_ID

    idx: dict[str, dict] = {}
    for uid, name in uefa_teams.items():
        tid = SS_TEAM_ID.get(uid)
        if not tid:
            try:
                tid = client.search_team(name)
            except SofaError:
                tid = None
        if not tid:
            log(f"  no Sofascore team for {name!r} (uefa {uid})")
            continue
        try:
            squad = client.team_players(tid)
        except SofaError as e:
            log(f"  Sofascore squad {name!r} ({tid}) failed: {e}")
            continue
        for row in squad:
            p = row.get("player", {})
            pid = p.get("id")
            if not pid:
                continue
            idx[normalise(p.get("name", ""))] = {
                "ss_id": pid,
                "pos": _POS.get((p.get("position") or "")[:1], ""),
                "ss_team": name,
                "ss_team_id": tid,
            }
    return idx


def _aggregate_player(client: SofaClient, ss_id: int, last_n: int) -> dict:
    ev = client.player_last_events(ss_id)
    events = ev.get("events", []) or []
    now = time.time()
    played = sorted(
        (e for e in events if (e.get("startTimestamp") or 0) < now - 3600),
        key=lambda e: -(e.get("startTimestamp") or 0),
    )[:last_n]
    stat_map = ev.get("statisticsMap", {}) or {}
    team_map = ev.get("playedForTeamMap", {}) or {}

    agg = {
        "matches": 0, "starts": 0, "minutes": 0.0, "goals": 0.0, "assists": 0.0,
        "npxg": 0.0, "xa": 0.0, "shots": 0.0, "rating_sum": 0.0, "rating_n": 0,
        "comps": [], "teams": [], "m14": 0, "roles": [],
    }
    for e in played:
        eid = e["id"]
        comp = e.get("tournament", {}).get("name", "")
        agg["comps"].append(comp)
        agg["teams"].append(team_map.get(str(eid)) or team_map.get(eid))
        if (e.get("startTimestamp") or 0) > now - 14 * 86400:
            agg["m14"] += 1
        s = client.player_match_stats(eid, ss_id) or stat_map.get(str(eid)) or {}
        slot = client.lineup_slot(eid, ss_id) or {}
        mins = _num(s.get("minutesPlayed"))
        agg["matches"] += 1
        agg["minutes"] += mins
        started = not slot.get("substitute", not (mins >= 60))
        if started:
            agg["starts"] += 1
            r = _role_of(slot.get("position", ""))
            if r:
                agg["roles"].append(r)
        agg["goals"] += _num(s.get("goals"))
        agg["assists"] += _num(s.get("goalAssist"))
        agg["npxg"] += _num(s.get("expectedGoals"))  # SS xG excludes penalties already
        agg["xa"] += _num(s.get("expectedAssists"))
        agg["shots"] += _num(s.get("totalShots"))
        if s.get("rating"):
            agg["rating_sum"] += _num(s.get("rating"))
            agg["rating_n"] += 1
    return agg


def fetch_form_rows(
    uefa_players,
    team_names: dict[int, str],
    *,
    last_n: int = 5,
    min_price: float = 4.5,
    log=print,
) -> list[FormRow]:  # pragma: no cover - network
    client = SofaClient()
    squad_idx = _build_squad_index(client, team_names, log)
    log(f"  Sofascore squads: {len(squad_idx)} players across {len(team_names)} clubs")

    rows: list[FormRow] = []
    seen_names = list(squad_idx.keys())
    done = 0
    for p in uefa_players:
        if p.price < min_price:
            continue
        nn = normalise(p.name)
        entry = squad_idx.get(nn)
        if entry is None:
            # fuzzy fallback on surname, but don't let "Gabriel" match "Gabriel X"
            surname = nn.split()[-1] if nn.split() else nn
            ntok = len(nn.split())
            cand = [
                (k, fuzz.token_sort_ratio(nn, k))
                for k in seen_names
                if surname in k and abs(len(k.split()) - ntok) <= 1
            ]
            cand.sort(key=lambda x: -x[1])
            if cand and cand[0][1] >= 84:
                entry = squad_idx[cand[0][0]]
        if entry is None:
            continue
        try:
            agg = _aggregate_player(client, entry["ss_id"], last_n)
        except SofaError as e:
            log(f"  stats failed for {p.name}: {e}")
            continue
        done += 1
        if done % 50 == 0:
            log(f"  … {done} players")
        roles = agg["roles"]
        played_role = max(set(roles), key=roles.count) if roles else entry["pos"]
        fr = FormRow(
            name=p.name, norm_name=nn, team=entry["ss_team"], norm_team=normalise(entry["ss_team"]),
            role=played_role,
            recent_matches=agg["matches"], recent_starts=agg["starts"],
            recent_minutes=round(agg["minutes"], 1), recent_goals=agg["goals"],
            recent_assists=agg["assists"], recent_npxg=round(agg["npxg"], 2),
            recent_xa=round(agg["xa"], 2), recent_shots=agg["shots"],
            avg_rating=round(agg["rating_sum"] / agg["rating_n"], 2) if agg["rating_n"] else 0.0,
            matches_14d=agg["m14"], comps=list(dict.fromkeys(agg["comps"])),
        )
        if fr.recent_minutes > 0:
            fr.season_npxg90 = fr.recent_npxg / (fr.recent_minutes / 90.0)
            fr.season_xa90 = fr.recent_xa / (fr.recent_minutes / 90.0)
            fr.season_minutes = fr.recent_minutes
        rows.append(fr)
    log(f"  Sofascore form: {len(rows)} players")
    return rows
