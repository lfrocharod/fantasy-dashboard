"""Parsers for UEFA Champions League Fantasy feed JSON.

Shapes below are the real 2026 feeds (competition id 90). The public feeds
(players / teams / fixtures) are confirmed; the authed ones (my-team, leagues,
standings) are best-effort tolerant parsers keyed through `_pick`, since their
exact keys are only visible once the session cookie is in place.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser

from fantasy.leagues.ucl.types import Fixture, LeagueEntry, Player, Position, SquadPick, Team

# UEFA's Fantasy feeds emit *naive* wall-clock times in their own timezone
# (Nyon / Zurich — CET in winter, CEST in summer). Treat them as such, not UTC,
# or every kickoff and deadline is off by an hour or two.
_UEFA_TZ = ZoneInfo("Europe/Zurich")

_SKILL_TO_POS: dict[int, Position] = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _pick(d: dict, *names: str, default: Any = None) -> Any:
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return default


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _opt_i(v: Any) -> int | None:
    return _i(v) if v not in (None, "", " ") else None


def unwrap(data: Any, *keys: str, depth: int = 0) -> Any:
    """Return data['data']['value'][…] style nested content, tolerating shape drift."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and depth < 6:
        for k in keys:
            if k in data:
                got = unwrap(data[k], *keys, depth=depth + 1)
                if got not in (None, [], {}):
                    return got
        for v in data.values():
            if isinstance(v, (dict, list)):
                got = unwrap(v, *keys, depth=depth + 1)
                if isinstance(got, list) and got:
                    return got
    return data if isinstance(data, list) else []


_LIST_KEYS = ("data", "value", "playerList", "players", "list", "rest", "leaderBoardList")


def _rows(feed: Any) -> list[dict]:
    v = feed
    if isinstance(feed, dict):
        v = feed.get("data", feed)
        if isinstance(v, dict):
            v = v.get("value", v)
    if isinstance(v, list):
        return v
    return unwrap(feed, *_LIST_KEYS)


def _dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        d = dateparser.parse(str(v))
    except (ValueError, OverflowError):
        return None
    if d is None:
        return None
    # naive -> it's Zurich wall-clock; normalise everything to UTC for storage
    if d.tzinfo is None:
        d = d.replace(tzinfo=_UEFA_TZ)
    return d.astimezone(UTC)


# --------------------------------------------------------------------------


def parse_teams(feed: Any) -> dict[int, Team]:
    out: dict[int, Team] = {}
    for r in _rows(feed):
        tid = _i(_pick(r, "id", "tId", "teamId"))
        if not tid:
            continue
        out[tid] = Team(
            uefa_team_id=tid,
            name=str(_pick(r, "webName", "offName", "shortName", "tName", default=f"Team {tid}")),
            code=str(_pick(r, "countryCode", "cCode", "shortName", default="")),
        )
    return out


