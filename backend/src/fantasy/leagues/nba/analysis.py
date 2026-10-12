"""NBA head-to-head points decisions: the daily lineup, a matchup's projection
and win probability, streaming adds, rest-of-season value, trades and the
playoff race.

A day's lineup is a maximum-weight assignment of the players who have a game
that day to the starting slots they're eligible for. A player is worth the
same in whichever slot he fills, so the sets of players that can all be seated
form a transversal matroid and the greedy rule is exact: take players best
first and keep each one an augmenting path can still seat.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from fantasy.leagues.nba.players import OUT_STATUS, NbaPlayer

# pro team id → {day: (opponent id, home)}
Games = Mapping[int, Mapping[int, tuple[int, bool]]]

# One game's fantasy points vary a lot: the standard deviation is about this
# share of a player's average (NBA box scores, points scoring).
GAME_CV = 0.38
# Spread a per-game model can't see over a week: minutes swings, a surprise
# rest day, a blowout. Scales the weekly standard deviation.
WEEK_NOISE = 1.15

# Slots in ESPN's order: specific ones first, so a player goes to his own
# position before a flexible slot and the lineup reads naturally.
SLOT_ORDER = ("PG", "SG", "SF", "PF", "C", "G", "F", "SG/SF", "G/F", "PF/C", "F/C", "UT")
# How fast an injury designation fades over the days ahead: the chance a
# player still misses a game k days out is (1 - play_prob) * RECOVERY ** k.
# Day-to-day knocks clear within days; "out" can mean a week or a month.
RECOVERY = {"DAY_TO_DAY": 0.6, "QUESTIONABLE": 0.6, "PROBABLE": 0.5, "DOUBTFUL": 0.75,
            "OUT": 0.88, "SUSPENSION": 0.9, "INJURY_RESERVE": 0.95}


def slot_list(slots: Mapping[str, int]) -> list[str]:
    """{"UT": 3, "PG": 1} → ["PG", "UT", "UT", "UT"]."""
    rank = {s: i for i, s in enumerate(SLOT_ORDER)}
    out: list[str] = []
    for s in sorted(slots, key=lambda s: (rank.get(s, len(rank)), s)):
        out += [s] * int(slots[s])
    return out


def plays(p: NbaPlayer, day: int, games: Games) -> bool:
    return day in games.get(p.pro_team_id, {})


def availability(p: NbaPlayer, ahead: int = 0) -> float:
    """Chance he plays a game `ahead` days from today, given today's tag."""
    miss = 1 - p.play_prob
    if miss <= 0:
        return 1.0
    return 1 - miss * RECOVERY.get(p.injury, 0.8) ** max(0, ahead)


def game_value(p: NbaPlayer, ahead: int = 0) -> float:
    """Expected points from one game `ahead` days from today."""
    return p.fppg * availability(p, ahead)


def keep_value(p: NbaPlayer) -> float:
    """What a player is worth when healthy, per game: how drop candidates
    are picked (an injured star is not the one to cut)."""
    return p.fppg * p.durability


def future_value(p: NbaPlayer) -> float:
    """Expected points from one game weeks out: today's injury fades into the
    usual share of games missed."""
    return p.fppg * p.durability


# ---- one day ------------------------------------------------------------------------------


@dataclass(slots=True)
class Seat:
    slot: str
    player: NbaPlayer | None
    value: float = 0.0


