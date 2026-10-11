"""FPL Draft decision logic: best XI, waiver and trade evaluation, rival
modelling, club dossiers. Pure functions over `FplPlayer` lists.

Ported from the old web app's `app/fpl/lib.ts` (it used to run in the
browser); `tests/test_parity_fpl.py` checks the port against that code.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from fantasy.football.formation import pick_formation_xi
from fantasy.football.jsmath import js_round, js_to_fixed, round1
from fantasy.leagues.fpl.players import FplPlayer

Horizon = Literal["short", "medium", "season"]
HORIZON_LABEL: dict[str, str] = {
    "short": "next GW",
    "medium": "next 6 GW",
    "season": "rest of season",
}
POSITIONS = ("GKP", "DEF", "MID", "FWD")

XI_MIN = {"GKP": 1, "DEF": 3, "MID": 3, "FWD": 1}
XI_MAX = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}

Score = Callable[[FplPlayer], float]


def _proj(p: FplPlayer) -> float:
    return p.proj


def rosterable(p: FplPlayer) -> bool:
    """A player you'd actually claim/trade for right now: fit and expected to play."""
    return not p.unavailable and p.status == "a"


def sort_players(players: Iterable[FplPlayer], key: str) -> list[FplPlayer]:
    def value(p: FplPlayer) -> float:
        return float(getattr(p, key))

    return sorted(players, key=lambda p: (-value(p), -p.horizon))


# ---- lineups ---------------------------------------------------------------------


@dataclass(slots=True)
class Lineup:
    xi: list[FplPlayer]
    bench: list[FplPlayer]
    formation: str


def best_xi(squad: Sequence[FplPlayer], score: Score = _proj) -> Lineup:
    """Best legal XI by a per-player score. No captain: draft scores every
    starter once."""
    by_pos: dict[str, list[FplPlayer]] = {pos: [] for pos in POSITIONS}
    for p in squad:
        by_pos.setdefault(p.pos, []).append(p)
    for pos in by_pos:
        by_pos[pos] = sorted(by_pos[pos], key=lambda p: -score(p))

    xi: list[FplPlayer] = []
    count = {pos: 0 for pos in POSITIONS}
    for pos in POSITIONS:
        for p in by_pos[pos][: XI_MIN[pos]]:
            xi.append(p)
            count[pos] += 1
    in_xi = {p.ext_id for p in xi}
    rest = sorted(
        (p for p in squad if p.ext_id not in in_xi and p.pos != "GKP"), key=lambda p: -score(p)
    )
    for p in rest:
        if len(xi) >= 11:
            break
        if p.pos in XI_MAX and count[p.pos] < XI_MAX[p.pos]:
            xi.append(p)
            count[p.pos] += 1
    starting = {p.ext_id for p in xi}
    bench = sorted(
        (p for p in squad if p.ext_id not in starting),
        key=lambda p: (1 if p.pos == "GKP" else 0, -score(p)),
    )
    return Lineup(xi=xi, bench=bench, formation=f"{count['DEF']}-{count['MID']}-{count['FWD']}")


def squad_horizon(squad: Sequence[FplPlayer], gw_indexes: Iterable[int]) -> float:
    """Total from the best XI each gameweek."""
    total = 0.0
    for gi in gw_indexes:
        xi = best_xi(squad, lambda p, gi=gi: p.gw_xpts(gi)).xi
        total += sum(p.gw_xpts(gi) for p in xi)
    return total


# ---- horizon-aware value ---------------------------------------------------------