def parse_players(feed: Any) -> tuple[list[Player], dict[int, Team]]:
    players: list[Player] = []
    teams: dict[int, Team] = {}
    # per player: (penalty attempts signal, goals) — used after the loop to rank
    # each club's likely first-choice penalty taker.
    pen_signal: dict[int, tuple[float, int]] = {}
    raw_minutes: dict[int, float] = {}  # uefa_player_id -> UEFA-competition minutes
    for r in _rows(feed):
        pid = _i(_pick(r, "id", "pId", "playerId"))
        if not pid:
            continue
        tid = _i(_pick(r, "tId", "teamId"))
        if tid and tid not in teams:
            teams[tid] = Team(
                uefa_team_id=tid,
                name=str(_pick(r, "tName", default=f"Team {tid}")),
                code=str(_pick(r, "cCode", default="")),
            )

        is_active = _i(_pick(r, "isActive", default=1))
        p_status = str(_pick(r, "pStatus", default="")).strip()
        q_status = str(_pick(r, "qStatus", default="")).strip()
        if is_active == 0:
            status_code, detail = 2, "not active"
        elif p_status and p_status not in ("0",):
            status_code, detail = (2 if p_status in ("2", "3") else 1), p_status
        elif q_status and q_status not in ("0",):
            status_code, detail = 1, "doubt"
        else:
            status_code, detail = 0, ""

        price = _f(_pick(r, "value", "price"))
        last_pts = _i(_pick(r, "totPts", "totalPoints"))
        last_mins = _f(_pick(r, "minsPlyd", "minutesPlayed"))
        t_in = _f(_pick(r, "mTransferIn", "transferIn"))
        t_out = _f(_pick(r, "mTransferOut", "transferOut"))
        net = t_in - t_out
        momentum = round(math.tanh(net / 8000.0), 3)
        pos = _SKILL_TO_POS.get(_i(_pick(r, "skill")), "MID")
        # `uefa_form` carries a reference *points-per-90*. UEFA's `avgPlayerPts`
        # is points-per-*appearance* off a tiny (often pre-season) sample, so it
        # runs hot — shrink every estimate toward the price-based prior and cap
        # it, or cheap defenders with one good cameo dominate the projections.
        cur_avg = _f(_pick(r, "avgPlayerPts", "pForm"))
        prior = _price_prior(price, pos)
        if last_mins >= 360 and last_pts > 0:
            raw = last_pts / (last_mins / 90.0)
            ppg = 0.70 * raw + 0.30 * prior
        elif last_mins >= 90 and last_pts > 0:
            raw = last_pts / (last_mins / 90.0)
            ppg = 0.45 * raw + 0.55 * prior
        elif cur_avg > 0:
            ppg = 0.35 * cur_avg + 0.65 * prior
        else:
            ppg = prior
        ppg = min(ppg, prior * 1.8 + 1.0)

        # Penalty-taker signal from last season: missing a penalty is near-proof
        # you were on them; scored pens (`pS`) too where the feed carries it.
        pens_missed = _f(_pick(r, "pM", "penaltyMiss"))
        pens_scored = _f(_pick(r, "pS", "penaltyScored"))
        goals = _i(_pick(r, "gS", "goalsScored"))
        pen_signal[pid] = (pens_missed * 2.0 + pens_scored * 2.0, goals)

        # Live matchday state: `curGDPts` is points banked so far this matchday,
        # `isPlayed`/`teamPlayed` whether they've featured. Both are 0 outside a
        # live/finished matchday, so we only trust them when a fixture says so.
        live_pts_raw = _pick(r, "curGDPts", "gdPoints", "gdPts")
        live_played = bool(
            _i(_pick(r, "isPlayed", "isplayed", default=0))
            or _i(_pick(r, "teamPlayed", "teamPlyd", default=0))
        )

        players.append(
            Player(
                uefa_player_id=pid,
                name=str(_pick(r, "latinName", "pFName", "pDName", "pName", default=f"Player {pid}")),
                team_id=tid,
                position=pos,
                price=price,
                uefa_total_points=last_pts,
                uefa_form=round(ppg, 2),
                selected_pct=_f(_pick(r, "selPer", "selectedBy")),
                price_momentum=momentum,
                status_code=status_code,
                status_detail=detail,
                live_points=_opt_i(live_pts_raw),
                live_played=live_played,
            )
        )
        raw_minutes[pid] = last_mins

    _mark_penalty_takers(players, pen_signal)
    _set_minutes_prior(players, raw_minutes)
    return players, teams


def _set_minutes_prior(players: list[Player], raw_minutes: dict[int, float]) -> None:
    """Turn each player's UEFA-competition minutes into a 0..1 start-probability
    prior, normalised against a near-ever-present at the same club (the 3rd-most-
    played squad member, so one freak total can't set the bar). Covers every
    player with zero scraping; the Sofascore recent-form scrape overrides it
    where we have it. If the feed carries no minutes yet (very start of a
    season) every prior is 0 and the model falls back as before."""
    by_club: dict[int, list[float]] = {}
    for p in players:
        by_club.setdefault(p.team_id, []).append(raw_minutes.get(p.uefa_player_id, 0.0))
    club_ref: dict[int, float] = {}
    for tid, arr in by_club.items():
        top = sorted(arr, reverse=True)
        ref = top[2] if len(top) >= 3 else (top[0] if top else 0.0)
        # floor so an early-knockout club (few games played) doesn't inflate
        # every squad member toward "nailed".
        club_ref[tid] = max(ref, 900.0)
    for p in players:
        rm = raw_minutes.get(p.uefa_player_id, 0.0)
        ref = club_ref.get(p.team_id, 0.0)
        p.minutes_prior = round(min(1.0, rm / ref), 3) if ref > 0 and rm > 0 else 0.0