def best_lineup(
    players: Sequence[NbaPlayer], value: Callable[[NbaPlayer], float], slots: Sequence[str],
) -> tuple[list[Seat], list[NbaPlayer]]:
    """The highest-value lineup (seats in `slots` order) and the players with
    value who didn't fit — games lost to the bench."""
    cands = sorted((p for p in players if value(p) > 0), key=lambda p: (-value(p), p.ext_id))
    owner: list[int | None] = [None] * len(slots)
    seated: list[NbaPlayer] = []
    elig: list[list[int]] = []
    benched: list[NbaPlayer] = []

    def place(ci: int, seen: set[int]) -> bool:  # Kuhn's augmenting path
        for si in elig[ci]:  # an open slot first, so nobody is shuffled needlessly
            if owner[si] is None:
                owner[si] = ci
                return True
        for si in elig[ci]:
            if si in seen:
                continue
            seen.add(si)
            prev = owner[si]
            if prev is not None and place(prev, seen):
                owner[si] = ci
                return True
        return False  # nothing was changed on the way down

    for p in cands:
        seated.append(p)
        elig.append([i for i, s in enumerate(slots) if s in p.slots])
        if not place(len(seated) - 1, set()):
            seated.pop()
            elig.pop()
            benched.append(p)
    seats = [
        Seat(slot, seated[o], value(seated[o])) if o is not None else Seat(slot, None)
        for slot, o in zip(slots, owner, strict=True)
    ]
    return seats, benched


# ---- a matchup period ---------------------------------------------------------------------


@dataclass(slots=True)
class DayPlan:
    day: int
    seats: list[Seat]
    benched: list[NbaPlayer]  # had a game but no seat
    idle: list[NbaPlayer]  # no game (or on IR)

    @property
    def points(self) -> float:
        return sum(s.value for s in self.seats)

    @property
    def variance(self) -> float:
        return sum((GAME_CV * s.value) ** 2 for s in self.seats)

    @property
    def started(self) -> int:
        return sum(1 for s in self.seats if s.player is not None)

    @property
    def open_slots(self) -> int:
        return sum(1 for s in self.seats if s.player is None)


@dataclass(slots=True)
class WeekPlan:
    days: list[DayPlan]

    @property
    def total(self) -> float:
        return sum(d.points for d in self.days)

    @property
    def variance(self) -> float:
        return sum(d.variance for d in self.days)

    @property
    def games(self) -> int:
        return sum(d.started for d in self.days)

    @property
    def lost(self) -> int:
        return sum(len(d.benched) for d in self.days)

    @property
    def open_slots(self) -> int:
        return sum(d.open_slots for d in self.days)


def _valuer(ahead: int) -> Callable[[NbaPlayer], float]:
    def value(p: NbaPlayer) -> float:
        return game_value(p, ahead)

    return value


def plan_days(
    roster: Sequence[NbaPlayer], days: Sequence[int], games: Games, slots: Sequence[str],
    today: int | None = None,
) -> WeekPlan:
    """The best lineup for each day. Players on IR can't start; an injury tag
    weighs less the further ahead the day is."""
    start = days[0] if today is None and days else (today or 0)
    out = []
    for d in days:
        active = [p for p in roster if p.slot != "IR" and plays(p, d, games)]
        seats, benched = best_lineup(active, _valuer(d - start), slots)
        playing = {p.ext_id for p in active}
        out.append(DayPlan(d, seats, benched, [p for p in roster if p.ext_id not in playing]))
    return WeekPlan(out)


def win_prob(my_points: float, my_plan: WeekPlan, opp_points: float, opp_plan: WeekPlan) -> int:
    """Chance (0-100) to win the matchup: banked points plus each side's
    projection, with the remaining games' spread on both sides."""
    margin = (my_points + my_plan.total) - (opp_points + opp_plan.total)
    var = (my_plan.variance + opp_plan.variance) * WEEK_NOISE**2
    if var <= 0:
        return 100 if margin > 0 else 0 if margin < 0 else 50
    p = 0.5 * (1 + math.erf(margin / math.sqrt(2 * var)))
    return max(1, min(99, round(100 * p)))


def games_in(p: NbaPlayer, days: Iterable[int], games: Games) -> int:
    team = games.get(p.pro_team_id, {})
    return sum(1 for d in days if d in team)


def ros_value(p: NbaPlayer, days: Sequence[int], games: Games) -> float:
    """Fantasy points still to come over `days` (from today to the end of the
    regular season): per-game rate × each game's chance he plays it — today's
    injury fading, then the usual share of games missed."""
    if not days:
        return 0.0
    team = games.get(p.pro_team_id, {})
    played = sum(availability(p, d - days[0]) for d in days if d in team)
    return p.fppg * p.durability * played