XGI_BENCH = {"MID": 0.35, "FWD": 0.55}
XGC_AVG = 1.35


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def opp_factor(p: FplPlayer) -> float:
    """Underlying-stats nudge, bounded to ±~10%: MID/FWD season xGI/90 against a
    solid-starter benchmark; DEF/GKP season xGC/90 against the league average.
    1.0 when the sample is thin (<270 min) or the stat is missing."""
    if p.minutes < 270:
        return 1.0
    if p.pos in ("MID", "FWD"):
        bench = XGI_BENCH[p.pos]
        if not p.xgi90:
            return 1.0
        return 1 + _clamp(((p.xgi90 - bench) / bench) * 0.15, -0.08, 0.1)
    if p.pos in ("DEF", "GKP"):
        if not p.xgc90:
            return 1.0
        return 1 + _clamp(((XGC_AVG - p.xgc90) / XGC_AVG) * 0.12, -0.07, 0.09)
    return 1.0


def opp_tag(p: FplPlayer) -> str:
    """"value" (underlying beats output) | "output-led" (living off returns) | ""."""
    f = opp_factor(p)
    return "value" if f >= 1.06 else "output-led" if f <= 0.95 else ""


def value_for(p: FplPlayer, h: str) -> float:
    base = p.proj if h == "short" else p.horizon if h == "medium" else p.ros
    return base * opp_factor(p)


def rank_to_ppg(rank: int) -> float:
    """Points per game a player of this draft rank typically returns — a stable
    floor that doesn't move with a hot or cold month."""
    r = rank or 9999
    if r <= 8:
        return 6.0
    if r <= 20:
        return 5.2
    if r <= 45:
        return 4.6
    if r <= 90:
        return 4.0
    if r <= 160:
        return 3.4
    if r <= 280:
        return 2.8
    return 2.2


def window_gws(p: FplPlayer, h: str) -> int:
    if h == "short":
        return 1
    if h == "medium":
        return max(1, sum(1 for g in p.gws if g.opp))
    return max(1, js_round(p.ros / p.ros_ppg)) if p.ros_ppg > 0 else 20


def neutral_value(p: FplPlayer, h: str) -> float:
    """What a typical rival would value the player at over a window — season
    output plus a draft-rank floor, deliberately NOT our form-sensitive
    projection, so an "easy sell" is one both sides think they win."""
    if p.unavailable:
        return 0.0
    rate = 0.62 * p.ppg + 0.38 * rank_to_ppg(p.provider_rank)
    avail = 0.55 + 0.45 * min(1.0, p.p_start / 0.9)
    return rate * window_gws(p, h) * avail


def xi_value(squad: Sequence[FplPlayer], h: str) -> float:
    """Value of the best startable XI over a window — what actually moves your
    score. A player who doesn't crack the XI contributes ~0."""
    if h == "medium":
        return squad_horizon(squad, range(6))

    def key(p: FplPlayer) -> float:
        return p.gw_xpts(0) if h == "short" else p.ros

    return sum(key(p) for p in best_xi(squad, key).xi)


def claimable(p: FplPlayer, h: str) -> bool:
    if not rosterable(p):
        return False
    if h == "short":
        return p.p_start >= 0.55  # has to actually feature this week
    if p.susp_risk and p.yc_to_ban <= 1:
        return False
    return p.p_start >= 0.6


# ---- waivers -----------------------------------------------------------------------


@dataclass(slots=True)
class Upgrade:
    out: FplPlayer
    in_: FplPlayer
    gain: float


def weak_spots(
    lineup: Sequence[FplPlayer], free_agents: Sequence[FplPlayer], h: str = "medium"
) -> list[Upgrade]:
    """Starters worth replacing for the window: genuinely below replacement
    level, or a real rotation/injury risk. A nailed premium is never a weak spot
    just because someone projects a hair higher."""
    fit_free = [p for p in free_agents if claimable(p, h)]

    def val(p: FplPlayer) -> float:
        return value_for(p, h)

    repl: dict[str, float] = {}
    for pos in POSITIONS:
        ranked = sorted((p for p in fit_free if p.pos == pos), key=lambda p: -val(p))
        # ~3rd-best startable free agent = replacement level
        repl[pos] = val(ranked[2]) if len(ranked) > 2 else val(ranked[-1]) if ranked else 0.0
    bar = 1.5 if h == "short" else 6 if h == "medium" else 18
    out: list[Upgrade] = []
    for s in lineup:
        # An elite draft asset (top ~20) whose projection looks weak is almost
        # always a thin-sample artefact — a new signing, an injury returnee.
        if s.provider_rank and s.provider_rank <= 20:
            continue
        cands = sorted((p for p in fit_free if p.pos == s.pos), key=lambda p: -val(p))
        if not cands:
            continue
        best = cands[0]
        gain = val(best) - val(s)
        below_repl = val(s) < repl.get(s.pos, 0.0) - 1
        risky = 0 < s.p_start < 0.6
        if (below_repl or risky) and gain > bar:
            out.append(Upgrade(out=s, in_=best, gain=gain))
    return sorted(out, key=lambda u: -u.gain)[:6]


