"""Parsers for UEFA Champions League Fantasy feed JSON.

Shapes below are the real 2026 feeds (competition id 90). The public feeds
(players / teams / fixtures) are confirmed; the authed ones (my-team, leagues,
standings) are best-effort tolerant parsers keyed through `_pick`, since their
exact keys are only visible once the session cookie is in place.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dateutil import parser as dateparser

from ..types import Fixture, LeagueEntry, Player, Position, SquadPick, Team

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
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (ValueError, OverflowError):
        return None


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

        players.append(
            Player(
                uefa_player_id=pid,
                name=str(_pick(r, "latinName", "pFName", "pDName", "pName", default=f"Player {pid}")),
                team_id=tid,
                position=_SKILL_TO_POS.get(_i(_pick(r, "skill")), "MID"),
                price=_f(_pick(r, "value", "price")),
                uefa_total_points=_i(_pick(r, "totPts", "totalPoints")),
                # No "form" field in the feed; season points-per-match is the closest.
                uefa_form=_f(_pick(r, "avgPlayerPts", "lastGdPoints")),
                selected_pct=_f(_pick(r, "selPer", "selectedBy")),
                status_code=status_code,
                status_detail=detail,
            )
        )
    return players, teams


@dataclass(slots=True)
class MatchdayInfo:
    matchday: int
    deadline: datetime | None
    is_current: bool


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
                is_current=bool(_i(_pick(md, "mdIsCurrent", "gdIsCurrent"))),
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


def parse_league_standings(payload: Any, matchday: int) -> list[LeagueEntry]:
    entries: list[LeagueEntry] = []
    for r in _rows(payload):
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
                points=_i(_pick(r, "gdPoints", "matchdayPoints", "points", "mdPoints")),
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
