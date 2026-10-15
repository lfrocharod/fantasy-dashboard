"""ESPN NFL in-season decision logic: weekly projections and ranges, lineup
optimisation, trade finding, club dossiers and the playoff Monte Carlo.

Ported from the old web app's `app/nfl/lib.ts` (it used to run in the
browser); `tests/test_parity_nfl.py` checks the port against that code.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from fantasy.football.jsmath import js_round
from fantasy.leagues.fpl.analysis import team_sort_key
from fantasy.leagues.nfl.players import FLEX_POS, OUT_STATUS, NflPlayer, WeekOpp

LineupMode = Literal["floor", "mean", "ceiling"]
START_ORDER = ("QB", "RB", "WR", "TE", "FLEX", "DST", "K")
DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1}


def usage_tag(p: NflPlayer) -> str:
    """"workhorse" / "rotational" / "" for skill players."""
    if p.usage_games < 1 or p.pos in ("K", "DST", "QB"):
        return ""
    heavy = p.snap_pct >= 0.75 or p.wopr >= 0.55 or p.touches >= 16
    light = 0 < p.snap_pct < 0.45 and p.wopr < 0.35 and p.touches < 9
    return "workhorse" if heavy else "rotational" if light else ""


def opp_factor(p: NflPlayer) -> float:
    """Opportunity adjustment (±13%): scoring above what the touches/targets
    expect (fpOE +) is finishing/TD luck that tends to regress; below is a
    buy-low. 1.0 with no expected-points data."""
    if not p.exp_games or p.pos in ("K", "DST"):
        return 1.0
    return 1 + max(-0.13, min(0.13, -p.fp_oe / 26))


def adj_ros(p: NflPlayer) -> float:
    """ROS projection nudged toward the opportunity signal — what the trade
    finder and waiver ranker compare."""
    return p.ros_proj * opp_factor(p)


def opp_tag(p: NflPlayer) -> str:
    """"buy-low" | "sell-high" | "" from the opportunity gap (needs ≥2 games)."""
    if p.exp_games < 2 or p.pos in ("K", "DST"):
        return ""
    if p.fp_oe <= -3.5:
        return "buy-low"
    if p.fp_oe >= 4:
        return "sell-high"
    return ""


def _matchup(p: NflPlayer, week_idx: int) -> WeekOpp | None:
    return p.matchups[week_idx] if 0 <= week_idx < len(p.matchups) else None


def week_points(p: NflPlayer, week_idx: int, weeks_left: int = 10) -> float:
    """Expected points in a week. Week 0 is ESPN's own matchup-specific
    projection; future weeks use a matchup-neutral per-week rate (ROS ÷ weeks
    left, blended with a fast-decaying bit of this week) adjusted for that
    week's opponent."""
    m = _matchup(p, week_idx)
    if m is None or m.opp in ("BYE", ""):
        return 0.0
    if week_idx == 0 and p.injury in OUT_STATUS:
        return 0.0
    if m.week in p.week_projs:
        # ESPN's projection for that week already prices the opponent in: no
        # second matchup nudge. This week's carries the experts' view too.
        return max(0.0, p.week_proj if week_idx == 0 else p.week_projs[m.week])
    if week_idx == 0:
        base = p.week_proj
    else:
        per_week = p.ros_proj / max(1, weeks_left) if p.ros_proj > 0 else p.week_proj
        form_w = max(0.03, 0.28 - 0.05 * week_idx)  # 23% wk1 -> ~3% wk6
        base = (1 - form_w) * per_week + form_w * p.week_proj
    swing = 0.05 if week_idx == 0 else 0.055 if p.pos == "QB" else 0.11 if p.pos == "DST" else 0.09
    fdr_adj = 1 + (3 - m.fdr) * swing if m.fdr else 1.0
    return max(0.0, base * fdr_adj)


