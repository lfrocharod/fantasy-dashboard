"""Match UEFA players to external stat rows by fuzzy name + team.

Returns per-player `PlayerStat` plus a list of unmatched players so the run can
print a report you resolve with the `player_id_overrides` table.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from fantasy.leagues.ucl.sources.domestic_xg import SourceRow, normalise
from fantasy.leagues.ucl.types import Player, PlayerStat

NAME_FLOOR = 78  # token_set_ratio below this is never a match
ACCEPT = 0.82  # combined (name, team) score to accept


@dataclass(slots=True)
class MatchReport:
    matched: dict[int, PlayerStat]
    unmatched: list[tuple[int, str, str]]  # (player_id, name, team)
    low_confidence: list[tuple[int, str, str, float]]


def _team_score(uefa_team_name: str, uefa_team_code: str, src: SourceRow) -> float:
    a = normalise(uefa_team_name)
    best = fuzz.token_set_ratio(a, src.norm_team) / 100.0
    if uefa_team_code:
        best = max(best, fuzz.partial_ratio(normalise(uefa_team_code), src.norm_team) / 100.0)
    # last word of each (e.g. "internazionale" vs "inter") helps
    if a.split() and src.norm_team.split():
        best = max(best, fuzz.ratio(a.split()[-1], src.norm_team.split()[-1]) / 100.0)
    return best


def _name_score(uefa_name: str, src: SourceRow) -> float:
    n = normalise(uefa_name)
    s1 = fuzz.token_set_ratio(n, src.norm_name) / 100.0
    # surname-only comparison catches "Vini Jr" vs "Vinicius Junior" etc.
    if n.split() and src.norm_name.split():
        s2 = fuzz.ratio(n.split()[-1], src.norm_name.split()[-1]) / 100.0
    else:
        s2 = 0.0
    return max(s1, 0.6 * s1 + 0.4 * s2)


def build_stats(
    players: list[Player],
    team_names: dict[int, str],
    fbref_rows: list[SourceRow],
    understat_rows: list[SourceRow],
    overrides: dict[int, tuple[str, str]] | None = None,
) -> MatchReport:
    overrides = overrides or {}
    by_source = {"fbref": fbref_rows, "understat": understat_rows}
    matched: dict[int, PlayerStat] = {}
    unmatched: list[tuple[int, str, str]] = []
    low: list[tuple[int, str, str, float]] = []

    for p in players:
        team_name = team_names.get(p.team_id, "")
        picks: dict[str, SourceRow] = {}
        for source, rows in by_source.items():
            best_row, best_score = None, 0.0
            ov = overrides.get(p.uefa_player_id)
            for row in rows:
                if ov and (normalise(ov[0]) != row.norm_name or (ov[1] and normalise(ov[1]) != row.norm_team)):
                    continue
                ns = _name_score(p.name, row)
                if ns * 100 < NAME_FLOOR and not ov:
                    continue
                ts = _team_score(team_name, "", row)
                combined = 1.0 if ov else 0.68 * ns + 0.32 * ts
                if combined > best_score:
                    best_row, best_score = row, combined
            if best_row and best_score >= (0.0 if overrides.get(p.uefa_player_id) else ACCEPT):
                picks[source] = best_row
                if best_score < ACCEPT + 0.06:
                    low.append((p.uefa_player_id, p.name, team_name, round(best_score, 3)))

        if not picks:
            unmatched.append((p.uefa_player_id, p.name, team_name))
            continue

        fb = picks.get("fbref")
        us = picks.get("understat")
        base = fb or us
        assert base is not None
        matched[p.uefa_player_id] = PlayerStat(
            player_id=p.uefa_player_id,
            scope="combined",
            minutes=base.minutes,
            matches=base.matches,
            npxg90=_blend(fb.npxg90 if fb else None, us.npxg90 if us else None),
            xag90=_blend(fb.xag90 if fb else None, us.xag90 if us else None),
            shots90=(fb.shots90 if fb else 0.0) or (us.shots90 if us else 0.0),
            sca90=fb.sca90 if fb else 0.0,
            save_pct=fb.save_pct if fb else 0.0,
            source="+".join(picks.keys()),
        )
    return MatchReport(matched=matched, unmatched=unmatched, low_confidence=low)


def _blend(a: float | None, b: float | None) -> float:
    vals = [x for x in (a, b) if x is not None]
    if not vals:
        return 0.0
    if len(vals) == 2:
        return round(0.6 * vals[0] + 0.4 * vals[1], 4)
    return round(vals[0], 4)