def _mark_penalty_takers(players: list[Player], pen_signal: dict[int, tuple[float, int]]) -> None:
    """Best-guess first-choice penalty taker per club: whoever has direct penalty
    evidence (missed/scored one), breaking ties on goals scored. Only a hint —
    the `set_piece_roles` override table is the source of truth."""
    by_club: dict[int, list[Player]] = {}
    for p in players:
        by_club.setdefault(p.team_id, []).append(p)
    for squad in by_club.values():
        ranked = sorted(
            squad,
            key=lambda p: (pen_signal.get(p.uefa_player_id, (0.0, 0))[0],
                           pen_signal.get(p.uefa_player_id, (0.0, 0))[1]),
            reverse=True,
        )
        if not ranked:
            continue
        top = ranked[0]
        sig, _g = pen_signal.get(top.uefa_player_id, (0.0, 0))
        if sig > 0:
            top.set_piece = "PK"
            if len(ranked) > 1 and pen_signal.get(ranked[1].uefa_player_id, (0.0, 0))[0] > 0:
                ranked[1].set_piece = "PK2"


def _price_prior(price: float, pos: Position) -> float:
    """Rough expected UCL-fantasy points per 90 for a player with no recent
    sample, from their price (€4m floor, €13m ceiling)."""
    base = max(0.0, price - 4.0)
    slope = {"GK": 0.35, "DEF": 0.45, "MID": 0.60, "FWD": 0.65}[pos]
    floor = {"GK": 2.6, "DEF": 2.4, "MID": 2.2, "FWD": 2.0}[pos]
    return floor + base * slope


@dataclass(slots=True)
class MatchdayInfo:
    matchday: int
    deadline: datetime | None
    is_current: bool
    # in-matchday substitutions the game allows, and how many roll over
    subs_allowed: int = 3
    subs_carry: int = 0


def parse_fixtures(
    feed: Any, fallback_md: int = 1
) -> tuple[list[Fixture], dict[int, Team], list[MatchdayInfo]]:
    fixtures: list[Fixture] = []
    teams: dict[int, Team] = {}
    md_info: list[MatchdayInfo] = []

    for md in _rows(feed):
        md_id = _i(_pick(md, "mdId", "matchday", "gameday"), fallback_md)
        md_info.append(
            MatchdayInfo(
                matchday=md_id,
                deadline=_dt(_pick(md, "deadline")),
                # tri-state: 2 = already played, 1 = the open matchday, 0 = future.
                # Only 1 is "current" — truthiness would flag every finished MD too.
                is_current=_i(_pick(md, "mdIsCurrent", "gdIsCurrent")) == 1,
                subs_allowed=_i(_pick(md, "subsAllowed", "subAllowed"), 3) or 3,
                subs_carry=_i(_pick(md, "maxSubsCf", "subsCf", "subCarryFwd"), 0),
            )
        )
        for m in md.get("match", []) if isinstance(md, dict) else []:
            mid = _i(_pick(m, "mId", "matchId", "id"))
            if not mid:
                continue
            ht, at = _i(_pick(m, "htId")), _i(_pick(m, "atId"))
            for tid, nm, cc in (
                (ht, _pick(m, "htName", default=f"Team {ht}"), _pick(m, "htCCode", default="")),
                (at, _pick(m, "atName", default=f"Team {at}"), _pick(m, "atCCode", default="")),
            ):
                if tid and tid not in teams:
                    teams[tid] = Team(uefa_team_id=tid, name=str(nm), code=str(cc))
            status_raw = str(_pick(m, "matchStatus", default="0"))
            status = (
                "finished" if status_raw in ("2", "3")
                else "live" if _i(_pick(m, "isLive")) or status_raw == "1"
                else "upcoming"
            )
            fixtures.append(
                Fixture(
                    uefa_match_id=mid,
                    matchday=md_id,
                    home_team_id=ht,
                    away_team_id=at,
                    kickoff=_dt(_pick(m, "dateTime", "dateTimeLock")),
                    status=status,
                    home_goals=_opt_i(_pick(m, "htScore")),
                    away_goals=_opt_i(_pick(m, "atScore")),
                )
            )
    return fixtures, teams, md_info


