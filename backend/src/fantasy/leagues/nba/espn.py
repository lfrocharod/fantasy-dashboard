"""ESPN Fantasy Basketball API: league, players and the NBA schedule.

The league endpoints need the account's `espn_s2` / `SWID` cookies for a
private league — the same ESPN login the NFL module uses, so NBA falls back to
those when it has none of its own. Player and schedule data are public.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"

LEAGUE_VIEWS = (
    "mSettings", "mTeam", "mRoster", "mMatchup", "mMatchupScore", "mSchedule", "mStatus",
    "mNav", "mDraftDetail",
)


def client(espn_s2: str | None = None, swid: str | None = None) -> httpx.Client:
    cookies = {}
    if espn_s2 and swid:
        cookies = {"espn_s2": espn_s2, "SWID": swid if swid.startswith("{") else "{" + swid + "}"}
    return httpx.Client(headers={"User-Agent": _UA}, cookies=cookies, timeout=45, follow_redirects=True)


def fetch_league(c: httpx.Client, season: int, league_id: str) -> dict[str, Any]:  # pragma: no cover - network
    r = c.get(f"{BASE}/{season}/segments/0/leagues/{league_id}",
              params=[("view", v) for v in LEAGUE_VIEWS])
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    return data


def fetch_players(
    c: httpx.Client, season: int, league_id: str | None = None, limit: int = 500
) -> list[dict[str, Any]]:  # pragma: no cover - network
    """The player pool, most-owned first, with ESPN's projections, last and
    this season's stats. In a league context each carries `onTeamId`."""
    fltr = {"players": {
        "limit": limit,
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        "filterStatsForTopScoringPeriodIds": {
            "value": 2, "additionalValue": [f"00{season}", f"10{season}", f"00{season - 1}", f"02{season}"],
        },
    }}
    where = f"leagues/{league_id}" if league_id else "leaguedefaults/1"
    r = c.get(f"{BASE}/{season}/segments/0/{where}", params={"view": "kona_player_info"},
              headers={"X-Fantasy-Filter": json.dumps(fltr)})
    r.raise_for_status()
    players: list[dict[str, Any]] = r.json().get("players", [])
    return players


def fetch_pro_schedule(c: httpx.Client, season: int) -> dict[str, Any]:  # pragma: no cover - network
    """Every NBA team and its games (by scoring period = day)."""
    r = c.get(f"{BASE}/{season}", params={"view": "proTeamSchedules_wl"})
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    return data
