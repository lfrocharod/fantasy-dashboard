"""ESPN fantasy basketball: league rules, fantasy teams, matchups and the
matchup calendar, parsed from the raw API payloads. Pure functions, no network.

Basketball scores by the day: every NBA game day is a scoring period, a lineup
is set per day (locking game by game), and a head-to-head matchup period spans
a run of days. ESPN publishes which week units make up each matchup period but
not their dates, so `build_calendar` derives them from the NBA schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# ESPN lineup slot ids for basketball
SLOT = {
    0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 7: "SG/SF", 8: "G/F",
    9: "PF/C", 10: "F/C", 11: "UT", 12: "BE", 13: "IR",
}
POS = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}
RESERVE = ("BE", "IR")
# Scoring stat ids → labels (the ones a league can score on).
STAT = {
    0: "PTS", 1: "BLK", 2: "STL", 3: "AST", 4: "OREB", 5: "DREB", 6: "REB", 7: "EJ", 8: "FF",
    9: "PF", 10: "TF", 11: "TO", 12: "DQ", 13: "FGM", 14: "FGA", 15: "FTM", 16: "FTA", 17: "3PM",
    18: "3PA", 19: "FG%", 20: "FT%", 21: "3P%", 37: "DD", 38: "TD", 39: "QD", 40: "MIN", 41: "GS",
    42: "GP",
}
# NBA game times are US Eastern; a scoring period is an Eastern calendar day.
ET = ZoneInfo("America/New_York")


def default_season(now: datetime | None = None) -> int:
    """ESPN numbers an NBA season by the year it ends: 2026-27 is 2027."""
    now = now or datetime.now(UTC)
    return now.year + 1 if now.month >= 8 else now.year


def _num(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


@dataclass(slots=True)
class Rules:
    """How the league is set up: scoring, lineup, schedule, transactions."""

    name: str
    scoring_type: str  # H2H_POINTS | H2H_CATEGORY | H2H_MOST_CATEGORIES | ROTO ...
    scoring: dict[int, float]  # stat id → points per unit
    slots: dict[str, int]  # starting lineup slots, e.g. {"PG": 1, …, "UT": 3}
    bench: int
    ir: int
    position_limits: dict[str, int]  # roster maximum by position, e.g. {"C": 4}
    reg_periods: int  # regular-season matchup periods
    playoff_periods: list[int]
    playoff_teams: int
    seeding_rule: str
    matchup_units: dict[int, list[int]]  # matchup period → the week units it spans
    first_day: int
    final_day: int
    current_period: int  # ESPN's, as of the pull
    acquisition_limit: int | None  # None = unlimited
    acquisition_per_day: bool  # the limit counts per scoring period, not per matchup
    waiver_hours: int
    waiver_days: list[str]
    trade_deadline: str | None  # ISO-8601 (UTC)
    lineup_lock: str  # INDIVIDUAL_GAME | FIRSTGAME_SCORINGPERIOD ...

    @property
    def is_points(self) -> bool:
        return "POINTS" in self.scoring_type


def parse_rules(league: dict[str, Any]) -> Rules:
    sett = league.get("settings", {}) or {}
    sc = sett.get("scoringSettings", {}) or {}
    roster = sett.get("rosterSettings", {}) or {}
    sched = sett.get("scheduleSettings", {}) or {}
    acq = sett.get("acquisitionSettings", {}) or {}
    trade = sett.get("tradeSettings", {}) or {}
    status = league.get("status", {}) or {}

    slots: dict[str, int] = {}
    bench = ir = 0
    for sid, n in (roster.get("lineupSlotCounts") or {}).items():
        label, n = SLOT.get(int(sid)), int(n or 0)
        if not label or n <= 0:
            continue
        if label == "BE":
            bench += n
        elif label == "IR":
            ir += n
        else:
            slots[label] = slots.get(label, 0) + n
    limits = {
        POS[int(k)]: int(v) for k, v in (roster.get("positionLimits") or {}).items()
        if int(k) in POS and int(v) > 0
    }
    units = {
        int(k): [int(u) for u in v] for k, v in (sched.get("matchupPeriods") or {}).items() if v
    }
    reg = int(sched.get("matchupPeriodCount") or 0) or (min(units) if units else 1)
    limit = acq.get("matchupAcquisitionLimit")
    deadline = trade.get("deadlineDate")
    return Rules(
        name=str(sett.get("name") or ""),
        scoring_type=str(sc.get("scoringType") or ""),
        scoring={int(i["statId"]): _num(i.get("points")) for i in sc.get("scoringItems", [])
                 if "statId" in i},
        slots=slots, bench=bench, ir=ir, position_limits=limits,
        reg_periods=reg,
        playoff_periods=sorted(p for p in units if p > reg),
        playoff_teams=int(sched.get("playoffTeamCount") or 4),
        # The seeding rule ESPN reports breaks ties on head-to-head record;
        # basketball leagues seed on record, so record it is.
        seeding_rule=str(sched.get("playoffSeedingRule") or "H2H_RECORD"),
        matchup_units=units,
        first_day=int(status.get("firstScoringPeriod") or 1),
        final_day=int(status.get("finalScoringPeriod") or 0),
        current_period=int(status.get("currentMatchupPeriod") or 1),
        acquisition_limit=int(limit) if limit is not None and _num(limit) >= 0 else None,
        acquisition_per_day=bool(acq.get("matchupLimitPerScoringPeriod")),
        waiver_hours=int(acq.get("waiverHours") or 0),
        waiver_days=[str(d) for d in acq.get("waiverProcessDays") or []],
        trade_deadline=(datetime.fromtimestamp(deadline / 1000, UTC).isoformat()
                        if isinstance(deadline, (int, float)) and deadline > 0 else None),
        lineup_lock=str(roster.get("lineupLocktimeType") or ""),
    )


# ---- the NBA schedule --------------------------------------------------------------------


@dataclass(slots=True)
class ProTeam:
    id: int
    abbrev: str
    name: str
    games: dict[int, tuple[int, bool]] = field(default_factory=dict)  # day → (opponent id, home)
    tips: dict[int, int] = field(default_factory=dict)  # day → tip-off, epoch ms


def pro_teams(pro_schedule: dict[str, Any]) -> tuple[dict[int, ProTeam], dict[int, date]]:
    """Every NBA team with its games by scoring period, and each period's date."""
    teams: dict[int, ProTeam] = {}
    day_dates: dict[int, date] = {}
    for t in (pro_schedule.get("settings", {}) or {}).get("proTeams", []) or []:
        tid = int(t.get("id") or 0)
        if not tid:  # id 0 is ESPN's "free agent" pseudo-team
            continue
        team = ProTeam(id=tid, abbrev=str(t.get("abbrev") or "").upper(),
                       name=f"{t.get('location', '')} {t.get('name', '')}".strip())
        for sp, games in (t.get("proGamesByScoringPeriod") or {}).items():
            for g in games or []:
                home, away = int(g.get("homeProTeamId") or 0), int(g.get("awayProTeamId") or 0)
                day = int(g.get("scoringPeriodId") or sp)
                team.games[day] = (away if home == tid else home, home == tid)
                when = g.get("date")
                if isinstance(when, (int, float)):
                    team.tips[day] = int(when)
                    if day not in day_dates:
                        day_dates[day] = datetime.fromtimestamp(when / 1000, UTC).astimezone(ET).date()
        teams[tid] = team
    return teams, day_dates


