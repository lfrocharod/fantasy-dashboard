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
_SCORE_SLUG = {"ppr": "ppr", "half": "half-point-ppr", "standard": "standard"}


def _scrape(url: str) -> list[dict]:  # pragma: no cover - network
    with httpx.Client(headers={"User-Agent": _UA}, timeout=30, follow_redirects=True) as c:
        html = c.get(url).text
    m = _RE.search(html)
    if not m:
        raise RuntimeError(f"FantasyPros: ecrData not found at {url}")
    return json.loads(m.group(1)).get("players", [])


def fetch(scoring: str = "ppr") -> list[dict]:  # pragma: no cover - network
    return _scrape(_PAGE.get(scoring, _PAGE["ppr"]))


def fetch_weekly(scoring: str, week: int) -> list[dict]:  # pragma: no cover - network
    """This week's expert-consensus ranks for every position: the flex page
    covers RB/WR/TE only, so the QB, K and DST pages are read too. A page that
    fails just leaves its position without the experts' view."""
    slug = _SCORE_SLUG.get(scoring, "ppr")
    rows: list[dict] = []
    for page in (f"{slug}-flex", "qb", "k", "dst"):
        try:
            rows += _scrape(f"https://www.fantasypros.com/nfl/rankings/{page}.php?week={week}")
        except (httpx.HTTPError, RuntimeError, ValueError):
            continue
    if not rows:
        raise RuntimeError(f"FantasyPros: no weekly rankings for week {week}")
    return rows


def fetch_ros(scoring: str) -> list[dict]:  # pragma: no cover - network
    """Rest-of-season overall expert-consensus ranks."""
    slug = _SCORE_SLUG.get(scoring, "ppr")
    return _scrape(f"https://www.fantasypros.com/nfl/rankings/ros-{slug}-overall.php")


def index_by_name(rows: list[dict]) -> dict[str, dict]:
    """key -> record, key = normalised name."""
    from fantasy.core.text import normalise

    out: dict[str, dict] = {}
    for r in rows:
        out[normalise(r.get("player_name", ""))] = r
    return out