LONG_TERM_NEWS = re.compile(
    r"unknown return|out for the season|long[- ]term|acl|achilles|surgery|"
    r"expected back .*(oct|nov|dec|jan)",
    re.I,
)
RETURN_SOON = re.compile(r"expected back|late fitness test|knock|assessed|day[- ]to[- ]day", re.I)


def stash_candidates(players: Sequence[FplPlayer], mine_ids: set[str]) -> list[FplPlayer]:
    """Injured players worth a bench spot: only genuine difference-makers, and
    only true superstars for a long lay-off."""

    def keep(p: FplPlayer) -> bool:
        if not p.available or p.ext_id in mine_ids or not p.unavailable:
            return False
        if p.status in ("u", "n"):
            return False
        elite = p.provider_rank <= 30 or p.fit_horizon / 6 >= 5.8
        if not elite:
            return False
        long_term = bool(LONG_TERM_NEWS.search(p.news)) or (
            p.status == "i" and not RETURN_SOON.search(p.news)
        )
        return not (long_term and p.provider_rank > 12)

    return sorted(
        (p for p in players if keep(p)), key=lambda p: (p.provider_rank, -p.fit_horizon)
    )[:6]


# ---- managers + trades ---------------------------------------------------------------


@dataclass(slots=True)
class Manager:
    entry_id: str
    name: str
    is_mine: bool
    players: list[FplPlayer] = field(default_factory=list)
    by_pos: dict[str, list[FplPlayer]] = field(default_factory=dict)
    total_medium: float = 0.0
    total_season: float = 0.0


def group_by_manager(
    players: Sequence[FplPlayer],
    my_entry_id: str | None,
    fallback_names: dict[str, str] | None = None,
) -> list[Manager]:
    """Current rosters from live ownership (`owner` = element-status entry id),
    not the draft history."""
    fallback_names = fallback_names or {}
    mine = "null" if my_entry_id is None else str(my_entry_id)
    managers: dict[str, Manager] = {}
    for pl in players:
        if not pl.owner:
            continue
        key = str(pl.owner)
        mg = managers.get(key)
        if mg is None:
            mg = Manager(
                entry_id=key,
                name=pl.owner_name or fallback_names.get(key) or f"Team {key}",
                is_mine=key == mine,
                by_pos={pos: [] for pos in POSITIONS},
            )
            managers[key] = mg
        if pl.owner_name and (mg.name.startswith("Team ") or not mg.name):
            mg.name = pl.owner_name
        mg.players.append(pl)
        mg.by_pos.setdefault(pl.pos, []).append(pl)
    for mg in managers.values():
        for pos in mg.by_pos:
            mg.by_pos[pos] = sorted(mg.by_pos[pos], key=lambda p: -p.horizon)
        mg.total_medium = round1(sum(p.horizon for p in mg.players))
        mg.total_season = round1(sum(p.ros for p in mg.players))
    return sorted(managers.values(), key=lambda m: (-(1 if m.is_mine else 0), -m.total_season))


def _pos_key(ps: Sequence[FplPlayer]) -> str:
    return "+".join(sorted(p.pos for p in ps))


