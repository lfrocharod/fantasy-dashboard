"""`fantasy sync nba`: pull the ESPN league, its player pool and the NBA
schedule, then write the player board, the league tables (standings,
matchups, your roster) and the `nba.league` document (rules, the matchup
calendar, every NBA team's games).

Settings live under `draft.nba.*` (league id, your team id, the season). A
private league needs the ESPN `espn_s2` / `SWID` cookies; with none stored for
basketball the NFL ones are used, since it's the same ESPN account.
"""

from __future__ import annotations

from typing import Any

from fantasy.config import Docs, Env
from fantasy.core.db import DB
from fantasy.leagues.draft.sync import _espn_cookies, config_for
from fantasy.leagues.nba import board, espn
from fantasy.leagues.nba import league as L
from fantasy.leagues.nba.league import default_season


def _log(m: str) -> None:
    print(f"[nba] {m}", flush=True)


def cookies(db: DB, env: Env | None) -> tuple[str | None, str | None]:
    s2, swid = _espn_cookies(config_for(db, "nba"), env)
    if not (s2 and swid):
        s2, swid = _espn_cookies(config_for(db, "nfl"), env)
    return s2, swid


def run(db: DB, env: Env) -> int:  # pragma: no cover - network
    cfg = config_for(db, "nba")
    league_id = cfg.get("league_id")
    if not league_id:
        _log("skipped — set the league in Settings (NBA)")
        return 0
    s2, swid = cookies(db, env)
    if not (s2 and swid):
        _log("no ESPN login stored (NBA or NFL setup) — a private league will refuse this")
    season = int(cfg.get("year") or default_season())
    my_team = int(cfg["my_team_id"]) if str(cfg.get("my_team_id") or "").isdigit() else None
    with espn.client(s2, swid) as c:
        lg = espn.fetch_league(c, season, league_id)
        pool = espn.fetch_players(c, season, league_id, limit=600)
        schedule = espn.fetch_pro_schedule(c, season)
    store(db, lg, pool, schedule, season, my_team)
    return 0


def store(db: DB, lg: dict[str, Any], pool: list[dict[str, Any]], schedule: dict[str, Any],
          season: int, my_team: int | None, pinned_today: int | None = None) -> None:
    """Write everything one pull produced. The demo seed calls this with a
    simulated league and `pinned_today` (a fixed scoring period)."""
    rules = L.parse_rules(lg)
    pro, day_dates = L.pro_teams(schedule)
    cal = L.build_calendar(rules, day_dates)
    teams = L.parse_teams(lg)
    matchups = L.parse_matchups(lg)
    for w in cal.warnings + L.check_calendar(cal, matchups):
        _log(f"calendar: {w}")
    rostered = {
        int(e["playerId"]): e["playerPoolEntry"]
        for t in lg.get("teams", []) or []
        for e in (t.get("roster", {}) or {}).get("entries", []) or []
        if e.get("playerId") and e.get("playerPoolEntry")
    }
    rows = board.build_rows(pool, teams, rules, pro, season, rostered)
    db.replace_draft_players("nba", rows)

    names = {t.id: t.name for t in teams}
    db.upsert_league(
        "nba", name=rules.name, scoring=rules.scoring_type, n_teams=len(teams),
        current_round=rules.current_period, regular_rounds=rules.reg_periods,
        playoff_rounds=rules.playoff_periods, playoff_teams=rules.playoff_teams,
        seeding_rule=rules.seeding_rule, lineup_slots=rules.slots,
        roster={"bench": rules.bench, "ir": rules.ir, "limits": rules.position_limits},
    )
    db.replace_league_entries("nba", [
        {"entry_id": t.id, "name": t.name, "is_mine": t.id == my_team, "rank": t.seed,
         "wins": t.wins, "draws": t.ties, "losses": t.losses,
         "points_for": t.points_for, "points_against": t.points_against}
        for t in teams
    ])
    db.replace_matchups("nba", [
        {"round": m.period, "home_entry": m.home, "away_entry": m.away,
         "home_name": names.get(m.home, ""), "away_name": names.get(m.away, ""),
         "home_points": m.home_points, "away_points": m.away_points, "winner": m.winner,
         "finished": m.winner in ("HOME", "AWAY", "TIE")}
        for m in matchups
    ])
    mine = next((t for t in teams if t.id == my_team), None)
    db.replace_my_lineup("nba", [
        {"ext_id": pid, "starter": slot not in L.RESERVE, "source": "espn"}
        for pid, slot in (mine.roster if mine else [])
    ])
    db.put_document(Docs.NBA_LEAGUE, {
        "season": season,
        "name": rules.name,
        "scoringType": rules.scoring_type,
        "scoring": {L.STAT.get(k, str(k)): v for k, v in rules.scoring.items()},
        "slots": rules.slots, "bench": rules.bench, "ir": rules.ir,
        "limits": rules.position_limits,
        "regPeriods": rules.reg_periods, "playoffPeriods": rules.playoff_periods,
        "playoffTeams": rules.playoff_teams,
        "periods": {str(k): list(v) for k, v in cal.periods.items()},
        "dayDates": {str(k): v.isoformat() for k, v in cal.day_dates.items()},
        "proTeams": {
            str(t.id): {"abbrev": t.abbrev, "name": t.name,
                        "games": {str(d): [o, h] for d, (o, h) in sorted(t.games.items())}}
            for t in pro.values()
        },
        "acquisitions": {
            "limit": rules.acquisition_limit, "perDay": rules.acquisition_per_day,
            "waiverHours": rules.waiver_hours, "waiverDays": rules.waiver_days,
            "used": {str(k): v for k, v in (mine.acquisitions if mine else {}).items()},
        },
        "tradeDeadline": rules.trade_deadline,
        "lineupLock": rules.lineup_lock,
        "espnPeriod": rules.current_period,
        "myTeamId": my_team,
        "today": pinned_today,
        "warnings": cal.warnings,
    })
    _log(f"{rules.name or 'league'} · {rules.scoring_type} · {len(teams)} teams · {len(rows)} players · "
         f"matchup {rules.current_period} · "
         + (f"{len(mine.roster)} on your roster" if mine else "no team of yours set"))
