"""Formation-constrained best XI + a greedy transfer planner.

Inputs are plain dicts/dataclasses of already-projected players, so this is
unit-testable without a DB. See tests/test_optimizer.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pulp

from ..types import Position

# Score a player for XI selection. Defaults to this-matchday xPts; the transfer
# planner passes `.hx` (the horizon-decayed sum) so a swap is judged over the
# whole planning window, not one matchday multiplied by a constant.
_Score = Callable[["OptPlayer"], float]
_XPTS: _Score = lambda p: p.xpts

XI_MIN: dict[Position, int] = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX: dict[Position, int] = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
XI_SIZE = 11
MAX_PER_CLUB = 3

SQUAD_QUOTA: dict[Position, int] = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
SQUAD_SIZE = 15
BUDGET = 100.0


@dataclass(slots=True)
class OptPlayer:
    player_id: int
    name: str
    team: str
    club_id: int
    position: Position
    price: float
    xpts: float
    owned: bool = False
    # sum of xpts across the planning horizon (for from-scratch squad building);
    # falls back to xpts when not set.
    horizon_xpts: float | None = None

    @property
    def hx(self) -> float:
        return self.horizon_xpts if self.horizon_xpts is not None else self.xpts


def _as_row(p: OptPlayer, **extra) -> dict:
    row = {
        "playerId": p.player_id,
        "name": p.name,
        "team": p.team,
        "position": p.position,
        "xpts": round(p.xpts, 2),
    }
    row.update(extra)
    return row


def best_xi(
    squad: list[OptPlayer], score: _Score = _XPTS
) -> tuple[list[OptPlayer], list[OptPlayer], str, float]:
    """Pick the 11 starters maximising summed `score` within UEFA formation
    limits. Returns (starters, bench, formation, xi_score)."""
    prob = pulp.LpProblem("best_xi", pulp.LpMaximize)
    x = {p.player_id: pulp.LpVariable(f"s_{p.player_id}", cat="Binary") for p in squad}

    prob += pulp.lpSum(score(p) * x[p.player_id] for p in squad)
    prob += pulp.lpSum(x.values()) == XI_SIZE
    for pos in ("GK", "DEF", "MID", "FWD"):
        in_pos = [x[p.player_id] for p in squad if p.position == pos]
        prob += pulp.lpSum(in_pos) >= XI_MIN[pos]
        prob += pulp.lpSum(in_pos) <= XI_MAX[pos]

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    starters = [p for p in squad if x[p.player_id].value() and x[p.player_id].value() > 0.5]
    bench = [p for p in squad if p not in starters]
    counts = {pos: sum(1 for p in starters if p.position == pos) for pos in ("DEF", "MID", "FWD")}
    formation = f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}"
    xi_score = sum(score(p) for p in starters)
    return starters, bench, formation, xi_score


def _bench_sorted(bench: list[OptPlayer]) -> list[OptPlayer]:
    gk = [p for p in bench if p.position == "GK"]
    outfield = sorted((p for p in bench if p.position != "GK"), key=lambda p: -p.xpts)
    return outfield + gk  # outfield subs first, keeper last


def captain_pick(starters: list[OptPlayer]) -> tuple[int | None, int | None]:
    ranked = sorted(starters, key=lambda p: -p.xpts)
    cap = ranked[0].player_id if ranked else None
    vice = ranked[1].player_id if len(ranked) > 1 else None
    return cap, vice


def _club_counts(squad: list[OptPlayer]) -> dict[int, int]:
    c: dict[int, int] = {}
    for p in squad:
        c[p.club_id] = c.get(p.club_id, 0) + 1
    return c


def _score_squad(squad: list[OptPlayer], score: _Score = _XPTS) -> float:
    starters, _, _, xi = best_xi(squad, score)
    cap = max(starters, key=score, default=None)
    return xi + (score(cap) if cap else 0.0)


def plan_transfers(
    squad: list[OptPlayer],
    pool: list[OptPlayer],
    bank: float,
    free_transfers: int = 1,
    horizon: int = 2,
    max_moves: int = 2,
    hit_cost: int = 4,
) -> list[dict]:
    """Greedy: repeatedly apply the single transfer with the best net gain over
    the planning horizon, stopping when nothing beats its hit.

    Value is the change in the best-XI-plus-captain total scored on `.hx` — the
    horizon-decayed sum of each player's per-matchday xPts. So a transfer that
    only helps the next fixture (and has a rough run after) is judged on its real
    multi-matchday worth, not `single_md_gain * horizon`.
    """
    hx: _Score = lambda p: p.hx
    owned_ids = {p.player_id for p in squad}
    by_pos: dict[Position, list[OptPlayer]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in pool:
        if p.player_id not in owned_ids:
            by_pos[p.position].append(p)
    for lst in by_pos.values():
        lst.sort(key=lambda p: -p.hx)

    current = list(squad)
    current_bank = bank
    moves: list[dict] = []
    base_score = _score_squad(current, hx)

    for move_idx in range(max_moves):
        clubs = _club_counts(current)
        best = None  # (net, out, cand, new_bank, horizon_gain, hit)
        for out in current:
            budget = current_bank + out.price
            for cand in by_pos[out.position][:40]:
                if cand.player_id in {p.player_id for p in current}:
                    continue
                if cand.price > budget + 1e-9:
                    continue
                # club limit after swap
                if cand.club_id != out.club_id and clubs.get(cand.club_id, 0) >= MAX_PER_CLUB:
                    continue
                trial = [cand if p.player_id == out.player_id else p for p in current]
                # already a horizon sum — no `* horizon`
                horizon_gain = _score_squad(trial, hx) - base_score
                hit = 0 if move_idx < free_transfers else hit_cost
                net = horizon_gain - hit
                if best is None or net > best[0]:
                    best = (net, out, cand, budget - cand.price, horizon_gain, hit)

        # require a clear win — a hit's worth of margin even for a free move, so
        # we don't burn a transfer chasing a rounding-error upgrade
        if best is None or best[0] <= 0.6:
            break
        net, out, cand, new_bank, horizon_gain, hit = best
        current = [cand if p.player_id == out.player_id else p for p in current]
        current_bank = new_bank
        base_score = _score_squad(current, hx)
        moves.append(
            {
                "out": _as_row(out),
                "in": _as_row(cand),
                "horizonGain": round(horizon_gain, 2),
                "hitCost": hit,
                "netGain": round(net, 2),
            }
        )
    return moves


def optimise(
    squad: list[OptPlayer],
    pool: list[OptPlayer],
    *,
    matchday: int,
    bank: float = 0.0,
    free_transfers: int = 1,
    horizon: int = 2,
    current_starter_ids: set[int] | None = None,
    current_captain_id: int | None = None,
) -> dict:
    starters, bench, formation, xi_xpts = best_xi(squad)
    cap, vice = captain_pick(starters)
    cap_bonus = next((p.xpts for p in starters if p.player_id == cap), 0.0)
    optimised = xi_xpts + cap_bonus

    # Baseline = the XI the manager currently has picked, if we know it.
    if current_starter_ids:
        cur = [p for p in squad if p.player_id in current_starter_ids]
        cur_cap = next((p.xpts for p in cur if p.player_id == current_captain_id), 0.0)
        if not cur_cap and cur:
            cur_cap = max(p.xpts for p in cur)
        baseline = sum(p.xpts for p in cur) + cur_cap
    else:
        baseline = optimised

    xi_rows = [
        _as_row(p, isCaptain=(p.player_id == cap), isVice=(p.player_id == vice))
        for p in sorted(starters, key=lambda p: ("GK", "DEF", "MID", "FWD").index(p.position))
    ]
    bench_rows = [
        _as_row(p, order=i + 1) for i, p in enumerate(_bench_sorted(bench))
    ]

    transfers = plan_transfers(
        squad, pool, bank=bank, free_transfers=free_transfers, horizon=horizon
    )

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "matchday": matchday,
        "horizon": horizon,
        "formation": formation,
        "baselineXpts": round(baseline, 2),
        "optimisedXpts": round(optimised, 2),
        "bestXI": xi_rows,
        "bench": bench_rows,
        "transfers": transfers,
    }


def build_squad(
    pool: list[OptPlayer],
    *,
    budget: float = BUDGET,
    max_per_club: int = MAX_PER_CLUB,
    max_per_club_pos: int = 2,
    quota: dict[Position, int] | None = None,
    lock_ids: set[int] | None = None,
) -> list[OptPlayer]:
    """Pick the best legal 15 from scratch, maximising summed horizon xPts under
    the €budget, 2/5/5/3 and max-per-club rules. `max_per_club_pos` caps how many
    players you can take from one club in the *same position* (3 Barça mids all
    blank on the same bad night — diversify). `lock_ids` forces players in."""
    quota = quota or SQUAD_QUOTA
    lock_ids = lock_ids or set()
    prob = pulp.LpProblem("build_squad", pulp.LpMaximize)
    x = {p.player_id: pulp.LpVariable(f"p_{p.player_id}", cat="Binary") for p in pool}

    prob += pulp.lpSum(p.hx * x[p.player_id] for p in pool)
    prob += pulp.lpSum(x.values()) == sum(quota.values())
    prob += pulp.lpSum(p.price * x[p.player_id] for p in pool) <= budget
    for pos, n in quota.items():
        prob += pulp.lpSum(x[p.player_id] for p in pool if p.position == pos) == n
    clubs = {p.club_id for p in pool}
    for cid in clubs:
        prob += pulp.lpSum(x[p.player_id] for p in pool if p.club_id == cid) <= max_per_club
        for pos in ("GK", "DEF", "MID", "FWD"):
            same = [x[p.player_id] for p in pool if p.club_id == cid and p.position == pos]
            if len(same) > max_per_club_pos:
                prob += pulp.lpSum(same) <= max_per_club_pos
    for pid in lock_ids:
        if pid in x:
            prob += x[pid] == 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        return []
    return [p for p in pool if x[p.player_id].value() and x[p.player_id].value() > 0.5]


def suggest_initial_squad(pool: list[OptPlayer], *, matchday: int, horizon: int, budget: float = BUDGET) -> dict:
    """From-scratch recommendation for building your team before the season /
    on a wildcard. XI + captain are picked for the given matchday."""
    squad = build_squad(pool, budget=budget)
    if len(squad) < SQUAD_SIZE:
        return {}
    starters, _bench, formation, xi_xpts = best_xi(squad)
    cap, vice = captain_pick(starters)
    cap_bonus = next((p.xpts for p in starters if p.player_id == cap), 0.0)
    order = ("GK", "DEF", "MID", "FWD")
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "matchday": matchday,
        "horizon": horizon,
        "formation": formation,
        "totalCost": round(sum(p.price for p in squad), 1),
        "budget": budget,
        "xiXpts": round(xi_xpts + cap_bonus, 2),
        "horizonXpts": round(sum(p.hx for p in squad), 1),
        "squad": [
            _as_row(p, price=round(p.price, 1), horizonXpts=round(p.hx, 1),
                    isStarter=(p in starters), isCaptain=(p.player_id == cap),
                    isVice=(p.player_id == vice))
            for p in sorted(squad, key=lambda p: (order.index(p.position), -p.hx))
        ],
    }


__all__ = [
    "OptPlayer", "best_xi", "build_squad", "captain_pick",
    "optimise", "plan_transfers", "suggest_initial_squad",
]