@dataclass(slots=True)
class TradeIdea:
    rival_name: str
    give: list[FplPlayer]
    get: list[FplPlayer]
    my_gain: float
    their_gain: float


def trade_ideas(
    my_squad: Sequence[FplPlayer],
    players: Sequence[FplPlayer],
    owners: dict[str, tuple[str, set[str]]],
    max_n: int = 4,
    h: str = "medium",
) -> list[TradeIdea]:
    """Position-balanced trades (1-for-1 up to 2-for-2) ranked by the gain to the
    XI you'd field, keeping the rival roughly whole by neutral value so they'd
    plausibly accept. `owners`: entry id -> (name, owned ext ids)."""
    ideas: list[TradeIdea] = []
    # lineup-delta eval is O(best_xi) per candidate: cap the auto-suggester at
    # 2-for-2 (bigger deals are rare and go through the manual trade lab).
    n_max = min(max_n, 2, len(my_squad))
    before = xi_value(my_squad, h)

    def my_delta(give: Sequence[FplPlayer], get: Sequence[FplPlayer]) -> float:
        give_ids = {p.ext_id for p in give}
        after = [p for p in my_squad if p.ext_id not in give_ids] + list(get)
        return round1(xi_value(after, h) - before)

    def nsum(ps: Sequence[FplPlayer]) -> float:
        return sum(neutral_value(p, h) for p in ps)

    # realistic things to give up: my weakest ~9 by neutral value
    givable = sorted(my_squad, key=lambda p: neutral_value(p, h))[:9]
    give_by_key: dict[str, list[tuple[FplPlayer, ...]]] = {}
    for n in range(1, n_max + 1):
        for g in itertools.combinations(givable, n):
            give_by_key.setdefault(_pos_key(g), []).append(g)

    for entry, (name, ids) in owners.items():
        theirs = [p for p in players if p.ext_id in ids and claimable(p, h)]
        if not theirs:
            continue
        for n in range(1, min(n_max, len(theirs)) + 1):
            for get in itertools.combinations(theirs, n):
                for give in give_by_key.get(_pos_key(get), []):
                    my_gain = my_delta(give, get)
                    their_gain = round1(nsum(give) - nsum(get))
                    bar = 3 if h == "season" else 1.2 if n == 1 else 2
                    floor = -8 if h == "season" else -3
                    if my_gain > bar and their_gain > floor:
                        ideas.append(
                            TradeIdea(name or entry, list(give), list(get), my_gain, their_gain)
                        )
    ranked = sorted(ideas, key=lambda t: (-(t.my_gain + min(0.0, t.their_gain)), len(t.give)))
    seen: set[str] = set()
    out: list[TradeIdea] = []
    for t in ranked:
        key = t.rival_name + "|" + ",".join(sorted(p.ext_id for p in t.get))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:12]


@dataclass(slots=True)
class TradeEval:
    balanced: bool
    pos_give: str
    pos_get: str
    me_short: float
    me_medium: float
    me_season: float
    them_short: float
    them_medium: float
    them_season: float
    warnings: list[str]
    verdict: str