# weekly PPR coefficient of variation by position — how boom/bust one start is
POS_CV = {"QB": 0.3, "RB": 0.42, "WR": 0.5, "TE": 0.55, "K": 0.44, "DST": 0.62}


def _r1(x: float) -> float:
    return math.floor(x * 10 + 0.5) / 10


def week_range(p: NflPlayer, week_idx: int = 0) -> tuple[float, float]:
    """Rough (floor, ceiling) for a week: tighter for a proven workhorse, wider
    for a committee back or thin sample; a hot player gets more downside."""
    mean = week_points(p, week_idx)
    if mean <= 0:
        return 0.0, 0.0
    cv = POS_CV.get(p.pos, 0.5)
    if p.usage_games >= 2 and p.pos in FLEX_POS:
        if p.snap_pct >= 0.78 and p.wopr >= 0.5:
            cv *= 0.82  # locked-in workhorse
        elif 0 < p.snap_pct < 0.5:
            cv *= 1.18  # committee / rotational
    hot_skew = max(-0.06, min(0.06, p.fp_oe / 60)) if p.exp_games >= 2 else 0.0
    return (
        _r1(max(0.0, mean * (1 - (0.9 + hot_skew) * cv))),
        _r1(mean * (1 + (1.15 - hot_skew) * cv)),
    )


def lineup_mode(win_pct: float, seed_by_points: bool) -> LineupMode:
    """Chase the ceiling as a clear underdog (or when the league seeds on
    points), protect the floor as a solid favourite, mean otherwise."""
    if seed_by_points or win_pct <= 40:
        return "ceiling"
    if win_pct >= 62:
        return "floor"
    return "mean"


def mode_score(mode: LineupMode) -> Callable[[NflPlayer], float]:
    def score(p: NflPlayer) -> float:
        mean = week_points(p, 0)
        if mean <= 0:
            return 0.0
        lo, hi = week_range(p, 0)
        if mode == "ceiling":
            return 0.45 * mean + 0.55 * hi
        if mode == "floor":
            return 0.55 * mean + 0.45 * lo
        return mean

    return score


def win_prob_from_margin(margin: float) -> int:
    """Win probability (0-100) from a projected margin: each team total has sd
    ~24, so the margin's sd is ~34; a logistic with scale ~19 approximates it."""
    return js_round(100 / (1 + math.exp(-margin / 19)))


@dataclass(slots=True)
class LineupSlot:
    slot: str
    player: NflPlayer | None


@dataclass(slots=True)
class Lineup:
    starters: list[LineupSlot]
    bench: list[NflPlayer]
    total: float


def optimal_lineup(
    roster: Sequence[NflPlayer],
    slots: dict[str, int],
    week_idx: int = 0,
    score_fn: Callable[[NflPlayer], float] | None = None,
) -> Lineup:
    """Fill the starting lineup greedily in slot order (QB, RB, WR, TE, FLEX,
    DST, K) from the best-scoring available players."""

    def default_score(p: NflPlayer) -> float:
        return week_points(p, week_idx)

    score = score_fn or default_score
    avail = sorted((p for p in roster if score(p) > 0), key=lambda p: -score(p))
    used: set[str] = set()
    starters: list[LineupSlot] = []
    for slot in START_ORDER:
        for _ in range(slots.get(slot, 0)):
            pick = next(
                (
                    p
                    for p in avail
                    if p.ext_id not in used
                    and (p.pos in FLEX_POS if slot == "FLEX" else p.pos == slot)
                ),
                None,
            )
            if pick is not None:
                used.add(pick.ext_id)
            starters.append(LineupSlot(slot=slot, player=pick))
    bench = sorted((p for p in roster if p.ext_id not in used), key=lambda p: -score(p))
    total = sum(score(s.player) for s in starters if s.player is not None)
    return Lineup(starters=starters, bench=bench, total=total)


