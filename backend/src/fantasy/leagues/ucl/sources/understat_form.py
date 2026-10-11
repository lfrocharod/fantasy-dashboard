"""Understat form fallback (domestic leagues only).

Used when RECENT_FORM_SOURCE=understat, or as a backstop if Sofascore is
unreachable. Also powers the offline `--samples` path via aggregate_match_rows().
"""

from __future__ import annotations

from collections import Counter

from fantasy.leagues.ucl.sources.recent_form import (  # canonical dataclass + name norm
    FormRow,
    normalise,
)

_ROLE = {
    "GK": "GK",
    "DL": "DEF", "DC": "DEF", "DR": "DEF", "D": "DEF",
    "DML": "MID", "DMC": "MID", "DMR": "MID", "DM": "MID",
    "ML": "MID", "MC": "MID", "MR": "MID", "M": "MID",
    "AML": "MID", "AMC": "MID", "AMR": "MID", "AM": "MID",
    "FWL": "FWD", "FW": "FWD", "FWR": "FWD", "F": "FWD", "FR": "FWD", "FL": "FWD",
}
_BENCH = {"sub", "substitute", "s", ""}


def _num(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _col(df, *cands: str):
    lower = {str(c).lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def aggregate_match_rows(records: list[dict], last_n: int = 5) -> list[FormRow]:
    """records: dicts with player, team, date, minutes, pos, goals, assists,
    npxg, xa, shots. Groups by (player, team), keeps the last `last_n`."""
    records = sorted(records, key=lambda r: (r.get("player", ""), r.get("date", "")))
    logs: dict[tuple[str, str], list[dict]] = {}
    meta: dict[tuple[str, str], tuple[str, str]] = {}
    for r in records:
        key = (normalise(r.get("player", "")), normalise(r.get("team", "")))
        logs.setdefault(key, []).append(r)
        meta[key] = (r.get("player", ""), r.get("team", ""))

    out: list[FormRow] = []
    for key, entries in logs.items():
        e = entries[-last_n:]
        started = [x for x in e if str(x.get("pos", "")).lower() not in _BENCH]
        roles = Counter(_ROLE[str(x["pos"]).upper()] for x in started if _ROLE.get(str(x["pos"]).upper()))
        mins = sum(_num(x.get("minutes")) for x in e)
        fr = FormRow(
            name=meta[key][0], norm_name=key[0], team=meta[key][1], norm_team=key[1],
            role=roles.most_common(1)[0][0] if roles else "",
            recent_matches=len(e), recent_starts=len(started),
            recent_minutes=round(mins, 1),
            recent_goals=sum(_num(x.get("goals")) for x in e),
            recent_assists=sum(_num(x.get("assists")) for x in e),
            recent_npxg=round(sum(_num(x.get("npxg")) for x in e), 2),
            recent_xa=round(sum(_num(x.get("xa")) for x in e), 2),
            recent_shots=sum(_num(x.get("shots")) for x in e),
        )
        if mins > 0:
            fr.season_npxg90 = fr.recent_npxg / (mins / 90.0)
            fr.season_xa90 = fr.recent_xa / (mins / 90.0)
            fr.season_minutes = mins
        out.append(fr)
    return out


def fetch_form_rows(leagues: list[str], season: str | None, last_n: int = 5) -> list[FormRow]:  # pragma: no cover
    import soccerdata as sd

    us = sd.Understat(leagues=leagues, seasons=[season] if season else None)
    m = us.read_player_match_stats().reset_index()
    cmap = {k: _col(m, *v) for k, v in {
        "player": ("player", "player_name"), "team": ("team", "team_title"),
        "date": ("date", "game_date", "game"), "minutes": ("time", "minutes"),
        "pos": ("position",), "goals": ("goals",), "assists": ("assists",),
        "npxg": ("npxg", "npxG"), "xa": ("xa", "xA"), "shots": ("shots",),
    }.items()}
    recs = [
        {out_k: (row[src] if src else "") for out_k, src in cmap.items()}
        for _, row in m.iterrows()
    ]
    return aggregate_match_rows(recs, last_n)