@dataclass(slots=True)
class Calendar:
    """Scoring periods (days) and how matchup periods group them."""

    day_dates: dict[int, date]  # every day from 1 to the last one with a game
    periods: dict[int, tuple[int, int]]  # matchup period → (first day, last day)
    warnings: list[str] = field(default_factory=list)

    def period_of(self, day: int) -> int:
        for mp, (_, last) in sorted(self.periods.items()):
            if day <= last:
                return mp
        return max(self.periods) if self.periods else 1

    def days(self, period: int) -> range:
        a, b = self.periods.get(period, (0, -1))
        return range(a, b + 1)

    def day_of(self, d: date) -> int:
        """The scoring period for a calendar date: that day, or the next one
        if nothing is scheduled (before the season: day 1)."""
        later = [k for k, v in self.day_dates.items() if v >= d]
        return min(later) if later else (max(self.day_dates) + 1 if self.day_dates else 1)


def build_calendar(rules: Rules, day_dates: dict[int, date]) -> Calendar:
    """Matchup period → day range. Week units after the first are Monday–Sunday;
    the first unit runs from opening night and takes whatever length makes the
    units add up to the league's final scoring period (ESPN stretches the
    opening week rather than leave a stub of a few days)."""
    warnings: list[str] = []
    if not day_dates:
        return Calendar({}, {}, ["no NBA schedule"])
    first = min(day_dates)
    d0 = day_dates[first] - timedelta(days=first - 1)
    last = max(max(day_dates), rules.final_day)
    full = {d: d0 + timedelta(days=d - 1) for d in range(1, last + 1)}
    for d, real in day_dates.items():
        if full[d] != real:
            warnings.append(f"day {d} is dated {real}, expected {full[d]}")
            full[d] = real

    n_units = max((u for us in rules.matchup_units.values() for u in us), default=0)
    final = rules.final_day or last
    if n_units < 1:
        return Calendar(full, {1: (1, final)}, warnings + ["no matchup periods in the settings"])
    first_len = final - 7 * (n_units - 1)
    if first_len < 1:
        warnings.append(f"{n_units} week units don't fit in {final} days; using 7-day units")
        first_len = 7

    def unit(u: int) -> tuple[int, int]:
        if u == 1:
            return 1, first_len
        start = first_len + 7 * (u - 2) + 1
        return start, start + 6

    periods = {}
    for mp, us in sorted(rules.matchup_units.items()):
        spans = [unit(u) for u in us]
        periods[mp] = (min(a for a, _ in spans), max(b for _, b in spans))
    if n_units > 1 and full.get(first_len + 1) and full[first_len + 1].weekday() != 0:
        warnings.append(f"week 2 starts on {full[first_len + 1]:%A}, not a Monday — check the calendar")
    return Calendar(full, periods, warnings)