def start_sit_call(p: NflPlayer, my_starters: set[str]) -> Literal["START", "SIT", "FLEX?"]:
    if p.injury in OUT_STATUS or p.on_bye:
        return "SIT"
    if p.ext_id in my_starters:
        return "START"
    return "FLEX?" if p.pos == "TE" or p.pos in FLEX_POS else "SIT"


# ---- managers ----------------------------------------------------------------------


@dataclass(slots=True)
class NflManager:
    team_id: int
    name: str
    is_mine: bool
    players: list[NflPlayer] = field(default_factory=list)
    by_pos: dict[str, list[NflPlayer]] = field(default_factory=dict)
    ros_total: int = 0


def group_teams(players: Sequence[NflPlayer], my_team_id: int | None) -> list[NflManager]:
    teams: dict[int, NflManager] = {}
    for p in players:
        if p.owner_team_id is None:
            continue
        mg = teams.get(p.owner_team_id)
        if mg is None:
            mg = NflManager(
                team_id=p.owner_team_id,
                name=p.owner_name or f"Team {p.owner_team_id}",
                is_mine=p.owner_team_id == my_team_id,
                by_pos={pos: [] for pos in ("QB", "RB", "WR", "TE", "K", "DST")},
            )
            teams[p.owner_team_id] = mg
        mg.players.append(p)
        mg.by_pos.setdefault(p.pos, []).append(p)
    for mg in teams.values():
        for pos in mg.by_pos:
            mg.by_pos[pos] = sorted(mg.by_pos[pos], key=lambda p: -p.ros_proj)
        mg.ros_total = js_round(sum(p.ros_proj for p in mg.players))
    return sorted(teams.values(), key=lambda m: (-(1 if m.is_mine else 0), -m.ros_total))


# ---- trades --------------------------------------------------------------------------


@dataclass(slots=True)
class NflTradeIdea:
    rival_name: str
    rival_team_id: int
    give: NflPlayer
    get: NflPlayer
    my_gain: int
    their_gain: int


def _xi_ros(roster: Sequence[NflPlayer], slots: dict[str, int]) -> float:
    """Your best lineup by opportunity-adjusted ROS (how YOU value it)."""
    return optimal_lineup(
        roster, slots, 0, lambda p: 0.0 if p.injury in OUT_STATUS else adj_ros(p)
    ).total


def _xi_ros_raw(roster: Sequence[NflPlayer], slots: dict[str, int]) -> float:
    """Same on the raw provider ROS — how a typical rival would value it."""
    return optimal_lineup(
        roster, slots, 0, lambda p: 0.0 if p.injury in OUT_STATUS else p.ros_proj
    ).total


def nfl_trade_ideas(
    me: NflManager, rivals: Sequence[NflManager], slots: dict[str, int]
) -> list[NflTradeIdea]:
    """1-for-1, position-matched swaps that improve your optimal lineup while
    staying roughly flat for the rival — the ones they'd accept."""
    my_base = _xi_ros(me.players, slots)
    # realistic to give: everyone outside my top 6 by opportunity-adjusted ROS
    givable = sorted(
        (p for p in me.players if p.injury not in OUT_STATUS and p.pos not in ("K", "DST")),
        key=lambda p: -adj_ros(p),
    )[6:]
    ideas: list[NflTradeIdea] = []
    for rv in rivals:
        their_base = _xi_ros_raw(rv.players, slots)
        their_givable = sorted(
            (p for p in rv.players if p.injury not in OUT_STATUS and p.pos not in ("K", "DST")),
            key=lambda p: -p.ros_proj,
        )[4:]  # not their top 4 by raw projection
        for give in givable:
            for get in their_givable:
                if give.pos != get.pos:
                    continue
                my_gain = (
                    _xi_ros([p for p in me.players if p.ext_id != give.ext_id] + [get], slots)
                    - my_base
                )
                their_gain = (
                    _xi_ros_raw([p for p in rv.players if p.ext_id != get.ext_id] + [give], slots)
                    - their_base
                )
                if my_gain > 4 and their_gain > -3:
                    ideas.append(
                        NflTradeIdea(
                            rv.name, rv.team_id, give, get, js_round(my_gain), js_round(their_gain)
                        )
                    )
    ranked = sorted(ideas, key=lambda t: -(t.my_gain + t.their_gain))
    seen: set[str] = set()
    out: list[NflTradeIdea] = []
    for t in ranked:
        key = f"{t.rival_team_id}|{t.get.ext_id}"
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:10]


