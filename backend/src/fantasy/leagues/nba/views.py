"""ESPN basketball pages, assembled from the database.

Everything is relative to "today": the scoring period for today's US Eastern
date (or, in the demo, the period the seed pinned). The current matchup is
the one containing today, and "days left" runs from today to its last day.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fantasy.api.schemas import nba as S
from fantasy.api.schemas.common import CheckItem
from fantasy.config import Docs
from fantasy.core import models as M
from fantasy.core.store import get_document
from fantasy.leagues.nba import analysis as A
from fantasy.leagues.nba.league import ET
from fantasy.leagues.nba.players import OUT_STATUS, NbaPlayer

POSITIONS = ("PG", "SG", "SF", "PF", "C")


@dataclass(slots=True)
class League:
    name: str
    players: list[NbaPlayer]
    my_team_id: int | None
    entries: list[M.LeagueEntry]
    matchups: list[M.Matchup]
    slot_counts: dict[str, int]
    ir_slots: int
    limits: dict[str, int]
    periods: dict[int, tuple[int, int]]
    day_dates: dict[int, date]
    games: dict[int, dict[int, tuple[int, bool]]]
    abbrev: dict[int, str]
    pro_names: dict[int, str]
    team_names: dict[int, str]
    today: int
    pinned: bool  # the demo fixes "today"
    reg_periods: int
    playoff_periods: list[int]
    playoff_teams: int
    acquisitions: dict[str, Any]
    trade_deadline: str | None
    warnings: list[str]
    _days: dict[str, list[int]] = field(default_factory=dict)

    # ---- the calendar ----

    @property
    def slots(self) -> list[str]:
        return A.slot_list(self.slot_counts)

    @property
    def period(self) -> int:
        for mp, (_, last) in sorted(self.periods.items()):
            if self.today <= last:
                return mp
        return max(self.periods) if self.periods else 1

    @property
    def season_over(self) -> bool:
        return bool(self.periods) and self.today > max(b for _, b in self.periods.values())

    def period_days(self, mp: int, from_today: bool = True) -> list[int]:
        a, b = self.periods.get(mp, (0, -1))
        return list(range(max(a, self.today) if from_today else a, b + 1))

    @property
    def days_left(self) -> list[int]:
        if "left" not in self._days:
            self._days["left"] = [] if self.season_over else self.period_days(self.period)
        return self._days["left"]

    @property
    def next_days(self) -> list[int]:
        if "next" not in self._days:
            self._days["next"] = self.period_days(self.period + 1, from_today=False)
        return self._days["next"]

    @property
    def ros_days(self) -> list[int]:
        """Today to the end of the regular season."""
        if "ros" not in self._days:
            end = self.periods.get(self.reg_periods, (0, -1))[1]
            self._days["ros"] = list(range(self.today, end + 1))
        return self._days["ros"]

    @property
    def playoff_days(self) -> list[int]:
        if "po" not in self._days:
            self._days["po"] = [d for mp in self.playoff_periods for d in self.period_days(mp)]
        return self._days["po"]

    def date(self, day: int) -> date | None:
        return self.day_dates.get(day)

    def tonight(self, p: NbaPlayer, day: int | None = None) -> str:
        g = self.games.get(p.pro_team_id, {}).get(self.today if day is None else day)
        if not g:
            return ""
        return f"{'vs' if g[1] else '@'} {self.abbrev.get(g[0], '?')}"

    # ---- teams ----

    def roster_of(self, team_id: int | None) -> list[NbaPlayer]:
        return [p for p in self.players if team_id is not None and p.owner_team_id == team_id]

    @property
    def my_roster(self) -> list[NbaPlayer]:
        return self.roster_of(self.my_team_id)

    def match_of(self, team_id: int | None, mp: int) -> M.Matchup | None:
        me = str(team_id)
        return next((m for m in self.matchups if m.round == mp and me in (m.home_entry, m.away_entry)),
                    None)


def _int_keys(d: Any) -> dict[int, Any]:
    return {int(k): v for k, v in (d or {}).items() if str(k).lstrip("-").isdigit()}


def today_day(day_dates: dict[int, date], now: datetime | None = None) -> int:
    """The scoring period for today in US Eastern time (the next one with games
    if today has none; day 1 before the season)."""
    today = (now or datetime.now(UTC)).astimezone(ET).date()
    later = [d for d, v in day_dates.items() if v >= today]
    if later:
        return min(later)
    return max(day_dates) + 1 if day_dates else 1


def load(session: Session, now: datetime | None = None) -> League:
    doc: dict[str, Any] = get_document(session, Docs.NBA_LEAGUE) or {}
    rows = session.scalars(select(M.DraftPlayer).where(M.DraftPlayer.sport == "nba")).all()
    players = sorted((NbaPlayer.from_row(r) for r in rows), key=lambda p: (-p.fppg, p.ext_id))
    entries = list(session.scalars(select(M.LeagueEntry).where(M.LeagueEntry.sport == "nba")))
    day_dates = {k: date.fromisoformat(v) for k, v in _int_keys(doc.get("dayDates")).items()}
    pro = _int_keys(doc.get("proTeams"))
    pinned = doc.get("today")
    my_team = doc.get("myTeamId")
    return League(
        name=str(doc.get("name") or ""),
        players=players,
        my_team_id=int(my_team) if my_team is not None else None,
        entries=entries,
        matchups=list(session.scalars(select(M.Matchup).where(M.Matchup.sport == "nba"))),
        slot_counts={str(k): int(v) for k, v in (doc.get("slots") or {}).items()},
        ir_slots=int(doc.get("ir") or 0),
        limits={str(k): int(v) for k, v in (doc.get("limits") or {}).items()},
        periods={k: (int(v[0]), int(v[1])) for k, v in _int_keys(doc.get("periods")).items()},
        day_dates=day_dates,
        games={k: {int(d): (int(g[0]), bool(g[1])) for d, g in (v.get("games") or {}).items()}
               for k, v in pro.items()},
        abbrev={k: str(v.get("abbrev") or "") for k, v in pro.items()},
        pro_names={k: str(v.get("name") or "") for k, v in pro.items()},
        team_names={int(e.entry_id): e.name for e in entries if e.entry_id.isdigit()},
        today=int(pinned) if pinned else today_day(day_dates, now),
        pinned=bool(pinned),
        reg_periods=int(doc.get("regPeriods") or 0),
        playoff_periods=[int(x) for x in doc.get("playoffPeriods") or []],
        playoff_teams=int(doc.get("playoffTeams") or 4),
        acquisitions=dict(doc.get("acquisitions") or {}),
        trade_deadline=doc.get("tradeDeadline"),
        warnings=[str(w) for w in doc.get("warnings") or []],
    )


# ---- players out --------------------------------------------------------------------------


def week_points(p: NbaPlayer, lg: League) -> float:
    """Expected points over the days left in this matchup if he started every
    game (an injury tag fading over the days)."""
    return sum(A.game_value(p, d - lg.today) for d in lg.days_left if A.plays(p, d, lg.games))


def out(p: NbaPlayer, lg: League) -> S.NbaPlayer:
    left = A.games_in(p, lg.days_left, lg.games)
    return S.NbaPlayer(
        ext_id=p.ext_id, name=p.name, team=p.team, pos=p.pos, positions=p.positions, slots=p.slots,
        fppg=round(p.fppg, 1), fppg_proj=round(p.fppg_proj, 1), fppg_now=round(p.fppg_now, 1),
        gp_now=p.gp_now, fppg_last=round(p.fppg_last, 1), fppg_l15=round(p.fppg_l15, 1),
        gp_l15=p.gp_l15, line=S.NbaLine.model_validate(p.line), line_source=p.line_source,
        injury=p.injury, pct_owned=p.pct_owned, pct_started=p.pct_started,
        pct_change=p.pct_change, status=p.status, owner_team_id=p.owner_team_id,
        owner_name=p.owner_name, slot=p.slot, adp=p.adp,
        games_left=left, games_next=A.games_in(p, lg.next_days, lg.games),
        week_points=round(week_points(p, lg), 1),
        ros=round(A.ros_value(p, lg.ros_days, lg.games)),
        playoff_games=A.games_in(p, lg.playoff_days, lg.games),
        today=lg.tonight(p),
    )


def outs(ps: Sequence[NbaPlayer], lg: League) -> list[S.NbaPlayer]:
    return [out(p, lg) for p in ps]


def _ros(lg: League) -> Callable[[NbaPlayer], float]:
    return lambda p: A.ros_value(p, lg.ros_days, lg.games)


def _stream_out(s: A.Stream, lg: League) -> S.NbaStream:
    return S.NbaStream(add=out(s.add, lg), drop=out(s.drop, lg), gain=round(s.gain, 1),
                       games=s.games, ros_delta=round(s.ros_delta))


def _free(lg: League) -> list[NbaPlayer]:
    return [p for p in lg.players if p.available and p.pro_team_id]


# ---- overview -----------------------------------------------------------------------------


def _score(lg: League, mp: int, days: list[int], plan: A.WeekPlan) -> S.NbaScore | None:
    match = lg.match_of(lg.my_team_id, mp)
    if match is None:
        return None
    home = match.home_entry == str(lg.my_team_id)
    opp_id = int(match.away_entry if home else match.home_entry)
    opp_plan = A.plan_days(lg.roster_of(opp_id), days, lg.games, lg.slots)
    mine = (match.home_points if home else match.away_points) or 0.0
    theirs = (match.away_points if home else match.home_points) or 0.0
    return S.NbaScore(
        my_points=round(mine, 1), my_remaining=round(plan.total, 1),
        my_proj=round(mine + plan.total, 1), opp_name=lg.team_names.get(opp_id),
        opp_points=round(theirs, 1), opp_remaining=round(opp_plan.total, 1),
        opp_proj=round(theirs + opp_plan.total, 1),
        win_pct=None if match.finished else A.win_prob(mine, plan, theirs, opp_plan),
    )


def _moves(lg: League) -> S.NbaMoves:
    acq = lg.acquisitions
    limit = acq.get("limit")
    used = int((acq.get("used") or {}).get(str(lg.period), 0))
    per_day = bool(acq.get("perDay"))
    days = ", ".join(d.title() for d in acq.get("waiverDays") or [])
    note = (f"Dropped players sit on waivers {acq.get('waiverHours')}h"
            + (f"; claims process {days}" if days else "")) if acq.get("waiverHours") else ""
    return S.NbaMoves(limit=limit, per_day=per_day, used=used,
                      left=None if limit is None or per_day else max(0, int(limit) - used),
                      waiver_note=note)


def _today_moves(lg: League, roster: list[NbaPlayer]) -> tuple[list[NbaPlayer], list[NbaPlayer]]:
    """(start these tonight, bench these) against the lineup ESPN has set."""
    if lg.today not in lg.days_left:
        return [], []
    playing = [p for p in roster if p.slot != "IR" and A.plays(p, lg.today, lg.games)]
    seats, _ = A.best_lineup(playing, A.game_value, lg.slots)
    best = {s.player.ext_id for s in seats if s.player}
    start = [p for p in roster if p.ext_id in best and p.slot in ("BE", "")]
    bench = [p for p in roster if p.slot not in ("BE", "IR", "") and p.ext_id not in best]
    return start, (bench if start else [])


def _when(lg: League, pinned: bool, now: datetime | None = None) -> str:
    """How to name the next scoring period: "Tonight", or its date when the
    next games are days away (preseason, the All-Star break)."""
    d = lg.date(lg.today)
    if d is None or pinned or d == (now or datetime.now(UTC)).astimezone(ET).date():
        return "Tonight"
    return f"{d:%a %b} {d.day}"


def _checklist(lg: League, roster: list[NbaPlayer], plan: A.WeekPlan,
               streams: list[A.Stream], score: S.NbaScore | None, moves: S.NbaMoves,
               when: str) -> list[CheckItem]:
    items: list[CheckItem] = []
    start, bench = _today_moves(lg, roster)
    if lg.today in lg.days_left:
        if start:
            text = f"{when}: start " + ", ".join(p.name for p in start)
            if bench:
                text += " over " + ", ".join(p.name for p in bench)
            items.append(CheckItem(ok=False, text=text, href="/nba/lineup", link_text="open Lineup →"))
        elif any(A.plays(p, lg.today, lg.games) for p in roster if p.slot != "IR"):
            items.append(CheckItem(ok=True, text=f"{when}: your lineup starts everyone it can"))
        else:
            items.append(CheckItem(ok=True, text=f"{when}: none of your players has a game"))
    healthy_ir = [p for p in roster if p.slot == "IR" and p.injury not in OUT_STATUS]
    if healthy_ir:
        items.append(CheckItem(
            ok=False, href="/nba/lineup", link_text="open Lineup →",
            text=f"{', '.join(p.name for p in healthy_ir)} is healthy but on IR — activate before "
            "ESPN blocks your other moves"))
    on_ir = [p for p in roster if p.slot == "IR"]
    out_active = [p for p in roster if p.slot != "IR" and p.injury in OUT_STATUS]
    if out_active and len(on_ir) < lg.ir_slots:
        items.append(CheckItem(
            ok=False, href="/nba/players", link_text="find a pickup →",
            text=f"Move {out_active[0].name} ({out_active[0].injury.replace('_', ' ').lower()}) to IR "
            "and use the roster spot"))
    elif out_active:
        items.append(CheckItem(
            ok=False, href="/nba/players", link_text="see free agents →",
            text=f"{', '.join(p.name for p in out_active)} {'is' if len(out_active) == 1 else 'are'} "
            f"out with your IR full ({', '.join(p.name for p in on_ir)}) — a roster spot not playing"))
    if plan.days:
        if plan.lost >= 3:
            items.append(CheckItem(
                ok=False, href="/nba/lineup", link_text="see the days →",
                text=f"{plan.lost} games lost to your bench this matchup — a 2-for-1 trade or a "
                "drop opens room for games on lighter days"))
        keeper = next((s for s in streams if s.ros_delta >= -50), None)
        if keeper is not None and keeper.gain >= 10:
            s = keeper
            items.append(CheckItem(
                ok=False, href="/nba/players", link_text="see streams →",
                text=f"Stream {s.add.name} for {s.drop.name}: +{s.gain:.0f} this matchup "
                f"({s.games} games)"))
        elif not plan.lost:
            items.append(CheckItem(ok=True, text="No games lost to your bench this matchup"))
    if score and score.win_pct is not None:
        if score.win_pct < 40:
            items.append(CheckItem(
                ok=False, href="/nba/players", link_text="find games →",
                text=f"Underdog vs {score.opp_name} ({score.win_pct}%) — games played decide "
                "points leagues: add volume"))
        else:
            items.append(CheckItem(
                ok=True, text=f"{'Favoured' if score.win_pct >= 60 else 'Close'} vs "
                f"{score.opp_name} ({score.win_pct}% win)"))
    if moves.left is not None:
        items.append(CheckItem(ok=moves.left > 0,
                               text=f"{moves.left} of {moves.limit} pickups left this matchup"))
    if lg.trade_deadline:
        left = datetime.fromisoformat(lg.trade_deadline) - datetime.now(UTC)
        if timedelta(0) < left < timedelta(days=7):
            items.append(CheckItem(ok=False, href="/nba/trade", link_text="open Trade →",
                                   text=f"Trade deadline in {left.days} days"))
    return items


def overview(session: Session) -> S.NbaOverview:
    lg = load(session)
    roster = lg.my_roster
    left = lg.days_left
    plan = A.plan_days(roster, left, lg.games, lg.slots)
    score = _score(lg, lg.period, left, plan)
    starts = Counter(s.player.ext_id for d in plan.days for s in d.seats if s.player)
    lost = Counter(p.ext_id for d in plan.days for p in d.benched)
    today_plan = next((d for d in plan.days if d.day == lg.today), None)
    tonight = {s.player.ext_id for s in today_plan.seats if s.player} if today_plan else set()

    def call(p: NbaPlayer) -> S.TodayCall:
        if p.slot == "IR":
            return "IR"
        if p.injury in OUT_STATUS:
            return "out"
        if not A.plays(p, lg.today, lg.games) or today_plan is None:
            return "no game"
        return "start" if p.ext_id in tonight else "bench"

    streams = A.streams(roster, _free(lg), left, lg.games, lg.slots, _ros(lg), lg.limits)
    moves = _moves(lg)
    when = _when(lg, lg.pinned)
    a, b = lg.periods.get(lg.period, (0, 0))
    first, last = lg.date(a), lg.date(b)
    return S.NbaOverview(
        league_name=lg.name, period=lg.period,
        first_date=first.isoformat() if first else None,
        last_date=last.isoformat() if last else None,
        today_date=d.isoformat() if (d := lg.date(lg.today)) else None,
        days_left=len(left), is_playoffs=lg.period in lg.playoff_periods,
        season_over=lg.season_over, has_roster=bool(roster), score=score,
        checklist=_checklist(lg, roster, plan, streams, score, moves, when) if roster else [],
        roster=[
            S.NbaRosterRow(player=out(p, lg), starts=starts[p.ext_id], lost=lost[p.ext_id],
                           today=call(p))
            for p in sorted(roster, key=lambda p: (p.slot == "IR", -p.fppg, p.ext_id))
        ],
        streams=[_stream_out(s, lg) for s in streams[:5]],
        moves=moves, warnings=lg.warnings,
    )


# ---- lineup -------------------------------------------------------------------------------


def lineup_page(session: Session) -> S.NbaLineup:
    lg = load(session)
    roster = lg.my_roster
    plan = A.plan_days(roster, lg.days_left, lg.games, lg.slots)
    start, bench = _today_moves(lg, roster)

    def day_out(d: A.DayPlan) -> S.NbaDay:
        when = lg.date(d.day)
        return S.NbaDay(
            day=d.day, date=when.isoformat() if when else "",
            weekday=when.strftime("%a") if when else "",
            seats=[S.NbaSeat(slot=s.slot, player=out(s.player, lg) if s.player else None,
                             opp=lg.tonight(s.player, d.day) if s.player else "")
                   for s in d.seats],
            benched=outs(d.benched, lg),
            idle=outs([p for p in d.idle if p.slot != "IR"], lg),
            points=round(d.points, 1), open_slots=d.open_slots,
        )

    return S.NbaLineup(
        period=lg.period, has_roster=bool(roster), days=[day_out(d) for d in plan.days],
        total=round(plan.total, 1), games=plan.games, lost=plan.lost, open_slots=plan.open_slots,
        today_start=outs(start, lg), today_bench=outs(bench, lg),
    )


# ---- players ------------------------------------------------------------------------------


def players_page(session: Session, sort: S.NbaSort, position: str, show: S.NbaShow) -> S.NbaPlayersResponse:
    lg = load(session)
    ros = _ros(lg)

    def value(p: NbaPlayer) -> float:
        if sort == "week":
            return week_points(p, lg)
        if sort == "ros":
            return ros(p)
        if sort == "trend":
            return p.pct_change
        return p.fppg

    pool = [
        p for p in lg.players
        if p.pro_team_id and (show == "all" or p.available)
        and (position == "ALL" or position in p.positions)
    ]
    pool.sort(key=lambda p: (-value(p), -p.fppg, p.ext_id))
    streams = A.streams(lg.my_roster, _free(lg), lg.days_left, lg.games, lg.slots, ros, lg.limits)
    return S.NbaPlayersResponse(
        period=lg.period, sort=sort, position=position, show=show,
        rows=[S.NbaFreeAgent(player=out(p, lg), value=round(value(p), 1)) for p in pool[:60]],
        streams=[_stream_out(s, lg) for s in streams[:8]],
    )


# ---- schedule -----------------------------------------------------------------------------


def schedule_page(session: Session) -> S.NbaScheduleResponse:
    lg = load(session)
    if not lg.periods:
        return S.NbaScheduleResponse(periods=[], teams=[], days=[])
    wanted = sorted({*(mp for mp in range(lg.period, lg.period + 4) if mp in lg.periods),
                     *(mp for mp in lg.playoff_periods if mp >= lg.period)})
    periods = []
    spans = {}
    for mp in wanted:
        days = lg.period_days(mp, from_today=mp == lg.period)
        spans[mp] = days
        a, b = (days[0], days[-1]) if days else lg.periods[mp]
        periods.append(S.NbaPeriod(
            period=mp, first_date=(lg.date(a) or date.min).isoformat(),
            last_date=(lg.date(b) or date.min).isoformat(), days=len(days),
            playoffs=mp in lg.playoff_periods))
    mine = Counter(p.pro_team_id for p in lg.my_roster)
    teams = [
        S.NbaTeamGames(team=lg.abbrev.get(tid, "?"), name=lg.pro_names.get(tid, ""),
                       games=[sum(1 for d in spans[mp] if d in g) for mp in wanted],
                       mine=mine.get(tid, 0))
        for tid, g in lg.games.items()
    ]
    teams.sort(key=lambda t: (-t.games[0] if t.games else 0, t.team))
    look = lg.days_left + lg.next_days
    per_day = {d: sum(1 for g in lg.games.values() if d in g) // 2 for d in look}
    busy = [n for n in per_day.values() if n]
    light = max(4.0, 0.6 * statistics.median(busy)) if busy else 0.0
    active = [p for p in lg.my_roster if p.slot != "IR"]
    day_rows = []
    for d in look:
        when = lg.date(d)
        n = per_day[d]
        day_rows.append(S.NbaDayCount(
            day=d, date=when.isoformat() if when else "", weekday=when.strftime("%a") if when else "",
            games=n, my_games=sum(1 for p in active if A.plays(p, d, lg.games)),
            light=0 < n <= light))
    return S.NbaScheduleResponse(periods=periods, teams=teams, days=day_rows)


# ---- standings ----------------------------------------------------------------------------


def _period_strength(lg: League, rosters: dict[int, list[NbaPlayer]]) -> dict[tuple[int, int], tuple[float, float]]:
    """(team, period) → (mean, variance) of the team's points: banked plus the
    lineup-aware projection for the current period, the fast estimate after."""
    out: dict[tuple[int, int], tuple[float, float]] = {}
    cap = len(lg.slots)
    for tid, roster in rosters.items():
        for mp in range(lg.period, lg.reg_periods + 1):
            if mp == lg.period:
                plan = A.plan_days(roster, lg.days_left, lg.games, lg.slots)
                m = lg.match_of(tid, mp)
                banked = 0.0
                if m is not None:
                    banked = (m.home_points if m.home_entry == str(tid) else m.away_points) or 0.0
                out[(tid, mp)] = (banked + plan.total, plan.variance * A.WEEK_NOISE**2)
            else:
                out[(tid, mp)] = A.team_period(roster, lg.period_days(mp, False), lg.games, cap)
    return out


def standings_page(session: Session) -> S.NbaStandingsResponse:
    lg = load(session)
    ids = sorted(lg.team_names)
    rosters = {t: lg.roster_of(t) for t in ids}
    standings = [
        A.Standing(team_id=int(e.entry_id), wins=e.wins or 0, losses=e.losses or 0,
                   ties=e.draws or 0, points_for=e.points_for or 0.0)
        for e in lg.entries if e.entry_id.isdigit()
    ]
    strength = _period_strength(lg, rosters) if lg.periods and not lg.season_over else {}
    remaining = [
        (m.round, int(m.home_entry), int(m.away_entry)) for m in lg.matchups
        if lg.period <= m.round <= lg.reg_periods and not m.finished
        and m.home_entry.isdigit() and m.away_entry.isdigit()
    ]
    # a projection is least certain in preseason; the doubt shrinks as the season is played
    left_share = max(0.0, (lg.reg_periods - lg.period + 1) / max(1, lg.reg_periods))
    odds = {o.team_id: o for o in A.sim_playoffs(standings, remaining, strength, lg.playoff_teams,
                                                  strength_sd=0.08 * math.sqrt(left_share))} \
        if standings and strength else {}
    by_id = {e.entry_id: e for e in lg.entries}
    table = sorted(standings, key=lambda s: (-(s.wins + 0.5 * s.ties), s.losses, -s.points_for))
    rows = []
    for i, s in enumerate(table):
        e = by_id[str(s.team_id)]
        o = odds.get(s.team_id)
        rows.append(S.NbaStandingRow(
            team_id=s.team_id, name=e.name, wins=s.wins, losses=s.losses, ties=s.ties,
            pf=round(s.points_for, 1), pa=round(e.points_against or 0.0, 1),
            mine=s.team_id == lg.my_team_id, in_line=i < lg.playoff_teams,
            playoff_pct=o.playoff_pct if o else None, top_seed_pct=o.top_seed_pct if o else None,
            proj_wins=o.proj_wins if o else None))

    upcoming = []
    if lg.my_team_id is not None:
        for mp in range(lg.period, min(lg.period + 4, lg.reg_periods + 1)):
            m = lg.match_of(lg.my_team_id, mp)
            if m is None or not (m.home_entry.isdigit() and m.away_entry.isdigit()):
                continue
            home = m.home_entry == str(lg.my_team_id)
            opp = int(m.away_entry if home else m.home_entry)
            mine = strength.get((lg.my_team_id, mp))
            theirs = strength.get((opp, mp))
            win = None
            if mine and theirs and (mine[1] + theirs[1]) > 0:
                z = (mine[0] - theirs[0]) / math.sqrt(mine[1] + theirs[1])
                win = max(1, min(99, round(50 * (1 + math.erf(z / math.sqrt(2))))))
            upcoming.append(S.NbaUpcoming(period=mp, opp_name=lg.team_names.get(opp, "?"),
                                          my_proj=round(mine[0]) if mine else 0,
                                          opp_proj=round(theirs[0]) if theirs else 0, win_pct=win))
    po = list(lg.playoff_periods)
    games = []
    for p in sorted(lg.my_roster, key=lambda p: -p.fppg):
        by = [A.games_in(p, lg.period_days(mp, False), lg.games) for mp in po]
        games.append(S.NbaPlayoffGames(player=out(p, lg), by_period=by, total=sum(by)))
    return S.NbaStandingsResponse(
        rows=rows, playoff_teams=lg.playoff_teams, reg_periods=lg.reg_periods, playoff_periods=po,
        upcoming=upcoming, playoff_games=games, trade_deadline=lg.trade_deadline,
    )


# ---- rivals -------------------------------------------------------------------------------


def _team(lg: League, team_id: int) -> S.NbaTeam:
    e = next((x for x in lg.entries if x.entry_id == str(team_id)), None)
    roster = lg.roster_of(team_id)
    plan = A.plan_days(roster, lg.days_left, lg.games, lg.slots)
    return S.NbaTeam(
        team_id=team_id, name=lg.team_names.get(team_id, f"Team {team_id}"),
        is_mine=team_id == lg.my_team_id, wins=(e.wins or 0) if e else 0,
        losses=(e.losses or 0) if e else 0, ties=(e.draws or 0) if e else 0,
        pf=round((e.points_for or 0.0) if e else 0.0, 1), week_proj=round(plan.total, 1),
        players=outs(sorted(roster, key=lambda p: (-p.fppg, p.ext_id)), lg),
    )


def rivals_page(session: Session) -> S.NbaRivalsResponse:
    lg = load(session)
    teams = [_team(lg, t) for t in sorted(lg.team_names)]
    teams.sort(key=lambda t: (not t.is_mine, -(t.wins + 0.5 * t.ties), t.losses, -t.pf))
    return S.NbaRivalsResponse(period=lg.period, teams=teams)


# ---- trades -------------------------------------------------------------------------------


def trade_lab(session: Session, rival_id: int | None) -> S.NbaTradeLab:
    lg = load(session)
    others = [t for t in sorted(lg.team_names) if t != lg.my_team_id]
    rival = rival_id if rival_id in others else (others[0] if others else None)
    ideas = A.trade_ideas(lg.my_roster, {t: lg.roster_of(t) for t in others}, lg.ros_days,
                          lg.games) if lg.my_roster else []
    return S.NbaTradeLab(
        me=_team(lg, lg.my_team_id) if lg.my_team_id is not None else None,
        rivals=[_team(lg, t) for t in others],
        rival=_team(lg, rival) if rival is not None else None,
        ideas=[S.NbaTradeIdea(rival_id=i.rival_id, rival_name=lg.team_names.get(i.rival_id, "?"),
                              give=out(i.give, lg), get=out(i.get, lg), my_gain=round(i.my_gain),
                              their_gain=round(i.their_gain)) for i in ideas],
        weeks_left=round(len(lg.ros_days) / 7, 1), trade_deadline=lg.trade_deadline,
    )


def evaluate_trade(session: Session, give_ids: Sequence[str], get_ids: Sequence[str]) -> S.NbaTradeEvaluation:
    lg = load(session)
    by_id = {p.ext_id: p for p in lg.players}
    give = [by_id[x] for x in give_ids if x in by_id]
    get = [by_id[x] for x in get_ids if x in by_id]
    ev = A.evaluate_trade(lg.my_roster, give, get, _free(lg), lg.days_left, lg.ros_days,
                          lg.playoff_days, lg.games, lg.slots)
    return S.NbaTradeEvaluation(
        my_ros=round(ev.my_ros), my_week=round(ev.my_week, 1), their_ros=round(ev.their_ros),
        my_playoff_games=ev.my_playoff_games, roster_moves=ev.roster_moves,
        warnings=ev.warnings, verdict=ev.verdict,
    )