def parse_my_team(payload: Any, matchday: int) -> tuple[list[SquadPick], float]:
    val = payload
    if isinstance(payload, dict):
        val = payload.get("data", payload)
        if isinstance(val, dict) and isinstance(val.get("value"), dict):
            val = val["value"]
    rows = []
    bank = 0.0
    if isinstance(val, dict):
        rows = val.get("playerid") or val.get("teamPlayers") or val.get("players") or []
        bank = _f(_pick(val, "teamBalance", "budget", "bank"))
    elif isinstance(val, list):
        rows = val

    picks: list[SquadPick] = []
    for r in rows:
        pid = _i(_pick(r, "id", "playerId", "pId"))
        if not pid:
            continue
        bench = _i(_pick(r, "benchposition", "benchOrder", "playerPosition"))
        on_bench = bench >= 12 or (0 < bench <= 4 and "benchposition" in r)
        picks.append(
            SquadPick(
                player_id=pid,
                is_starter=not on_bench,
                is_captain=bool(_i(_pick(r, "iscaptain", "isCaptain"))),
                is_vice=bool(_i(_pick(r, "isvicecaptain", "isViceCaptain", "isvicecpt"))),
                bench_order=bench if on_bench else 0,
                purchase_price=_f(_pick(r, "value", "buyValue", "purchasePrice")),
                is_played=bool(_i(_pick(r, "isplayed", "isPlayed", default=0))),
            )
        )
    return picks, bank


def parse_private_leagues(payload: Any) -> list[dict]:
    """-> [{id, name, code, memberCount}]"""
    out = []
    for r in _rows(payload):
        lid = _pick(r, "leagueId", "id", "lId")
        if lid is None:
            continue
        out.append(
            {
                "id": str(lid),
                "name": str(_pick(r, "leagueName", "name", "lName", default="")),
                "code": str(_pick(r, "leagueCode", "code", "lCode", default="")).upper(),
                "memberCount": _i(_pick(r, "memberCount", "members", "totalMembers")),
            }
        )
    return out


def league_rows(payload: Any) -> tuple[list[dict], int | None]:
    """(rows, total members) from a leaderboard page. The site's payload
    splits rows into `initial` and `rest`; older shapes are a plain list."""
    v = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(v, dict):
        v = v.get("value", v)
    if isinstance(v, dict) and ("rest" in v or "initial" in v):
        rows, seen = [], set()
        for r in [*(v.get("initial") or []), *(v.get("rest") or [])]:
            key = str(_pick(r, "guid", "userGuid", "socialId", default=id(r)))
            if isinstance(r, dict) and key not in seen:
                seen.add(key)
                rows.append(r)
        total = v.get("totalMembers") or v.get("totUserNew")
        return rows, int(total) if str(total or "").isdigit() else None
    return _rows(payload), None


def parse_league_standings(payload: Any, matchday: int) -> list[LeagueEntry]:
    entries: list[LeagueEntry] = []
    rows = payload if isinstance(payload, list) else league_rows(payload)[0]
    for r in rows:
        entry_id = str(
            _pick(r, "guid", "userGuid", "entryId", "userId", "gameEntryId", "socialId", default="")
        )
        if not entry_id:
            continue
        entries.append(
            LeagueEntry(
                entry_id=entry_id,
                manager_name=str(
                    _pick(r, "fullName", "memberName", "userName", "managerName", default="")
                ),
                team_name=str(_pick(r, "teamName", "tName", "userTeamName", default="")),
                matchday=matchday,
                points=_i(_pick(r, "currentGamedayPoints", "gdPoints", "gamedayPoints",
                                "matchdayPoints", "points", "mdPoints")),
                total_points=_i(_pick(r, "overallPoints", "totPoints", "totalPoints", "ovPoints")),
                rank=_i(_pick(r, "rank", "overallRank", "ovRank", "position")),
                prev_rank=_i(_pick(r, "previousRank", "prevRank", "lastRank")),
            )
        )
    return entries


def current_matchday(md_info: Iterable[MatchdayInfo], default: int = 1) -> int:
    cur = [m for m in md_info if m.is_current]
    if cur:
        return cur[0].matchday
    future = sorted(
        (m for m in md_info if m.deadline and m.deadline > datetime.now(UTC)),
        key=lambda m: m.deadline,  # type: ignore[arg-type,return-value]
    )
    if future:
        return future[0].matchday
    allmd = [m.matchday for m in md_info]
    return max(allmd) if allmd else default


# Back-compat shim for run.py / tests that still import unwrap_list.
def unwrap_list(data: Any, keys: tuple[str, ...]) -> list[dict]:
    got = unwrap(data, *keys)
    return got if isinstance(got, list) else []
