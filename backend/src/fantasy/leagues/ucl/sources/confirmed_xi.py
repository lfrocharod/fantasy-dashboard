"""Confirmed starting XIs for the matchday, from UEFA's own match centre.

uefa.com publishes each side's starting XI and bench about an hour before
kick-off, under the same match and player ids UEFA Fantasy uses, so nothing
has to be matched by name. Once a lineup is out it's ground truth: the
projection model defers to it completely (a nailed 95%-start player who's on
the bench is a 0, not a 0.95).

`fetch_confirmed_xi` returns `{uefa_player_id: "start" | "bench"}` for every
player named in a published lineup. Players in matches whose lineups aren't
out yet are simply absent (the model keeps its own number for them).

(This used Sofascore, matched by name, until Sofascore started refusing the
app outright.)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

MATCH_API = "https://match.uefa.com/v5/matches"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
# `lineupStatus` before a team sheet is out; anything else names the real XI
_NOT_OUT = frozenset({"", "NOT_AVAILABLE"})


def parse_lineups(data: dict[str, Any]) -> dict[int, str]:
    """{player id: "start" | "bench"} from one match's lineups payload, or {}
    while the team sheets aren't out. A side without a full XI is skipped."""
    if str(data.get("lineupStatus") or "") in _NOT_OUT:
        return {}
    out: dict[int, str] = {}
    for side in ("homeTeam", "awayTeam"):
        team = data.get(side) or {}
        field = team.get("field") or []
        if len(field) < 11:
            continue
        for rows, role in ((field, "start"), (team.get("bench") or [], "bench")):
            for row in rows:
                pid = str((row.get("player") or {}).get("id") or "")
                if pid.isdigit():
                    out[int(pid)] = role
    return out


def fetch_confirmed_xi(
    fixtures: Iterable[Any],
    *,
    client: httpx.Client | None = None,
    log: Callable[[str], None] = print,
) -> dict[int, str]:
    """`fixtures`: the matchday's Fixture rows still to finish (their
    `uefa_match_id` is uefa.com's match id)."""
    c = client or httpx.Client(headers={"User-Agent": _UA}, timeout=20, follow_redirects=True)
    out: dict[int, str] = {}
    published = 0
    try:
        for f in fixtures:
            try:
                r = c.get(f"{MATCH_API}/{f.uefa_match_id}/lineups")
                r.raise_for_status()
                got = parse_lineups(r.json())
            except (httpx.HTTPError, ValueError) as e:
                log(f"  confirmed XI: match {f.uefa_match_id} unavailable ({type(e).__name__})")
                continue
            if got:
                published += 1
                out.update(got)
    finally:
        if client is None:
            c.close()
    starters = sum(1 for v in out.values() if v == "start")
    log(f"  confirmed XI: {published} lineup(s) out — {starters} starters, "
        f"{len(out) - starters} on the bench")
    return out


def within_matchday_window(fixtures, *, hours_before: float = 26.0, hours_after: float = 3.5) -> bool:
    """Only worth asking while a fixture is imminent or live."""
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
