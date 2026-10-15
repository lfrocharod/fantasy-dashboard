"""Your FPL Draft mini-league: ownership (free-agent map), standings, draft
history, and your current squad.

Most endpoints on draft.premierleague.com are readable without auth. The
`pl_profile` cookie is only needed for a specific team's live squad
(`entry/{id}/event/{gw}`) and your own transactions.
"""

from __future__ import annotations

import re

import httpx

_BASE = "https://draft.premierleague.com/api"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def split_auth(blob: str | None) -> tuple[str, str | None]:
    """Pull a cookie string and/or a Bearer token out of whatever the user
    pasted — a bare token, a `Bearer …` value, an `x-api-authorization:` line,
    a `Cookie:` header, or a whole `curl` command copied from DevTools.

    Returns (cookie_string, bearer_token). FPL's account API now authenticates
    with the Bearer token (from `x-api-authorization`), not a session cookie.
    """
    if not blob:
        return "", None
    s = blob.strip()

    bearer = None
    m = re.search(r"[Bb]earer\s+(" + _JWT_RE.pattern + r")", s)
    if m:
        bearer = m.group(1)
    elif _JWT_RE.fullmatch(s):
        bearer = s

    cookie = ""
    # curl copies the cookie jar as  -b '...'  or  --cookie '...'
    cm = re.search(r"(?:-b|--cookie)\s+'([^']+)'", s) or re.search(r'(?:-b|--cookie)\s+"([^"]+)"', s)
    if cm:
        cookie = cm.group(1)
    else:
        hm = re.search(r"[Cc]ookie:\s*([^\r\n']+)", s)
        if hm:
            cookie = hm.group(1).strip()
        elif "=" in s and ";" in s and "\n" not in s and "curl" not in s:
            cookie = s  # looks like a bare "a=b; c=d" string
    return cookie, bearer


def _client(auth: str | None = None) -> httpx.Client:
    cookie_str, bearer = split_auth(auth)
    cookies = {}
    for part in cookie_str.split(";"):
        if "=" in part:
            k, _, v = part.strip().partition("=")
            cookies[k] = v
    headers = {"User-Agent": _UA}
    if bearer:
        headers["x-api-authorization"] = f"Bearer {bearer}"
    return httpx.Client(headers=headers, cookies=cookies, timeout=30, follow_redirects=True)


def has_auth(auth: str | None) -> bool:
    """True when the pasted blob carries a usable Bearer token."""
    return split_auth(auth)[1] is not None


def _get(c: httpx.Client, path: str) -> dict:
    url = f"{_BASE}/{path}"
    r = c.get(url)
    if r.status_code in (401, 403) and ("x-api-authorization" in c.headers or c.cookies):
        # A request carrying an expired login is refused even by the public
        # endpoints, and the token only lasts hours: ask again without it.
        with _client() as anon:
            r = anon.get(url)
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


def _picks_to_lineup(picks: list[dict], source: str) -> list[dict]:
    out = []
    for p in picks or []:
        if not p.get("element"):
            continue
        slot = int(p.get("position") or 0)
        out.append({
            "element": p["element"],
            "slot": slot,
            "starter": 1 <= slot <= 11,
            "captain": bool(p.get("is_captain")),
            "vice": bool(p.get("is_vice_captain")),
            "source": source,
        })
    out.sort(key=lambda x: x["slot"] or 99)
    return out


def fetch_gw_lineup(client: httpx.Client, entry_id: str, gw: int) -> list[dict]:
    """The lineup you fielded in gameweek `gw`, the one that scores it: [] if
    FPL won't show it (before the deadline, or not to this session)."""
    try:
        d = _get(client, f"entry/{entry_id}/event/{gw}")
    except (httpx.HTTPError, ValueError):
        return []
    return _picks_to_lineup(d.get("picks", []), f"event/{gw}")


def fetch_my_squad(
    client: httpx.Client, entry_id: str, next_gw: int, authed: bool, log=lambda _m: None
) -> list[dict]:
    """The lineup you set on FPL's "Pick Team" tab.

    Each pick: element id, `position` 1-15 (1-11 = the starting XI in the
    formation you chose, 12-15 = bench order), and captain / vice flags.

    With a logged-in Bearer token we read `entry/{id}/my-team` — the LIVE
    editable team for the upcoming gameweek, i.e. exactly what Pick Team shows.
    Without one the API only exposes completed gameweeks, so we fall back to the
    most recent one you actually fielded.
    """
    if authed:
        try:
            d = _get(client, f"entry/{entry_id}/my-team")
            lu = _picks_to_lineup(d.get("picks", []), "my-team")
            if lu:
                return lu
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                log("  my-team: 401/403 — the token is missing or expired. Copy a "
                    "fresh one (DevTools -> Network -> an api/ request -> "
                    "x-api-authorization: Bearer ...) into Settings. Using last "
                    "fielded XI for now.")
        except Exception:  # noqa: BLE001,S110
            pass
    for gw in (next_gw, next_gw - 1, next_gw - 2):
        if gw < 1:
            continue
        try:
            d = _get(client, f"entry/{entry_id}/event/{gw}")
        except Exception:  # noqa: BLE001,S112
            continue
        lu = _picks_to_lineup(d.get("picks", []), f"event/{gw}")
        if lu:
            return lu
    return []
