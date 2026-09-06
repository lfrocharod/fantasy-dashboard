"""FantasyPros expert consensus rankings + tiers (scraped from the cheatsheet
page's embedded `var ecrData = {...}`)."""

from __future__ import annotations

import json
import re

import httpx

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
_PAGE = {
    "ppr": "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
    "half": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
    "standard": "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
}
_RE = re.compile(r"var ecrData\s*=\s*(\{.*?\});", re.DOTALL)


def fetch(scoring: str = "ppr") -> list[dict]:  # pragma: no cover - network
    url = _PAGE.get(scoring, _PAGE["ppr"])
    with httpx.Client(headers={"User-Agent": _UA}, timeout=30, follow_redirects=True) as c:
        html = c.get(url).text
    m = _RE.search(html)
    if not m:
        raise RuntimeError("FantasyPros: ecrData not found (page layout changed?)")
    return json.loads(m.group(1)).get("players", [])


def index_by_name(rows: list[dict]) -> dict[str, dict]:
    """key -> record, key = normalised name."""
    from ..sources.domestic_xg import normalise

    out: dict[str, dict] = {}
    for r in rows:
        out[normalise(r.get("player_name", ""))] = r
    return out