# ---- streaming ----------------------------------------------------------------------------


def pickup_cap(limit: int | None, per_game_day: bool, game_days: int) -> int | None:
    """Pickups allowed in a matchup. ESPN's limit is either per matchup or,
    with its per-scoring-period switch on, per NBA game day in the matchup:
    seven in an ordinary week, more in the long opening one, fewer when the
    schedule thins out (the All-Star break, NBA Cup nights)."""
    if limit is None:
        return None
    return limit * game_days if per_game_day else limit


@dataclass(slots=True)
class Stream:
    add: NbaPlayer
    drop: NbaPlayer
    gain: float  # matchup points gained over the days left
    games: int  # the add's games over those days
    ros_delta: float  # rest-of-season value, add minus drop (negative: a pure stream)


def streams(
    roster: Sequence[NbaPlayer], free_agents: Sequence[NbaPlayer], days: Sequence[int],
    games: Games, slots: Sequence[str], ros: Callable[[NbaPlayer], float],
    limits: Mapping[str, int] | None = None, n_adds: int = 30, n_drops: int = 3,
) -> list[Stream]:
    """Add/drop pairs that raise this matchup's projection: each free agent with
    games left, swapped for whichever of your least valuable players gains the
    most. Waiver-wire players are left out (claims don't clear in time)."""
    if not days:
        return []
    base = plan_days(roster, days, games, slots).total
    droppable = [p for p in roster if p.droppable and p.slot != "IR"]
    drops = sorted(droppable, key=lambda p: (keep_value(p), p.ext_id))[:n_drops]
    adds = sorted(
        (p for p in free_agents
         if p.status != "WAIVERS" and p.play_prob > 0 and games_in(p, days, games) > 0),
        key=lambda p: (-p.fppg * games_in(p, days, games), p.ext_id),
    )[:n_adds]
    out = []
    for a in adds:
        best: Stream | None = None
        for d in drops:
            after = [p for p in roster if p.ext_id != d.ext_id] + [a]
            cap = (limits or {}).get(a.pos)
            if cap is not None and sum(1 for p in after if p.pos == a.pos) > cap:
                continue
            gain = plan_days(after, days, games, slots).total - base
            if best is None or gain > best.gain:
                best = Stream(a, d, gain, games_in(a, days, games), ros(a) - ros(d))
        if best is not None and best.gain >= 1:
            out.append(best)
    out.sort(key=lambda s: (-s.gain, s.add.ext_id))
    return out


# ---- trades -------------------------------------------------------------------------------


@dataclass(slots=True)
class TradeEval:
    my_ros: float  # change in your rest-of-season points, roster moves included
    my_week: float  # change in this matchup's projection
    their_ros: float  # their change, valued on ESPN's projections
    my_playoff_games: int  # change in your players' games in the fantasy playoffs
    roster_moves: list[str]
    warnings: list[str]
    verdict: str


def their_value(p: NbaPlayer, days: Iterable[int], games: Games) -> float:
    """How the league tends to value a player: ESPN's projection, not form."""
    return (p.fppg_proj or p.fppg) * p.durability * games_in(p, days, games)


