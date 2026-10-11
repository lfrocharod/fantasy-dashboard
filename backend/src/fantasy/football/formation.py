"""Build a plausible starting XI from a pool plus a "chance of starting" score,
shaped to the team's likely formation.

Every legal outfield shape (3-5 DEF / 2-5 MID / 1-3 FWD, summing to 10) is
tried, and the one whose ten best players add up to the most start-probability
wins, with a small nudge toward a back four (the most common shape). This keeps
a nailed striker in even when a club fields lots of wide midfielders, and drops
to a back four when the fifth defender is a rotation body, not a starter.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(slots=True)
class FormationXI[T]:
    xi: list[T]
    bench: list[T]
    formation: str  # e.g. "4-3-3", or "—" when a line can't be filled


def pick_formation_xi[T](
    pool: Sequence[T],
    *,
    is_gk: Callable[[T], bool],
    is_def: Callable[[T], bool],
    is_mid: Callable[[T], bool],
    is_fwd: Callable[[T], bool],
    score: Callable[[T], float],
    bench_n: int = 6,
) -> FormationXI[T]:
    def by_score(items: Sequence[T]) -> list[T]:
        return sorted(items, key=lambda p: -score(p))  # stable, like Array.sort

    gk = by_score([p for p in pool if is_gk(p)])[:1]
    defs = by_score([p for p in pool if not is_gk(p) and is_def(p)])
    mids = by_score([p for p in pool if not is_gk(p) and is_mid(p)])
    fwds = by_score([p for p in pool if not is_gk(p) and is_fwd(p)])

    def total(items: list[T], n: int) -> float:
        return sum(max(0.0, score(p)) for p in items[:n])

    best: tuple[int, int, int] | None = None
    best_total = float("-inf")
    for d in range(3, 6):
        for f in range(1, 4):
            m = 10 - d - f
            if m < 2 or m > 5:
                continue
            if len(defs) < d or len(mids) < m or len(fwds) < f:
                continue
            # tiny structural prior: 4 at the back, then 3
            prior = 0.03 if d == 4 else 0.01 if d == 3 else 0.0
            t = total(defs, d) + total(mids, m) + total(fwds, f) + prior
            if t > best_total:
                best, best_total = (d, m, f), t

    if best is None:  # data-poor: a line can't be filled — take the top 10 outfield
        xi = [*gk, *by_score([*defs, *mids, *fwds])[:10]]
        in_xi = {id(p) for p in xi}
        bench = [p for p in by_score(list(pool)) if id(p) not in in_xi][:bench_n]
        return FormationXI(xi=xi, bench=bench, formation="—")

    d, m, f = best
    xi = [*gk, *defs[:d], *mids[:m], *fwds[:f]]
    in_xi = {id(p) for p in xi}
    bench = [p for p in by_score(list(pool)) if id(p) not in in_xi][:bench_n]
    return FormationXI(xi=xi, bench=bench, formation=f"{d}-{m}-{f}")
