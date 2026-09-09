"""Chip strategy for UEFA Champions League Fantasy.

The CL game has exactly two chips (no Bench Boost / Triple Captain):

  * Limitless — for ONE matchday: unlimited transfers AND no budget cap; the
    squad reverts the next matchday. Worth playing when the best legal XI you
    could pick from the *entire* player pool (price ignored) beats the best XI
    you can already field from your current 15 by a wide margin — i.e. when your
    squad is genuinely holding you back for a specific matchday.

  * Wildcard — unlimited transfers for one matchday, and you KEEP the squad.
    Best used on the **last league-phase matchday**: all eight games kick off at
    the same time, so confirmed lineups are out before you have to lock, which
    removes the rotation guesswork that makes an earlier wildcard a gamble. Its
    value is over the remaining horizon (you keep the team), not one matchday.

We can't read which chips you still hold, so the output is advisory — the UI
reminds you to confirm.
"""

from __future__ import annotations

from .optimizer import best_xi, build_squad

# Only recommend Limitless when the unconstrained XI is this much better than
# what your own squad can field — otherwise a couple of free transfers do it.
LIMITLESS_MIN_GAIN = 6.0


def _xi_plus_cap(squad, score=lambda p: p.xpts) -> float:
    """Best XI + captain (one extra multiple of the best starter) on `score`."""
    starters, _b, _f, xi = best_xi(squad, score)
    return xi + max((score(p) for p in starters), default=0.0)


def _xi_after_free_transfers(squad, pool, ft: int, score=lambda p: p.xpts) -> float:
    """Best XI + captain you could field after up to `ft` FREE transfers — the
    yardstick Limitless is actually measured against (you'd make those moves
    anyway). Greedy upper bound: each step signs the pool player who most lifts
    the best XI at their position and retires the weakest starter there."""
    working = list(squad)
    owned = {p.player_id for p in working}
    for _ in range(max(0, ft)):
        starters, _b, _f, _xi = best_xi(working, score)
        best_delta, best_pair = 0.0, None
        for pos in {s.position for s in starters}:
            top = max((c for c in pool if c.position == pos and c.player_id not in owned),
                      key=score, default=None)
            weak = min((s for s in starters if s.position == pos), key=score, default=None)
            if top and weak and score(top) - score(weak) > best_delta:
                best_delta, best_pair = score(top) - score(weak), (weak, top)
        if not best_pair:
            break
        weak, top = best_pair
        working = [p for p in working if p.player_id != weak.player_id] + [top]
        owned.discard(weak.player_id)
        owned.add(top.player_id)
    return _xi_plus_cap(working, score)


def _md_row(md: int, squad, pool, ft: int = 2) -> dict:
    """`pool` here already includes your owned players (neither chip drops them)."""
    base = _xi_plus_cap(squad)
    # what you could field for THIS matchday just by spending your free transfers
    base_ft = _xi_after_free_transfers(squad, pool, ft)

    # Limitless: best legal XI from the whole pool, price ignored — for one MD,
    # measured against the team your free transfers already get you to.
    ll_gain = round(max(0.0, _xi_plus_cap(pool) - base_ft), 2)

    # Wildcard: best legal 15 under €100m / 2-5-5-3 / max-3 — you keep it, so
    # score the gain over the planning horizon.
    wc_gain = 0.0
    wc = build_squad(pool)
    if len(wc) >= 15:
        wc_gain = round(max(0.0, _xi_plus_cap(wc, lambda p: p.hx) - _xi_plus_cap(squad, lambda p: p.hx)), 2)

    return {"matchday": md, "currentXiXpts": round(base, 2),
            "freeTransferXiXpts": round(base_ft, 2),
            "limitless": ll_gain, "wildcard": wc_gain}


def evaluate_chips(
    squad_by_md: dict[int, list],
    pool_by_md: dict[int, list],
    *,
    start_md: int,
    last_league_md: int = 8,
    free_transfers: int = 2,
    used: dict[str, object] | None = None,
) -> dict:
    used = used or {}
    mds = sorted(md for md in squad_by_md if md >= start_md and len(squad_by_md[md]) >= 15)
    # Limitless / Wildcard both keep your owned players available in the pool.
    rows = [
        _md_row(md, squad_by_md[md], pool_by_md.get(md, []) + squad_by_md[md], free_transfers)
        for md in mds
    ]
    by_md = {r["matchday"]: r for r in rows}

    limitless = None
    if rows and not _is_used(used, "limitless"):
        top = max(rows, key=lambda r: r["limitless"])
        if top["limitless"] >= LIMITLESS_MIN_GAIN:
            limitless = {"matchday": top["matchday"], "gain": top["limitless"],
                         "why": f"the best price-free XI for MD{top['matchday']} projects "
                                f"+{top['limitless']} over the team your free transfers "
                                "already get you to — a one-week swing worth the chip"}

    wildcard = None
    if rows and not _is_used(used, "wildcard"):
        # the rule of thumb: play it on the last league-phase MD (simultaneous
        # kickoffs, lineups known) unless it's genuinely worthless there.
        wc_md = last_league_md if last_league_md in by_md else mds[-1]
        g = by_md[wc_md]["wildcard"]
        wildcard = {
            "matchday": wc_md, "gain": g,
            "why": "all games kick off together on the last league-phase MD, so "
                   "you lock in with confirmed lineups — no rotation guesswork"
                   if wc_md == last_league_md
                   else "last matchday we have projections for",
        }

    return {
        "perMatchday": rows,
        "recommend": {"limitless": limitless, "wildcard": wildcard},
        "used": used,
        "note": "CL Fantasy has only Limitless and Wildcard. Estimated from "
                "projections — confirm which chips you still hold in the UEFA app.",
    }


def _is_used(used: dict, key: str) -> bool:
    v = used.get(key)
    return v is not None and v is not False