# ---- fixture ticker + team watch ---------------------------------------------------------


@dataclass(slots=True)
class NflClubFix:
    team: str
    cells: list[WeekOpp]
    avg_fdr: float


def nfl_club_fixtures(players: Sequence[NflPlayer]) -> list[NflClubFix]:
    seen: dict[str, NflPlayer] = {}
    for p in players:
        if not p.team or p.team in seen:
            continue
        if p.matchups:
            seen[p.team] = p
    out = []
    for team, p in seen.items():
        rated = [c for c in p.matchups if c.fdr]
        avg = sum(c.fdr for c in rated) / len(rated) if rated else 3.0
        out.append(NflClubFix(team=team, cells=p.matchups, avg_fdr=avg))
    return sorted(out, key=lambda c: (c.avg_fdr, *team_sort_key(c.team)))


STARTER_CAP = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "K": 1, "DST": 1}


@dataclass(slots=True)
class NflClubDossier:
    team: str
    fixtures: list[WeekOpp]
    avg_fdr: float
    starters: list[NflPlayer]
    bench: list[NflPlayer]
    doubts: list[NflPlayer]
    bye: int


def nfl_club_dossiers(players: Sequence[NflPlayer]) -> list[NflClubDossier]:
    by_team: dict[str, list[NflPlayer]] = {}
    for p in players:
        if p.team:
            by_team.setdefault(p.team, []).append(p)
    fx = {c.team: c for c in nfl_club_fixtures(players)}
    out = []
    for team, roster in by_team.items():
        c = fx.get(team)
        starters: list[NflPlayer] = []
        bench: list[NflPlayer] = []
        for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
            # ESPN "% started" is the crowd's read on the depth chart; ties on ROS
            ranked = sorted(
                (p for p in roster if p.pos == pos and p.injury not in OUT_STATUS),
                key=lambda p: (-p.pct_started, -p.ros_proj),
            )
            starters.extend(ranked[: STARTER_CAP[pos]])
            bench.extend(ranked[STARTER_CAP[pos] : STARTER_CAP[pos] + 1])
        out.append(
            NflClubDossier(
                team=team,
                fixtures=c.cells if c else [],
                avg_fdr=c.avg_fdr if c else 3.0,
                starters=starters,
                bench=bench,
                doubts=sorted((p for p in roster if p.injury != "ACTIVE"), key=lambda p: -p.ros_proj),
                bye=next((p.bye for p in roster if p.bye), 0),
            )
        )
    return sorted(out, key=lambda d: (d.avg_fdr, *team_sort_key(d.team)))


# ---- playoff odds (Monte Carlo) ------------------------------------------------------------


@dataclass(slots=True)
class Standing:
    team_id: int
    name: str
    wins: int
    losses: int
    ties: int
    pf: float


@dataclass(slots=True)
class Game:
    week: int
    home: int
    away: int


@dataclass(slots=True)
class PlayoffOdds:
    team_id: int
    name: str
    is_mine: bool
    proj_wins: float
    proj_pf: float  # projected season points-for
    playoff_pct: float
    bye_pct: float  # P(top-2 seed)