def evaluate_trade(
    give: Sequence[FplPlayer], get: Sequence[FplPlayer], my_squad: Sequence[FplPlayer] = ()
) -> TradeEval:
    """A concrete proposed trade. `me_*` is the change to the XI you can field;
    `them_*` is the rival's swing valued neutrally, so positive means they'd
    want it too."""
    pos_give, pos_get = _pos_key(give), _pos_key(get)
    balanced = len(give) == len(get) and pos_give == pos_get
    give_ids = {p.ext_id for p in give}
    before = list(my_squad) if my_squad else list(give)
    after = [p for p in my_squad if p.ext_id not in give_ids] + list(get) if my_squad else list(get)

    me = {h: round1(xi_value(after, h) - xi_value(before, h)) for h in HORIZON_LABEL}

    def nsum(ps: Sequence[FplPlayer], h: str) -> float:
        return sum(neutral_value(p, h) for p in ps)

    them = {h: round1(nsum(give, h) - nsum(get, h)) for h in HORIZON_LABEL}

    warnings: list[str] = []
    for p in get:
        if p.susp_risk:
            warnings.append(f"{p.name} is {p.yc_to_ban} booking from a ban")
        if p.unavailable:
            state = "suspended" if p.status == "s" else "injured"
            warnings.append(f"{p.name} is currently {state}" + (f" — {p.news}" if p.news else ""))
        if p.p_start < 0.7:
            warnings.append(f"{p.name} isn't a nailed starter (p≈{js_round(p.p_start * 100)}%)")
        if opp_tag(p) == "output-led":
            warnings.append(
                f"{p.name}'s returns are ahead of the underlying (xGI/90 "
                f"{js_to_fixed(p.xgi90, 2)}) — regression risk, you may be buying a peak"
            )
    for p in give:
        if opp_tag(p) == "value":
            warnings.append(
                f"{p.name}'s xGI/90 ({js_to_fixed(p.xgi90, 2)}) is strong — the underlying "
                "backs a bounce, don't undersell"
            )
    if balanced and me["season"] > 2 and them["season"] < -3:
        warnings.append(
            "Lopsided in your favour by neutral value — the rival is unlikely to accept as-is."
        )

    short_win = me["short"] > 0.3
    long_win = me["season"] > 2
    if not balanced:
        verdict = "Not position-balanced — a draft trade needs the same positions on both sides."
    elif me["season"] <= -2:
        verdict = "You lose startable value over the season — don't, unless it patches an injury hole now."
    elif short_win and long_win:
        verdict = (
            "Upgrades your XI now and rest-of-season, and the rival isn't losing much — propose it."
            if them["season"] > -3
            else "Upgrades your XI, but skewed in your favour — sweeten it or expect a no."
        )
    elif long_win:
        verdict = "Rest-of-season upgrade to your XI, roughly flat this week."
    elif short_win:
        verdict = "Helps this week but not the season — only if you're chasing points now."
    else:
        verdict = "Marginal — barely changes the XI you'd field."
    return TradeEval(
        balanced=balanced,
        pos_give=pos_give,
        pos_get=pos_get,
        me_short=me["short"],
        me_medium=me["medium"],
        me_season=me["season"],
        them_short=them["short"],
        them_medium=them["medium"],
        them_season=them["season"],
        warnings=warnings,
        verdict=verdict,
    )


# ---- fixtures + clubs ---------------------------------------------------------------


def team_sort_key(name: str) -> tuple[str, str]:
    """Approximates JS localeCompare for club names: case-insensitive first."""
    return (name.casefold(), name)


@dataclass(slots=True)
class ClubCell:
    gw: int
    opp: str
    home: bool | None
    fdr: int
    fdr_att: int
    fdr_def: int


@dataclass(slots=True)
class ClubFix:
    team: str
    cells: list[ClubCell]
    avg_fdr: float


_HOME_AWAY_SUFFIX = re.compile(r" \(.\)$")


def club_fixtures(players: Sequence[FplPlayer]) -> list[ClubFix]:
    """One fixture run per PL club, carrying both position-neutral axes so the
    ticker can be read for attackers or defenders."""
    seen: dict[str, FplPlayer] = {}
    for p in players:
        if not p.team or p.team in seen:
            continue
        if p.gws:
            seen[p.team] = p
    out: list[ClubFix] = []
    for team, p in seen.items():
        cells = [
            ClubCell(
                gw=g.gw,
                opp=_HOME_AWAY_SUFFIX.sub("", g.opp),
                home=g.home,
                fdr=g.fdr,
                fdr_att=g.fdr_att if g.fdr_att is not None else g.fdr,
                fdr_def=g.fdr_def if g.fdr_def is not None else g.fdr,
            )
            for g in p.gws
        ]
        rated = [c for c in cells if c.fdr_att]
        avg = sum(c.fdr_att for c in rated) / len(rated) if rated else 3.0
        out.append(ClubFix(team=team, cells=cells, avg_fdr=avg))
    return sorted(out, key=lambda c: (c.avg_fdr, *team_sort_key(c.team)))