def check_calendar(cal: Calendar, matchups: list[Matchup]) -> list[str]:
    """Days ESPN has actually scored, per matchup period, against the derived
    calendar — a mismatch means the derivation is off for this season."""
    out = []
    for m in matchups:
        days = m.home_days + m.away_days
        if not days:
            continue
        a, b = cal.periods.get(m.period, (0, -1))
        stray = sorted({d for d in days if not a <= d <= b})
        if stray:
            out.append(f"matchup {m.period} scored on days {stray} outside {a}–{b}")
    return out


# ---- fantasy teams, rosters, matchups ---------------------------------------------------


@dataclass(slots=True)
class FantasyTeam:
    id: int
    name: str
    abbrev: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    seed: int | None
    waiver_rank: int | None
    acquisitions: dict[int, int]  # matchup period → adds made
    roster: list[tuple[int, str]]  # (player id, lineup slot label)


def team_name(t: dict[str, Any]) -> str:
    return (t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
            or f"Team {t.get('id')}")


def parse_teams(league: dict[str, Any]) -> list[FantasyTeam]:
    out = []
    for t in league.get("teams", []) or []:
        rec = (t.get("record", {}) or {}).get("overall", {}) or {}
        tc = t.get("transactionCounter", {}) or {}
        roster = []
        for e in (t.get("roster", {}) or {}).get("entries", []) or []:
            pid = e.get("playerId") or (e.get("playerPoolEntry", {}) or {}).get("id")
            if pid:
                roster.append((int(pid), SLOT.get(int(e.get("lineupSlotId", 12)), "BE")))
        out.append(FantasyTeam(
            id=int(t["id"]), name=team_name(t), abbrev=str(t.get("abbrev") or ""),
            wins=int(rec.get("wins") or 0), losses=int(rec.get("losses") or 0),
            ties=int(rec.get("ties") or 0),
            points_for=round(_num(rec.get("pointsFor")), 1),
            points_against=round(_num(rec.get("pointsAgainst")), 1),
            seed=int(t["playoffSeed"]) if t.get("playoffSeed") else None,
            waiver_rank=int(t["waiverRank"]) if t.get("waiverRank") else None,
            acquisitions={int(k): int(v) for k, v in
                          (tc.get("matchupAcquisitionTotals") or {}).items()},
            roster=roster,
        ))
    return out


@dataclass(slots=True)
class Matchup:
    period: int
    home: int
    away: int
    home_points: float
    away_points: float
    winner: str  # HOME | AWAY | TIE | UNDECIDED
    home_days: list[int] = field(default_factory=list)  # days ESPN has scored
    away_days: list[int] = field(default_factory=list)


def parse_matchups(league: dict[str, Any]) -> list[Matchup]:
    out = []
    for m in league.get("schedule", []) or []:
        h, a = m.get("home", {}) or {}, m.get("away", {}) or {}
        if not (h.get("teamId") and a.get("teamId")):
            continue  # a playoff bye

        def pts(side: dict[str, Any]) -> float:
            live = side.get("totalPointsLive")
            return round(_num(live if live is not None else side.get("totalPoints")), 1)

        def days(side: dict[str, Any]) -> list[int]:
            return sorted(int(k) for k, v in (side.get("pointsByScoringPeriod") or {}).items() if v)

        out.append(Matchup(
            period=int(m.get("matchupPeriodId") or 0), home=int(h["teamId"]), away=int(a["teamId"]),
            home_points=pts(h), away_points=pts(a), winner=str(m.get("winner") or "UNDECIDED"),
            home_days=days(h), away_days=days(a),
        ))
    return out
