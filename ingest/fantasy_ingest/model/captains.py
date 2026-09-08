"""Captaincy analysis for the current squad on a given matchday.

Captain doubles a player's score, so the decision is almost always the biggest
single swing of the week. We surface EV, ceiling, floor and a differential
option (low-owned, high-ceiling) so a mini-league player can pick safe when
ahead and aggressive when behind.
"""

from __future__ import annotations


def analyse_captains(rows: list[dict], *, top_n: int = 6) -> dict:
    """`rows`: current-squad players with keys playerId, name, team, position,
    xpts, xptsHigh, xptsLow, selectedPct (0-100)."""
    cands = []
    for r in rows:
        xp = r.get("xpts") or 0.0
        if xp <= 0:
            continue
        # you effectively never captain a goalkeeper — their ceiling is a save
        # count, not a haul. Keep them out of every captain suggestion.
        if r.get("position") == "GK":
            continue
        hi = r.get("xptsHigh") or xp
        lo = r.get("xptsLow") or xp
        cands.append(
            {
                "playerId": r["playerId"],
                "name": r["name"],
                "team": r.get("team", ""),
                "position": r.get("position", ""),
                "ev": round(2 * xp, 2),
                "ceiling": round(2 * hi, 2),
                "floor": round(2 * lo, 2),
                "owned": round(r.get("selectedPct") or 0.0, 1),
                # blended score: mostly EV, some upside
                "score": round(0.72 * (2 * xp) + 0.28 * (2 * hi), 2),
            }
        )
    cands.sort(key=lambda c: -c["score"])
    shortlist = cands[:top_n]
    safe = max(shortlist, key=lambda c: (0.6 * c["ev"] + 0.4 * c["floor"]), default=None)
    # a differential captain still has to be a *plausible* captain — within ~65%
    # of the best pick's EV — not a low-owned lottery ticket.
    top_ev = shortlist[0]["ev"] if shortlist else 0.0
    diff_pool = [c for c in cands if c["owned"] < 15 and c["ev"] >= 0.65 * top_ev] or [
        c for c in cands if c["owned"] < 15
    ] or cands
    differential = max(diff_pool, key=lambda c: c["ceiling"], default=None)
    return {
        "candidates": shortlist,
        "safePick": safe,
        "differentialPick": differential if differential and (not safe or differential["playerId"] != safe["playerId"]) else None,
    }