def start_score(p: FplPlayer) -> float:
    """Chance a player starts — modelled p_start, else a prior from ROS output."""
    if p.p_start > 0:
        return p.p_start
    return max(0.12, min(0.7, p.ros_ppg / 6))


@dataclass(slots=True)
class ClubDossier:
    team: str
    fixtures: list[ClubCell]
    avg_fdr: float
    probable_xi: list[FplPlayer]
    bench: list[FplPlayer]
    set_pieces: dict[str, list[FplPlayer]]
    doubts: list[FplPlayer]
    key_players: list[FplPlayer]


def club_dossiers(players: Sequence[FplPlayer]) -> list[ClubDossier]:
    by_team: dict[str, list[FplPlayer]] = {}
    for p in players:
        if p.team:
            by_team.setdefault(p.team, []).append(p)
    fx = {c.team: c for c in club_fixtures(players)}

    def has(p: FplPlayer, tag: str) -> bool:
        return tag in [x.strip() for x in (p.set_piece or "").split(",")]

    out: list[ClubDossier] = []
    for team, roster in by_team.items():
        c = fx.get(team)
        pool = [p for p in roster if p.status == "a"]
        picked = pick_formation_xi(
            pool,
            is_gk=lambda p: p.pos == "GKP",
            is_def=lambda p: p.pos == "DEF",
            is_mid=lambda p: p.pos == "MID",
            is_fwd=lambda p: p.pos == "FWD",
            score=start_score,
        )
        out.append(
            ClubDossier(
                team=team,
                fixtures=c.cells if c else [],
                avg_fdr=c.avg_fdr if c else 3.0,
                probable_xi=picked.xi,
                bench=picked.bench,
                set_pieces={
                    "pk": [p for p in roster if has(p, "P")],
                    "fk": [p for p in roster if has(p, "F")],
                    "ck": [p for p in roster if has(p, "C")],
                },
                doubts=sorted(
                    (p for p in roster if p.unavailable or p.status != "a"),
                    key=lambda p: -p.total_points,
                ),
                key_players=sorted(roster, key=lambda p: -p.ros)[:5],
            )
        )
    return sorted(out, key=lambda d: (d.avg_fdr, *team_sort_key(d.team)))


# ---- rivals' likely waiver claims -------------------------------------------------------


@dataclass(slots=True)
class ClaimPrediction:
    rival_name: str
    weak_pos: str
    weak_starter: str
    target: FplPlayer
    gain: int


def predict_claims(
    managers: Sequence[Manager], players: Sequence[FplPlayer], my_entry_id: str | None
) -> list[ClaimPrediction]:
    owned = {p.ext_id for m in managers for p in m.players}
    free = [p for p in players if p.ext_id not in owned and p.status == "a" and not p.unavailable]
    mine = "null" if my_entry_id is None else str(my_entry_id)
    out: list[ClaimPrediction] = []
    for mg in managers:
        if mg.is_mine or mg.entry_id == mine:
            continue
        xi = best_xi(mg.players, lambda p: p.ros).xi
        # the weakest starter a rival would realistically move on — not an
        # elite asset they're holding through a slow start
        cands = sorted(
            (p for p in xi if not (p.provider_rank and p.provider_rank <= 20)), key=lambda p: p.ros
        )
        if not cands:
            continue
        weak = cands[0]
        targets = sorted((p for p in free if p.pos == weak.pos), key=lambda p: -p.ros)
        if targets and targets[0].ros - weak.ros > 15:
            t = targets[0]
            out.append(ClaimPrediction(mg.name, weak.pos, weak.name, t, js_round(t.ros - weak.ros)))
    return sorted(out, key=lambda c: -c.gain)
