"""Match UEFA players to recent-form rows (Sofascore / Understat) and derive:
  * team_ok    — still at the club UEFA lists them under?
  * role       — the position they've actually been playing
  * role_note  — human note when role != UEFA position
  * start_prob — data-driven chance of starting the next match
  * hot_score  — recent goal involvement per 90, nudged by rating
"""

from __future__ import annotations

from rapidfuzz import fuzz

from ..sources.recent_form import FormRow, normalise
from ..types import Player, PlayerForm

_NAME_FLOOR = 80


def _name_score(uefa_name: str, fr: FormRow) -> float:
    n = normalise(uefa_name)
    s = fuzz.token_set_ratio(n, fr.norm_name) / 100.0
    if n.split() and fr.norm_name.split():
        s = max(s, 0.5 * s + 0.5 * fuzz.ratio(n.split()[-1], fr.norm_name.split()[-1]) / 100.0)
    return s


def _team_match(uefa_team: str, fr: FormRow) -> float:
    a, b = normalise(uefa_team), fr.norm_team
    sc = fuzz.token_set_ratio(a, b) / 100.0
    if a.split() and b.split():
        sc = max(sc, fuzz.ratio(a.split()[-1], b.split()[-1]) / 100.0)
    return sc


def _infer_role(nominal: str, sofa_role: str, fr: FormRow) -> str:
    """Sofascore's per-match position isn't always in the aggregate feed, so
    when it says nothing, infer 'playing forward' from output: a listed MID/DEF
    with a striker's underlying rate over a real sample is a leverage pick."""
    if sofa_role and sofa_role != nominal:
        return sofa_role
    if nominal in ("MID", "DEF") and fr.recent_minutes >= 200:
        npxg90 = fr.recent_npxg / (fr.recent_minutes / 90.0)
        sh90 = fr.recent_shots / (fr.recent_minutes / 90.0)
        if npxg90 >= 0.45 and sh90 >= 2.2:
            return "FWD"
    return nominal


def build_player_form(
    players: list[Player],
    team_names: dict[int, str],
    form_rows: list[FormRow],
    role_overrides: dict | None = None,
) -> tuple[list[PlayerForm], list[tuple[int, str]]]:
    role_overrides = role_overrides or {}
    out: list[PlayerForm] = []
    unmatched: list[tuple[int, str]] = []
    by_surname: dict[str, list[FormRow]] = {}
    for fr in form_rows:
        if fr.norm_name.split():
            by_surname.setdefault(fr.norm_name.split()[-1], []).append(fr)

    for p in players:
        uefa_team = team_names.get(p.team_id, "")
        surname = normalise(p.name).split()[-1] if normalise(p.name).split() else ""
        cands = by_surname.get(surname, []) or form_rows
        p_tokens = len(normalise(p.name).split())
        best, best_s = None, 0.0
        for fr in cands:
            ns = _name_score(p.name, fr)
            if ns * 100 < _NAME_FLOOR:
                continue
            ts = _team_match(uefa_team, fr)
            # token_set_ratio treats "Gabriel" as a perfect match for "Gabriel
            # Teixeira"; require the token counts to be close unless the teams
            # actually agree.
            fr_tokens = len(fr.norm_name.split())
            if ts < 0.6 and (ns < 0.94 or abs(fr_tokens - p_tokens) >= 1):
                continue
            score = 0.7 * ns + 0.3 * ts
            if score > best_s:
                best, best_s = fr, score
        if not best or best_s < 0.66:
            unmatched.append((p.uefa_player_id, p.name))
            continue

        # Only call a player "transferred out" when the club really doesn't
        # match — a soft mismatch (0.4–0.55) is usually a naming quirk or
        # national-team contamination, not a move, and blanking a premium pick
        # over it is worse than trusting the roster.
        tscore = _team_match(uefa_team, best)
        team_ok = tscore >= 0.45 or best.recent_minutes == 0
        ovr = role_overrides.get(str(p.uefa_player_id)) or role_overrides.get(p.name)
        role = (str(ovr).upper() if ovr else None) or _infer_role(p.position, best.role, best)
        note = ""
        if role != p.position:
            note = f"listed {p.position}, playing {role}"
        if not team_ok:
            note = f"now at {best.team}?" + (f" — {note}" if note else "")
        elif 0.45 <= tscore < 0.62 and best.recent_minutes > 0:
            note = (note + " · " if note else "") + f"club check: UEFA {uefa_team} / form {best.team}"

        out.append(
            PlayerForm(
                player_id=p.uefa_player_id,
                source_team=best.team,
                team_ok=team_ok,
                role=role,
                role_note=note,
                recent_matches=best.recent_matches,
                recent_starts=best.recent_starts,
                recent_minutes=round(best.recent_minutes, 1),
                recent_goals=best.recent_goals,
                recent_assists=best.recent_assists,
                recent_npxg=round(best.recent_npxg, 2),
                recent_xa=round(best.recent_xa, 2),
                recent_shots=best.recent_shots,
                season_minutes=round(best.season_minutes, 1),
                season_npxg90=round(best.season_npxg90, 3),
                season_xa90=round(best.season_xa90, 3),
                avg_rating=round(getattr(best, "avg_rating", 0.0), 2),
                matches_14d=int(getattr(best, "matches_14d", 0)),
                comps=", ".join(getattr(best, "comps", []) or []),
                start_prob=_start_prob(p, best),
                hot_score=_hot(best),
            )
        )
    return out, unmatched


def _start_prob(p: Player, fr: FormRow) -> float:
    if p.status_code >= 2:
        return 0.0
    if fr.recent_matches == 0:
        base = 0.4
    else:
        start_rate = fr.recent_starts / fr.recent_matches
        mins_rate = min(1.0, fr.recent_minutes / (fr.recent_matches * 90.0))
        base = 0.65 * start_rate + 0.35 * mins_rate
    if p.status_code == 1:
        base *= 0.6
    return round(max(0.0, min(0.99, base)), 3)


def _hot(fr: FormRow) -> float:
    if fr.recent_minutes < 30:
        return 0.0
    per90 = (fr.recent_goals + fr.recent_assists) / (fr.recent_minutes / 90.0)
    x_per90 = (fr.recent_npxg + fr.recent_xa) / (fr.recent_minutes / 90.0)
    score = 0.6 * per90 + 0.4 * x_per90
    r = getattr(fr, "avg_rating", 0.0)
    if r:  # a 7.5 avg lifts it ~20%, a 6.0 avg cuts it ~15%
        score *= max(0.7, min(1.35, 1.0 + (r - 6.8) * 0.18))
    return round(score, 2)