def sim_playoffs(
    managers: Sequence[NflManager],
    standings: Sequence[Standing],
    schedule: Sequence[Game],
    slots: dict[str, int],
    current_week: int,
    reg_weeks: int,
    playoff_teams: int,
    my_team_id: int | None,
    seeding_rule: str = "H2H_RECORD",
    iters: int = 3000,
    rng: np.random.Generator | None = None,
) -> list[PlayoffOdds]:
    """Simulate the rest of the regular season `iters` times. Each team's weekly
    score is Normal(projected best lineup × a season-long strength wobble, 24);
    seeding by record (then points) or by total points."""
    rng = rng or np.random.default_rng()
    by_points = seeding_rule == "TOTAL_POINTS_SCORED"
    team_ids = [m.team_id for m in managers]
    if not team_ids:
        return []
    # Schedule teams with no rostered players still play their games (at a
    # flat 90-point projection), they just aren't seeded.
    ghosts = sorted(
        {t for g in schedule for t in (g.home, g.away)} - set(team_ids)
    )
    all_ids = team_ids + ghosts
    idx = {t: i for i, t in enumerate(all_ids)}
    n_all, n_teams = len(all_ids), len(team_ids)
    rec0 = np.zeros(n_all)
    pf0 = np.zeros(n_all)
    for s in standings:
        if s.team_id in idx:
            rec0[idx[s.team_id]] = s.wins + 0.5 * s.ties
            pf0[idx[s.team_id]] = s.pf

    # each team's projected weekly score (best lineup for that week index)
    weeks = list(range(current_week, reg_weeks + 1))
    week_score = np.full((n_all, max(1, len(weeks))), 90.0)
    def scorer(wi: int, wl: int) -> Callable[[NflPlayer], float]:
        def score(pl: NflPlayer) -> float:
            return week_points(pl, wi, wl)

        return score

    for m in managers:
        for wi, w in enumerate(weeks):
            week_score[idx[m.team_id], wi] = optimal_lineup(
                m.players, slots, wi, scorer(wi, reg_weeks - w + 1)
            ).total

    games = [g for g in schedule if current_week <= g.week <= reg_weeks]
    wins = np.tile(rec0, (iters, 1))
    pf = np.tile(pf0, (iters, 1))
    # a season-long strength wobble per team — rosters drift (waivers,
    # injuries, breakouts), so the projection itself is uncertain
    strength = np.ones((iters, n_all))
    strength[:, :n_teams] = np.maximum(0.7, rng.normal(1.0, 0.06, size=(iters, n_teams)))
    for g in games:
        h, a, wi = idx[g.home], idx[g.away], g.week - current_week
        hs = rng.normal(week_score[h, wi] * strength[:, h], 24)
        as_ = rng.normal(week_score[a, wi] * strength[:, a], 24)
        pf[:, h] += np.maximum(0, hs)
        pf[:, a] += np.maximum(0, as_)
        wins[:, h] += np.where(hs > as_, 1.0, np.where(hs == as_, 0.5, 0.0))
        wins[:, a] += np.where(as_ > hs, 1.0, np.where(hs == as_, 0.5, 0.0))

    # seed the rostered teams only: primary then secondary key, both descending
    # (lexsort sorts by its last key first and is stable, like Array.sort)
    w_m, pf_m = wins[:, :n_teams], pf[:, :n_teams]
    primary, secondary = (pf_m, w_m) if by_points else (w_m, pf_m)
    order = np.lexsort((-secondary, -primary), axis=1)
    seed = np.empty_like(order)
    seed[np.arange(iters)[:, None], order] = np.arange(n_teams)[None, :]
    made = (seed < playoff_teams).mean(axis=0) * 100
    byes = (seed < 2).mean(axis=0) * 100

    out = [
        PlayoffOdds(
            team_id=m.team_id,
            name=m.name,
            is_mine=m.team_id == my_team_id,
            proj_wins=float(wins[:, idx[m.team_id]].mean()),
            proj_pf=float(pf[:, idx[m.team_id]].mean()),
            playoff_pct=float(made[idx[m.team_id]]),
            bye_pct=float(byes[idx[m.team_id]]),
        )
        for m in managers
    ]
    return sorted(out, key=lambda o: (-o.playoff_pct, -o.proj_pf))
