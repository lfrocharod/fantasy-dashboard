"""Chip strategy — for every remaining matchday, how much each chip is worth if
played then, plus the single best matchday to use each one.

UCL Fantasy chips (names as UEFA labels them):
  * Wildcard      — unlimited transfers for one MD, squad kept afterwards.
  * Limitless     — unlimited transfers AND unlimited budget for one MD only,
                    squad reverts next MD.
  * Bench Boost   — all 15 score for one MD (bench points count).
  * Triple Captain— captain scores 3x instead of 2x for one MD.

We can only *estimate* value from projections, and we can't read which chips you
still hold (no reliable feed), so the output is advisory: it flags the archetype
and the matchday, and the UI reminds you to confirm the chip is still available.
"""

from __future__ import annotations

from .optimizer import best_xi, build_squad


def _score(squad) -> tuple[list, list, float, float]:
    """(starters, bench, xi_xpts, captain_bonus) for a squad — captain bonus is
    one extra multiple of the best starter (the 2x captain)."""
    starters, bench, _formation, xi = best_xi(squad)
    cap_bonus = max((p.xpts for p in starters), default=0.0)
    return starters, bench, xi, cap_bonus


def _md_row(md: int, squad, pool) -> dict:
    _st, bench, xi, cap_bonus = _score(squad)
    base = xi + cap_bonus

    # Bench Boost: the 4 non-starters all score.
    bench_pts = round(sum(p.xpts for p in bench), 2)

    # Triple Captain: one extra multiple of the best starter.
    tc_gain = round(cap_bonus, 2)

    # Limitless: best legal XI from the whole player pool, price ignored.
    _lst, _lb, ll_xi, ll_cap = _score(pool)
    ll_gain = round(max(0.0, (ll_xi + ll_cap) - base), 2)

    # Wildcard: best legal 15 under the €100m / 2-5-5-3 / max-3 rules for this MD.
    wc = build_squad(pool)
    wc_gain = 0.0
    if len(wc) >= 15:
        _wst, _wb, wc_xi, wc_cap = _score(wc)
        wc_gain = round(max(0.0, (wc_xi + wc_cap) - base), 2)

    return {
        "matchday": md,
        "currentXiXpts": round(base, 2),
        "benchBoost": bench_pts,
        "tripleCaptain": tc_gain,
        "limitless": ll_gain,
        "wildcard": wc_gain,
    }


def evaluate_chips(
    squad_by_md: dict[int, list],
    pool_by_md: dict[int, list],
    *,
    start_md: int,
    used: dict[str, object] | None = None,
) -> dict:
    used = used or {}
    mds = sorted(md for md in squad_by_md if md >= start_md and len(squad_by_md[md]) >= 15)
    rows = [_md_row(md, squad_by_md[md], pool_by_md.get(md, [])) for md in mds]

    def _best(key: str) -> dict | None:
        if not rows or _is_used(used, key):
            return None
        top = max(rows, key=lambda r: r[key])
        return {"matchday": top["matchday"], "gain": top[key]} if top[key] > 0 else None

    return {
        "perMatchday": rows,
        "recommend": {
            "wildcard": _best("wildcard"),
            "limitless": _best("limitless"),
            "benchBoost": _best("benchBoost"),
            "tripleCaptain": _best("tripleCaptain"),
        },
        "used": used,
        "note": "Estimated from projections. Confirm which chips you still hold in the UEFA app.",
    }


def _is_used(used: dict, key: str) -> bool:
    v = used.get(key)
    return v is True or (isinstance(v, (int, float)) and v > 0)
