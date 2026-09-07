"""Your FPL Draft mini-league: ownership (free-agent map), standings, draft
history, and your current squad.

Most endpoints on draft.premierleague.com are readable without auth. The
`pl_profile` cookie is only needed for a specific team's live squad
(`entry/{id}/event/{gw}`) and your own transactions.
"""

from __future__ import annotations

import httpx

_BASE = "https://draft.premierleague.com/api"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"


def _client(cookie: str | None = None) -> httpx.Client:
    cookies = {}
    if cookie:
        # accept either a bare pl_profile value or a full "a=b; c=d" cookie string
        if "=" in cookie:
            for part in cookie.split(";"):
                if "=" in part:
                    k, _, v = part.strip().partition("=")
                    cookies[k] = v
        else:
            cookies["pl_profile"] = cookie
    return httpx.Client(headers={"User-Agent": _UA}, cookies=cookies, timeout=30,
                        follow_redirects=True)


def _get(c: httpx.Client, path: str) -> dict:
    r = c.get(f"{_BASE}/{path}")
    r.raise_for_status()
    return r.json()


def league_details(client: httpx.Client, league_id: str) -> dict:
    return _get(client, f"league/{league_id}/details")


def fetch_ownership(client: httpx.Client, league_id: str, cookie: str | None
                    ) -> tuple[dict[int, int], dict[int, str]]:
    """-> ({element_id: owner_entry_id}, {owner_entry_id: manager/team name})."""
    det = league_details(client, league_id)
    names = {
        e["entry_id"]: (e.get("entry_name")
                        or f"{e.get('player_first_name','')} {e.get('player_last_name','')}".strip())
        for e in det.get("league_entries", []) if e.get("entry_id")
    }
    es = _get(client, f"league/{league_id}/element-status").get("element_status", [])
    owned = {row["element"]: row["owner"] for row in es if row.get("owner")}
    return owned, names


def parse_standings(det: dict) -> list[dict]:
    by_le = {}
    by_le_entry = {}
    for e in det.get("league_entries", []):
        nm = (e.get("entry_name")
              or f"{e.get('player_first_name','')} {e.get('player_last_name','')}".strip())
        by_le[e["id"]] = nm
        by_le_entry[e["id"]] = e.get("entry_id")
    out = []
    for s in det.get("standings", []):
        le = s.get("league_entry")
        out.append({
            "league_entry": le,
            "entry_id": by_le_entry.get(le),
            "name": by_le.get(le, str(le)),
            "rank": s.get("rank"),
            "total": s.get("total"),
            "points_for": s.get("points_for") or s.get("event_total"),
            "points_against": s.get("points_against"),
            "w": s.get("matches_won"), "d": s.get("matches_drawn"), "l": s.get("matches_lost"),
        })
    return out


def parse_choices(client: httpx.Client, league_id: str) -> list[dict]:
    ch = _get(client, f"draft/{league_id}/choices").get("choices", [])
    return [{
        "overall": c.get("index") or c.get("pick"),
        "round": c.get("round", 0),
        "pick_in_round": c.get("pick", 0),
        "team_id": c.get("entry", 0),
        "team_name": c.get("entry_name", ""),
        "player_ext_id": c.get("element"),
        "source": "fpl",
    } for c in ch if c.get("element")]


def fetch_my_squad(client: httpx.Client, entry_id: str, gw: int) -> list[dict]:
    """Needs the pl_profile cookie for a team that isn't yours to be visible;
    yours is always visible when authenticated."""
    d = _get(client, f"entry/{entry_id}/event/{gw}")
    return d.get("picks", []) or []
