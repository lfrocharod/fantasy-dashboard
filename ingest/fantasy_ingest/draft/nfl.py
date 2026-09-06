"""Build the NFL draft board: ESPN projections + ADP + FantasyPros ECR/tiers,
merged, with value-based-draft (VBD) points over replacement."""

from __future__ import annotations

from ..sources.domestic_xg import normalise
from . import espn_nfl, fantasypros
from .types import DraftRow

# FLEX demand roughly splits across RB/WR/TE.
_FLEX_SPLIT = {"RB": 0.5, "WR": 0.4, "TE": 0.1}


def build(year: int, scoring: str, roster: dict[str, int], teams: int) -> list[DraftRow]:
    espn_raw = espn_nfl.fetch_players(year)
    rows = espn_nfl.parse(espn_raw, year)
    _merge_fantasypros(rows, scoring)
    _compute_vbd(rows, roster, teams)
    rows.sort(key=lambda r: (-(r.vbd or 0), r.ecr_rank or 9999, -(r.proj_points or 0)))
    return rows


def _merge_fantasypros(rows: list[DraftRow], scoring: str) -> None:
    try:
        fp_rows = fantasypros.fetch(scoring)
    except Exception as e:  # noqa: BLE001
        print(f"[draft] FantasyPros merge skipped: {e}", flush=True)
        return
    fp = fantasypros.index_by_name(fp_rows)
    # surname+team fallback index
    fp_alt = {}
    for r in fp_rows:
        n = normalise(r.get("player_name", ""))
        if n.split():
            fp_alt.setdefault((n.split()[-1], (r.get("player_team_id") or "").upper()), r)

    for row in rows:
        key = normalise(row.name)
        rec = fp.get(key)
        if rec is None and key.split():
            rec = fp_alt.get((key.split()[-1], row.team.upper()))
        if rec is None:
            continue
        row.ecr_rank = _int(rec.get("rank_ecr"))
        row.ecr_tier = _int(rec.get("tier"))
        row.ecr_pos_rank = str(rec.get("pos_rank") or "")
        row.ecr_std = _float(rec.get("rank_std"))
        row.bye_week = _int(rec.get("player_bye_week")) or row.bye_week
        if not row.adp:
            row.adp = _float(rec.get("player_owned_avg"))


def _compute_vbd(rows: list[DraftRow], roster: dict[str, int], teams: int) -> None:
    by_pos: dict[str, list[DraftRow]] = {}
    for r in rows:
        by_pos.setdefault(r.primary_pos or "?", []).append(r)
    for lst in by_pos.values():
        lst.sort(key=lambda r: -(r.proj_points or 0))

    flex_slots = roster.get("FLEX", 0) * teams
    for pos, lst in by_pos.items():
        starters = roster.get(pos, 0) * teams
        demand = starters + flex_slots * _FLEX_SPLIT.get(pos, 0.0)
        idx = max(0, min(len(lst) - 1, round(demand) - 1))
        repl = lst[idx].proj_points if lst else 0.0
        for r in lst:
            r.vbd = round((r.proj_points or 0) - repl, 1)


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
