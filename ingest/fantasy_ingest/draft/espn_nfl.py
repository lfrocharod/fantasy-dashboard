"""ESPN fantasy football player universe + season projections.

Public endpoint (no cookies): the "leaguedefaults/3" player pool. Cookies are
only needed for a specific league's settings / live draft picks (espn_league.py).
"""

from __future__ import annotations

import json

import httpx

from .types import ESPN_POS, ESPN_SLOT, DraftRow

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"


def _filter(limit: int, offset: int) -> str:
    return json.dumps(
        {
            "players": {
                "limit": limit,
                "offset": offset,
                "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "PPR"},
                "filterStatsForSourceIds": {"value": [0, 1]},
            }
        }
    )


def fetch_players(year: int, *, total: int = 450, page: int = 150) -> list[dict]:  # pragma: no cover - network
    out: list[dict] = []
    with httpx.Client(headers={"User-Agent": _UA}, timeout=40, follow_redirects=True) as c:
        for offset in range(0, total, page):
            r = c.get(
                f"{BASE}/{year}/segments/0/leaguedefaults/3",
                params={"view": "kona_player_info", "scoringPeriodId": 0},
                headers={"x-fantasy-filter": _filter(page, offset)},
            )
            r.raise_for_status()
            batch = r.json().get("players", [])
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page:
                break
    return out


def _season_proj(stats: list[dict], year: int) -> float:
    for s in stats or []:
        if (
            s.get("seasonId") == year
            and s.get("statSourceId") == 1  # projected
            and s.get("statSplitTypeId") == 0  # whole season
        ):
            return round(float(s.get("appliedTotal") or 0), 1)
    return 0.0


def parse(players: list[dict], year: int) -> list[DraftRow]:
    rows: list[DraftRow] = []
    for e in players:
        p = e.get("player", e)
        pid = p.get("id")
        if pid is None:
            continue
        eligible = [ESPN_SLOT.get(s, "") for s in p.get("eligibleSlots", [])]
        positions = [x for x in eligible if x in ("QB", "RB", "WR", "TE", "K", "DST")]
        primary = ESPN_POS.get(p.get("defaultPositionId"), positions[0] if positions else "")
        own = p.get("ownership") or {}
        ranks = p.get("draftRanksByRankType") or {}
        ppr = ranks.get("PPR") or {}
        rows.append(
            DraftRow(
                sport="nfl",
                ext_id=str(pid),
                name=p.get("fullName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip(),
                team=_PRO_TEAM.get(p.get("proTeamId"), ""),
                positions=positions or ([primary] if primary else []),
                primary_pos=primary,
                proj_points=_season_proj(p.get("stats", []), year),
                adp=round(float(own.get("averageDraftPosition") or 0), 1),
                provider_rank=ppr.get("rank"),
                injury_status=(p.get("injuryStatus") or "").replace("_", " ").title()
                if p.get("injured")
                else "",
                outlook=(p.get("seasonOutlook") or "")[:600],
                raw={"auctionValue": ppr.get("auctionValue"), "pctOwned": own.get("percentOwned")},
            )
        )
    return rows


_PRO_TEAM = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
    17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}
