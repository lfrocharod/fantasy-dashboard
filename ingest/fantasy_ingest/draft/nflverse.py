"""Usage data (snap share, target share, opportunity) from nflverse.

nflverse publishes per-week CSVs as versioned GitHub release assets — stable
URLs, documented columns, no rate limits, no key. We pull two:

  snap_counts        -> offense_pct per player per game
  stats_player_week  -> targets / target_share / wopr / carries per player per week

Everything here is best-effort: a 404 (season not released yet) or a parse
problem returns an empty dict and the caller carries on.
"""

from __future__ import annotations

import csv
import io
import unicodedata

import httpx

_REL = "https://github.com/nflverse/nflverse-data/releases/download"
_UA = {"User-Agent": "Mozilla/5.0"}

# nflverse team abbreviations that differ from ESPN's
_TEAM_FIX = {"LA": "LAR", "LV": "LV", "WAS": "WSH", "JAC": "JAX"}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ")
    # drop common suffixes so "Michael Pittman Jr" == "Michael Pittman"
    toks = [t for t in s.split() if t not in ("jr", "sr", "ii", "iii", "iv", "v")]
    return " ".join(toks)


def _team(abbr: str) -> str:
    a = (abbr or "").upper()
    return _TEAM_FIX.get(a, a)


def _get_csv(url: str) -> list[dict]:
    try:
        r = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            return []
        return list(csv.DictReader(io.StringIO(r.text)))
    except Exception:  # noqa: BLE001
        return []


def _f(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def fetch_usage(season: int, last_n: int = 4) -> dict[tuple[str, str], dict]:
    """{(normalised_name, team_abbr): {...usage...}} over the last `last_n` games.

    Keys:
      snap_pct     mean offensive snap share (0..1)
      snap_trend   last game's snap share minus the prior mean (rising / falling)
      target_share mean team target share (0..1)
      wopr         mean weighted opportunity rating (~0..0.9, pass-catchers)
      touches      mean carries + receptions per game
      games        games counted
    """
    snaps = _get_csv(f"{_REL}/snap_counts/snap_counts_{season}.csv")
    weekly = _get_csv(f"{_REL}/stats_player/stats_player_week_{season}.csv")
    if not snaps and not weekly:
        return {}

    # snap share per (player, team) -> [(week, pct), ...]
    snap_log: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for row in snaps:
        key = (_norm(row.get("player", "")), _team(row.get("team", "")))
        wk = int(_f(row.get("week")))
        snap_log.setdefault(key, []).append((wk, _f(row.get("offense_pct"))))

    use_log: dict[tuple[str, str], list[dict]] = {}
    for row in weekly:
        key = (_norm(row.get("player_display_name") or row.get("player_name", "")),
               _team(row.get("team") or row.get("recent_team", "")))
        use_log.setdefault(key, []).append({
            "week": int(_f(row.get("week"))),
            "target_share": _f(row.get("target_share")),
            "wopr": _f(row.get("wopr")),
            "touches": _f(row.get("carries")) + _f(row.get("receptions")),
        })

    out: dict[tuple[str, str], dict] = {}
    keys = set(snap_log) | set(use_log)
    for key in keys:
        rec: dict = {"games": 0}
        sl = sorted(snap_log.get(key, []), key=lambda x: x[0])[-last_n:]
        if sl:
            pcts = [p for _w, p in sl]
            rec["snap_pct"] = round(sum(pcts) / len(pcts), 3)
            rec["snap_trend"] = round(pcts[-1] - (sum(pcts[:-1]) / max(1, len(pcts) - 1)), 3)
            rec["games"] = max(rec["games"], len(sl))
        ul = sorted(use_log.get(key, []), key=lambda x: x["week"])[-last_n:]
        if ul:
            n = len(ul)
            rec["target_share"] = round(sum(u["target_share"] for u in ul) / n, 3)
            rec["wopr"] = round(sum(u["wopr"] for u in ul) / n, 3)
            rec["touches"] = round(sum(u["touches"] for u in ul) / n, 1)
            rec["games"] = max(rec["games"], n)
        if rec["games"]:
            out[key] = rec
    return out


norm_name = _norm  # public alias for cross-module name matching

__all__ = ["fetch_usage", "norm_name"]
