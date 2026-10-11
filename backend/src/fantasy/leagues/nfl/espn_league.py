"""Your specific ESPN league: roster rules (mSettings) and live draft picks
(mDraftDetail). Needs the espn_s2 + SWID cookies from a logged-in browser."""

from __future__ import annotations

import httpx

from fantasy.leagues.draft.types import ESPN_SLOT

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"


def _client(espn_s2: str, swid: str) -> httpx.Client:
    swid = swid if swid.startswith("{") else "{" + swid + "}"
    return httpx.Client(
        headers={"User-Agent": _UA},
        cookies={"espn_s2": espn_s2, "SWID": swid},
        timeout=30,
        follow_redirects=True,
    )


def fetch_league(year: int, league_id: str, espn_s2: str, swid: str) -> dict:  # pragma: no cover
    with _client(espn_s2, swid) as c:
        r = c.get(
            f"{BASE}/{year}/segments/0/leagues/{league_id}",
            params=[("view", "mSettings"), ("view", "mDraftDetail"), ("view", "mTeam")],
        )
        r.raise_for_status()
        return r.json()


def parse_settings(data: dict) -> dict:
    s = data.get("settings", {})
    roster = s.get("rosterSettings", {}).get("lineupSlotCounts", {})
    slots: dict[str, int] = {}
    for slot_id, n in roster.items():
        label = ESPN_SLOT.get(int(slot_id), None)
        if label and n and label not in ("BE", "IR"):
            slots[label] = slots.get(label, 0) + int(n)
    bench = int(roster.get("20", 0))
    scoring_items = s.get("scoringSettings", {}).get("scoringItems", [])
    ppr = next((i.get("points", 0) for i in scoring_items if i.get("statId") == 53), 0)  # receptions
    scoring = "ppr" if ppr >= 0.9 else "half" if ppr >= 0.4 else "standard"
    return {
        "roster": slots,
        "bench": bench,
        "teams": s.get("size") or len(data.get("teams", []) or []) or 12,
        "scoring": scoring,
        "name": s.get("name", ""),
    }


def parse_picks(data: dict, my_team_id: int | None = None) -> list[dict]:
    draft = data.get("draftDetail", {})
    picks = draft.get("picks", []) or []
    out: list[dict] = []
    for p in picks:
        # Pre-draft, ESPN pre-creates every slot with playerId -1 / 0.
        if not p.get("playerId") or int(p.get("playerId", 0)) <= 0:
            continue
        out.append(
            {
                "overall": p.get("overallPickNumber") or p.get("pickNumber") or (len(out) + 1),
                "round": p.get("roundId", 0),
                "pick_in_round": p.get("roundPickNumber", 0),
                "team_id": p.get("teamId", 0),
                "team_name": "",
                "player_ext_id": p["playerId"],
                "is_mine": my_team_id is not None and p.get("teamId") == my_team_id,
                "source": "espn",
            }
        )
    names = {t.get("id"): (t.get("name") or f"Team {t.get('id')}") for t in data.get("teams", [])}
    for o in out:
        o["team_name"] = names.get(o["team_id"], "")
    return out