def evaluate_trade(
    roster: Sequence[NbaPlayer], give: Sequence[NbaPlayer], get: Sequence[NbaPlayer],
    free_agents: Sequence[NbaPlayer], week_days: Sequence[int], ros_days: Sequence[int],
    playoff_days: Sequence[int], games: Games, slots: Sequence[str],
) -> TradeEval:
    def ros(p: NbaPlayer) -> float:
        return ros_value(p, ros_days, games)

    moves: list[str] = []
    gain = sum(ros(p) for p in get) - sum(ros(p) for p in give)
    give_ids = {p.ext_id for p in give}
    after = [p for p in roster if p.ext_id not in give_ids] + list(get)
    extra = len(get) - len(give)
    if extra > 0:  # roster's full: cut the weakest players who aren't in the deal
        get_ids = {p.ext_id for p in get}
        cuts = sorted((p for p in after if p.ext_id not in get_ids and p.droppable),
                      key=lambda p: (keep_value(p), p.ext_id))[:extra]
        gain -= sum(ros(p) for p in cuts)
        cut_ids = {p.ext_id for p in cuts}
        after = [p for p in after if p.ext_id not in cut_ids]
        moves += [f"drop {p.name} to make room" for p in cuts]
    elif extra < 0:  # open spots: fill them from free agency
        fills = sorted((p for p in free_agents if p.play_prob > 0),
                       key=lambda p: (-ros(p), p.ext_id))[:-extra]
        gain += sum(ros(p) for p in fills)
        after += fills
        moves += [f"add {p.name} with the open spot" for p in fills]

    week = (plan_days(after, week_days, games, slots).total
            - plan_days(roster, week_days, games, slots).total) if week_days else 0.0
    theirs = (sum(their_value(p, ros_days, games) for p in give)
              - sum(their_value(p, ros_days, games) for p in get))
    po_games = (sum(games_in(p, playoff_days, games) for p in get)
                - sum(games_in(p, playoff_days, games) for p in give))

    warnings = []
    for p in get:
        if p.injury in OUT_STATUS:
            warnings.append(f"{p.name} is {p.injury.replace('_', ' ').lower()}")
        if p.gp_now >= 8 and p.fppg_proj and p.fppg_now > 1.25 * p.fppg_proj:
            warnings.append(f"{p.name} is running {p.fppg_now:.0f} a game against a "
                            f"{p.fppg_proj:.0f} projection — buying near the peak")
    for p in give:
        if p.gp_now >= 8 and p.fppg_proj and p.fppg_now < 0.8 * p.fppg_proj:
            warnings.append(f"{p.name} is below his {p.fppg_proj:.0f} projection — "
                            "selling low")
    weeks_left = max(1.0, len(ros_days) / 7)
    per_week = gain / weeks_left
    if per_week >= 15 and theirs >= -0.04 * max(1.0, sum(their_value(p, ros_days, games) for p in get)):
        verdict = "Clear win, and it looks fair on paper — propose it."
    elif per_week >= 15:
        verdict = "A win for you, but lopsided on their numbers — expect a counter."
    elif per_week <= -15:
        verdict = "You lose rest-of-season points — pass unless you need this week."
    elif po_games >= 2 and per_week > -5:
        verdict = "About even now, more games when the playoffs come — worth it."
    else:
        verdict = "Roughly even."
    return TradeEval(my_ros=gain, my_week=week, their_ros=theirs, my_playoff_games=po_games,
                     roster_moves=moves, warnings=warnings, verdict=verdict)


@dataclass(slots=True)
class TradeIdea:
    rival_id: int
    give: NbaPlayer
    get: NbaPlayer
    my_gain: float
    their_gain: float


def trade_ideas(
    mine: Sequence[NbaPlayer], rivals: Mapping[int, Sequence[NbaPlayer]], ros_days: Sequence[int],
    games: Games, per_rival: int = 2, limit: int = 8,
) -> list[TradeIdea]:
    """One-for-one swaps that add rest-of-season points for you while looking
    even (or better) for them on ESPN's projections — the gap between this
    season's form plus the schedule, and the preseason numbers most managers
    trade on. Your two best players stay off the table."""
    def ros(p: NbaPlayer) -> float:
        return ros_value(p, ros_days, games)

    core = {p.ext_id for p in sorted(mine, key=lambda p: -ros(p))[:2]}
    offer = [p for p in mine if p.ext_id not in core and p.injury not in OUT_STATUS]
    out = []
    for rid, theirs in rivals.items():
        ideas = []
        for g in offer:
            for t in theirs:
                if t.injury in OUT_STATUS:
                    continue
                mine_gain = ros(t) - ros(g)
                their_gain = their_value(g, ros_days, games) - their_value(t, ros_days, games)
                if mine_gain >= max(40.0, 0.04 * ros(g)) and their_gain >= -0.02 * their_value(t, ros_days, games):
                    ideas.append(TradeIdea(rid, g, t, mine_gain, their_gain))
        ideas.sort(key=lambda i: (-i.my_gain, i.get.ext_id))
        out += ideas[:per_rival]
    out.sort(key=lambda i: (-i.my_gain, i.rival_id, i.get.ext_id))
    return out[:limit]


