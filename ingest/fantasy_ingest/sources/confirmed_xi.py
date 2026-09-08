"""Confirmed starting XIs for the upcoming matchday, from Sofascore.

Sofascore publishes a predicted lineup days out and flips it to
`confirmed: true` ~an hour before kick-off. Once confirmed it's ground truth —
the projection model should defer to it completely (a nailed 95%-start player
who's on the bench is a 0, not a 0.95).

`fetch_confirmed_xi` returns `{uefa_player_id: "start" | "bench"}` for every
player named in a *confirmed* lineup for the given fixtures. Players in matches
without a confirmed lineup yet are simply absent (the model keeps its own
number for them).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..model.club_strength import SS_TEAM_ID
from .recent_form import normalise
from .sofascore import SofaClient, SofaError

_UCL_UT_ID = 7  # Sofascore uniqueTournament id for the Champions League


def _pick_event(events: list[dict], opp_ss_id: int, kickoff: datetime | None) -> dict | None:
    """The Sofascore event that is this fixture: same opponent, near the same
    date, Champions League where the field is present."""
    ko_ts = kickoff.timestamp() if kickoff else None
    for e in events:
        ht = (e.get("homeTeam") or {}).get("id")
        at = (e.get("awayTeam") or {}).get("id")
        if opp_ss_id not in (ht, at):
            continue
        ut = ((e.get("tournament") or {}).get("uniqueTournament") or {}).get("id")
        if ut and ut != _UCL_UT_ID:
            continue
        if ko_ts is not None:
            ts = e.get("startTimestamp") or 0
            if abs(ts - ko_ts) > 3 * 86400:
                continue
        return e
    return None


def _index_players(players, team_id: int) -> dict:
    exact: dict[str, object] = {}
    sur: dict[str, list] = {}
    for p in players:
        if p.team_id != team_id:
            continue
        nn = normalise(p.name)
        exact[nn] = p
        toks = nn.split()
        if toks:
            sur.setdefault(toks[-1], []).append(p)
    return {"exact": exact, "sur": sur}


def _resolve(idx: dict, ss_name: str):
    nn = normalise(ss_name)
    if not nn:
        return None
    hit = idx["exact"].get(nn)
    if hit is not None:
        return hit
    toks = nn.split()
    cands = idx["sur"].get(toks[-1] if toks else nn, [])
    if len(cands) == 1:
        return cands[0]
    # surname shared: try to disambiguate on a first-initial / first-name token
    if toks and len(cands) > 1:
        for c in cands:
            ct = normalise(c.name).split()
            if ct and toks[0] and (ct[0] == toks[0] or ct[0][0] == toks[0][0]):
                return c
    return None


def fetch_confirmed_xi(
    fixtures,
    players,
    team_names: dict[int, str],
    *,
    only_confirmed: bool = True,
    delay: float = 0.4,
    log=print,
) -> dict[int, str]:  # pragma: no cover - network
    """`fixtures`: the upcoming matchday's Fixture rows. Returns
    {uefa_player_id: "start"|"bench"} for players in confirmed lineups."""
    client = SofaClient(delay=delay, ttl_hours=2.0)
    idx_by_team: dict[int, dict] = {}

    out: dict[int, str] = {}
    n_conf = 0
    for fx in fixtures:
        h_ss = SS_TEAM_ID.get(fx.home_team_id)
        a_ss = SS_TEAM_ID.get(fx.away_team_id)
        if not h_ss or not a_ss:
            continue
        try:
            events = client.team_events_next(h_ss) + client.team_events_last(h_ss)
        except SofaError as e:
            log(f"  confirmed XI: events for {team_names.get(fx.home_team_id, h_ss)} failed ({e})")
            continue
        ev = _pick_event(events, a_ss, fx.kickoff)
        if not ev or not ev.get("id"):
            continue
        try:
            lu = client.event_lineups(int(ev["id"]), fresh=True)
        except SofaError as e:
            log(f"  confirmed XI: lineups {ev['id']} failed ({e})")
            continue
        if not lu:
            continue
        if only_confirmed and not lu.get("confirmed"):
            continue
        n_conf += 1
        for side, tid in (("home", fx.home_team_id), ("away", fx.away_team_id)):
            idx = idx_by_team.get(tid) or idx_by_team.setdefault(tid, _index_players(players, tid))
            for row in (lu.get(side) or {}).get("players", []):
                p = _resolve(idx, (row.get("player") or {}).get("name") or "")
                if p is None:
                    continue
                out[p.uefa_player_id] = "bench" if row.get("substitute") else "start"

    starters = sum(1 for v in out.values() if v == "start")
    log(f"  confirmed XI: {n_conf} confirmed lineup(s) — {starters} starters, "
        f"{len(out) - starters} benched")
    return out


def within_matchday_window(fixtures, *, hours_before: float = 26.0, hours_after: float = 3.5) -> bool:
    """Only worth the ~40 Sofascore calls when a fixture is imminent or live."""
    now = datetime.now(UTC)
    for f in fixtures:
        ko = f.kickoff
        if not ko:
            continue
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=UTC)
        h = (ko - now).total_seconds() / 3600.0
        if -hours_after <= h <= hours_before:
            return True
    return False
