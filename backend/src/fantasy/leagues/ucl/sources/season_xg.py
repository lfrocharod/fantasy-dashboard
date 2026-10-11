"""Season non-penalty xG / xA per 90 for **every** Champions League player, from
Sofascore's per-competition league-statistics endpoints.

The Understat layer (`sources/domestic_xg.py`) only covers the big-5 leagues, so
players at Sporting, PSV, Ajax, Celtic, Bodø/Glimt, Qarabağ … had no xGI at all.
Sofascore tracks xG for essentially every league a CL club plays in, and its
league-statistics endpoint returns the whole table in a handful of paged calls
(~110 requests total, disk-cached) rather than one call per player.

Output: {uefa_player_id: PlayerStat(scope="combined", …)} ready to upsert.
"""

from __future__ import annotations

import time

from rapidfuzz import fuzz

from fantasy.leagues.ucl.mapping.coverage import LOW_MINUTES, NO_NAME_MATCH, NO_STAT_ROW, XgCoverage
from fantasy.leagues.ucl.sources.recent_form import _build_squad_index, normalise
from fantasy.leagues.ucl.sources.sofascore import SofaClient, SofaError
from fantasy.leagues.ucl.types import PlayerStat

# A penalty is worth ~0.79 xG; subtract taken pens to approximate non-penalty xG
# so these line up with the Understat npxG values.
_PEN_XG = 0.79

_FIELDS = (
    "expectedGoals,expectedAssists,minutesPlayed,totalShots,"
    "appearances,matchesStarted,penaltiesTaken"
)


def _f(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _resolve_entry(
    name: str, idx: dict, idx_keys: list[str], force_name: str = ""
) -> dict | None:
    """Find a player in the Sofascore squad index by name. `force_name` (from a
    `player_id_overrides` row) is tried first and, if present, exactly."""
    if force_name:
        return idx.get(normalise(force_name))
    nn = normalise(name)
    entry = idx.get(nn)
    if entry is not None:
        return entry
    # surname fuzzy fallback: "Luis Suarez" <-> "Luis Javier Suarez", "Vinicius"
    # <-> "Vinicius Jr".
    toks = nn.split()
    surname = toks[-1] if toks else nn
    cand = [
        (k, fuzz.token_sort_ratio(nn, k))
        for k in idx_keys
        if surname in k and abs(len(k.split()) - len(toks)) <= 1
    ]
    cand.sort(key=lambda x: -x[1])
    if cand and cand[0][1] >= 84:
        return idx[cand[0][0]]
    return None


def _league_seasons(client: SofaClient, ss_team_ids: set[int], log) -> dict[int, int]:
    """{uniqueTournamentId: currentSeasonId} for the leagues these clubs play in."""
    out: dict[int, int] = {}
    for tid in ss_team_ids:
        try:
            t = (client.get(f"/team/{tid}", allow_404=True) or {}).get("team", {})
        except SofaError:
            continue
        ut = (t.get("primaryUniqueTournament") or {}).get("id")
        if not ut or ut in out:
            continue
        try:
            seas = (client.get(f"/unique-tournament/{ut}/seasons", allow_404=True) or {}).get(
                "seasons", []
            )
        except SofaError:
            continue
        if seas:
            out[ut] = seas[0]["id"]
    log(f"  season-xG: resolved {len(out)} leagues from {len(ss_team_ids)} clubs")
    return out


def _league_table(client: SofaClient, ut: int, season: int, log) -> dict[int, dict]:
    """{ss_player_id: stat row} for a whole league season, paged."""
    out: dict[int, dict] = {}
    offset = 0
    for _page in range(15):  # safety cap ~1500 players
        url = (
            f"/unique-tournament/{ut}/season/{season}/statistics"
            f"?limit=100&offset={offset}&accumulation=total&order=-minutesPlayed"
            f"&fields={_FIELDS}"
        )
        try:
            d = client.get(url, allow_404=True) or {}
        except SofaError as e:
            log(f"  season-xG ut{ut} page {offset // 100}: {e}")
            break
        res = d.get("results", []) or []
        for r in res:
            pid = (r.get("player") or {}).get("id")
            if pid:
                out[int(pid)] = r
        pages = d.get("pages") or 1
        offset += 100
        if not res or offset >= pages * 100:
            break
    return out


def fetch_season_xg(
    uefa_players,
    team_names: dict[int, str],
    *,
    min_price: float = 0.0,
    delay: float = 0.5,
    overrides: dict[int, tuple[str, str]] | None = None,
    log=print,
) -> tuple[dict[int, PlayerStat], XgCoverage]:  # pragma: no cover - network
    """Returns ({uefa_player_id: PlayerStat}, coverage). `overrides` maps a
    uefa_player_id to (force_name, force_team) — the `player_id_overrides` rows —
    to pin a player the fuzzy match keeps missing."""
    overrides = overrides or {}
    cov = XgCoverage(source="sofascore-season")
    client = SofaClient(delay=delay)
    try:
        idx = _build_squad_index(client, team_names, log, deadline=time.time() + 300)
    except SofaError as e:
        log(f"  season-xG: squad index failed ({e})")
        return {}, cov
    if not idx:
        return {}, cov

    ss_team_ids = {v["ss_team_id"] for v in idx.values() if v.get("ss_team_id")}
    leagues = _league_seasons(client, ss_team_ids, log)
    by_ssid: dict[int, dict] = {}
    for ut, season in leagues.items():
        by_ssid.update(_league_table(client, ut, season, log))
    log(f"  season-xG: {len(by_ssid)} player rows across {len(leagues)} leagues")

    idx_keys = list(idx.keys())
    out: dict[int, PlayerStat] = {}
    for p in uefa_players:
        if p.price < min_price:
            continue
        cov.total += 1
        team = team_names.get(p.team_id, "")
        force_name = (overrides.get(p.uefa_player_id) or ("", ""))[0]
        entry = _resolve_entry(p.name, idx, idx_keys, force_name)
        if entry is None:
            cov.miss(p.uefa_player_id, p.name, team, p.price, NO_NAME_MATCH)
            continue
        r = by_ssid.get(entry["ss_id"])
        if not r:
            cov.miss(p.uefa_player_id, p.name, team, p.price, NO_STAT_ROW)
            continue
        mins = _f(r.get("minutesPlayed"))
        if mins < 90:
            cov.miss(p.uefa_player_id, p.name, team, p.price, LOW_MINUTES)
            continue
        f90 = mins / 90.0
        npxg = max(0.0, _f(r.get("expectedGoals")) - _f(r.get("penaltiesTaken")) * _PEN_XG)
        app = int(_f(r.get("appearances")) or round(f90))
        out[p.uefa_player_id] = PlayerStat(
            player_id=p.uefa_player_id,
            scope="combined",
            minutes=round(mins, 1),
            matches=app,
            npxg90=round(npxg / f90, 4),
            xag90=round(_f(r.get("expectedAssists")) / f90, 4),
            shots90=round(_f(r.get("totalShots")) / f90, 4),
            sca90=0.0,
            source="sofascore-season",
        )
        cov.hit()
    log("  " + cov.summary_line())
    return out, cov