# ---- the playoff race ---------------------------------------------------------------------


def team_period(roster: Sequence[NbaPlayer], days: Iterable[int], games: Games,
                capacity: int) -> tuple[float, float]:
    """(mean, variance) of a team's points over a future period. Each day takes
    the best `capacity` players with a game — slot eligibility rarely binds
    over a full roster, and this keeps the season simulation fast."""
    mean = var = 0.0
    for d in days:
        vals = sorted((future_value(p) for p in roster if p.slot != "IR" and plays(p, d, games)),
                      reverse=True)[:capacity]
        mean += sum(vals)
        var += sum((GAME_CV * v) ** 2 for v in vals)
    return mean, var * WEEK_NOISE**2


@dataclass(slots=True)
class Standing:
    team_id: int
    wins: int
    losses: int
    ties: int
    points_for: float


@dataclass(slots=True)
class Odds:
    team_id: int
    playoff_pct: float
    top_seed_pct: float
    proj_wins: float
    proj_pf: float


def sim_playoffs(
    standings: Sequence[Standing],
    remaining: Sequence[tuple[int, int, int]],  # (period, home, away)
    period_mean: Mapping[tuple[int, int], tuple[float, float]],  # (team, period) → (mean, var)
    playoff_teams: int, strength_sd: float = 0.0, sims: int = 4000, seed: int = 20261020,
) -> list[Odds]:
    """Monte Carlo over the regular season left: each matchup is two normal
    draws, scaled by a per-season shock to each team's strength (`strength_sd`:
    injuries, trades and projections being wrong — a projection is not a
    certainty); seeding is wins, then points for."""
    ids = [s.team_id for s in standings]
    idx = {t: i for i, t in enumerate(ids)}
    rng = np.random.default_rng(seed)
    shock = (rng.normal(1.0, strength_sd, (sims, len(ids))) if strength_sd > 0
             else np.ones((sims, len(ids))))
    wins = np.tile(np.array([s.wins + 0.5 * s.ties for s in standings], dtype=float), (sims, 1))
    pf = np.tile(np.array([s.points_for for s in standings], dtype=float), (sims, 1))
    for period, h, a in remaining:
        if h not in idx or a not in idx:
            continue
        mh, vh = period_mean.get((h, period), (0.0, 0.0))
        ma, va = period_mean.get((a, period), (0.0, 0.0))
        sh = (rng.normal(mh, math.sqrt(vh), sims) if vh > 0 else np.full(sims, mh)) * shock[:, idx[h]]
        sa = (rng.normal(ma, math.sqrt(va), sims) if va > 0 else np.full(sims, ma)) * shock[:, idx[a]]
        wins[:, idx[h]] += sh > sa
        wins[:, idx[a]] += sa > sh
        pf[:, idx[h]] += sh
        pf[:, idx[a]] += sa
    # rank by wins, then points for (pf is far below 1e6 a season)
    order = np.argsort(-(wins * 1e6 + pf), axis=1)
    rank = np.empty_like(order)
    rows = np.arange(sims)[:, None]
    rank[rows, order] = np.arange(len(ids))[None, :]
    return [
        Odds(team_id=t, playoff_pct=round(100 * float(np.mean(rank[:, i] < playoff_teams)), 1),
             top_seed_pct=round(100 * float(np.mean(rank[:, i] == 0)), 1),
             proj_wins=round(float(np.mean(wins[:, i])), 1),
             proj_pf=round(float(np.mean(pf[:, i])), 0))
        for t, i in idx.items()
    ]
