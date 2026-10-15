"""The cross-league command centre: one card per league plus the alerts worth
acting on now, most urgent first. Ported from the old web app's lib/home.ts,
plus a data-freshness check per league."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fantasy.api.schemas import home as S
from fantasy.config import Keys
from fantasy.core import models as M
from fantasy.core.store import get_settings
from fantasy.football.jsmath import js_round
from fantasy.leagues.fpl import analysis as FA
from fantasy.leagues.fpl import views as fpl_views
from fantasy.leagues.nba import analysis as BA
from fantasy.leagues.nba import views as nba_views
from fantasy.leagues.nba.players import OUT_STATUS as NBA_OUT
from fantasy.leagues.nfl import analysis as NA
from fantasy.leagues.nfl import views as nfl_views
from fantasy.leagues.nfl.players import OUT_STATUS
from fantasy.leagues.ucl import views as ucl_views

# The home runner refreshes every 30 minutes through the day; a gap this long
# means it has stopped (machine off, a crash, an expired cookie).
STALE_AFTER = timedelta(hours=12)
TONE_ORDER = {"bad": 0, "warn": 1, "accent": 2}


def _hours_until(iso: str | None) -> float | None:
    if not iso:
        return None
    return (datetime.fromisoformat(iso) - datetime.now(UTC)).total_seconds() / 3600


def _ucl(session: Session, alerts: list[S.Alert]) -> S.UclHome:
    d = ucl_views.dashboard_summary(session)
    opt = ucl_views.optimizer_output(session)
    captain = opt.captains.safe_pick.name if opt and opt.captains and opt.captains.safe_pick else None
    live = d["live"]
    live_out = None
    if live:
        cap = live.captain
        note = cap.note if cap and (cap.recommendation == "switch" or cap.effective_name is None) else None
        live_out = S.UclLive(
            matchday=live.matchday, state=live.state, secured=live.secured_points,
            projected_finish=live.projected_finish,
            played=live.played, starters=live.starters, manual_subs=len(live.manual_subs),
            captain_note=note,
        )
        if live.manual_subs:
            n = len(live.manual_subs)
            alerts.append(S.Alert(
                league="UCL", tone="warn", href="/ucl",
                text=f"Live: {n} substitution{'s' if n > 1 else ''} still worth making before "
                "those players' games kick off.",
            ))
        if note:
            alerts.append(S.Alert(league="UCL", tone="accent", text=f"Live: {note}.", href="/ucl"))
    out = S.UclHome(
        active=d["squad_size"] > 0, matchday=d["matchday"], deadline_iso=d["deadline_iso"],
        projected=js_round(d["projected"]), captain=captain, rank=d["rank"],
        league_size=d["league_size"], ingest_ok=d["ingest_ok"], ingest_at=d["ingest_at"],
        live=live_out,
    )
    h = _hours_until(out.deadline_iso)
    if out.active and h is not None and 0 < h < 48:
        when = "<1h" if h < 1 else f"{js_round(h)}h"
        alerts.append(S.Alert(
            league="UCL", tone="bad" if h < 12 else "warn", href="/ucl/optimizer",
            text=f"Champions League deadline in {when} — set your XI & captain"
            + (f" ({captain})" if captain else "") + ".",
        ))
    # the late-day bench tip is for the matchday whose deadline is next, not
    # the one after while a matchday is under way
    if opt and opt.matchday == out.matchday and opt.matchday_timing and opt.matchday_timing.live_options:
        opts = ", ".join(opt.matchday_timing.live_options[:3])
        alerts.append(S.Alert(
            league="UCL", tone="accent", href="/ucl/optimizer",
            text=f"Bench your late-day options ({opts}) — you can sub them in after the early games.",
        ))
    auth = get_settings(session, [Keys.UEFA_TOKEN, Keys.UEFA_AUTH_STATE])
    if auth.get(Keys.UEFA_TOKEN) and auth.get(Keys.UEFA_AUTH_STATE) == "public_only":
        alerts.append(S.Alert(
            league="UCL", tone="bad", href="/settings",
            text="Your UEFA login has expired — paste a fresh cookie in Settings. Your squad, "
            "rivals and the mini-league table stop updating until then.",
        ))
    return out


def _fpl(session: Session, alerts: list[S.Alert]) -> S.FplHome:
    b = fpl_views.load_board(session)
    squad = b.my_squad
    xi = FA.best_xi(squad) if len(squad) >= 11 else None
    injured = sum(1 for p in squad if p.unavailable)
    mine = {p.ext_id for p in squad}
    free = sorted(
        (p for p in b.players if p.available and p.ext_id not in mine and not p.unavailable),
        key=lambda p: -FA.value_for(p, "medium"),
    )
    worst = min((FA.value_for(p, "medium") for p in xi.xi), default=0.0) if xi else 0.0
    top = free[0] if free else None
    claim = None
    if top and FA.value_for(top, "medium") - worst > 4:
        claim = S.Claim(name=top.name, gain=js_round(FA.value_for(top, "medium") - worst))
    live_doc = session.scalar(select(M.Document.payload).where(M.Document.key == "fpl.live"))
    lv = (fpl_views.live_view(live_doc, b, fpl_views.gw_projections(session, int(live_doc.get("gw") or 0)))
          if live_doc else None)
    me = next((e for e in b.entries if e.is_mine), None)
    out = S.FplHome(
        active=bool(squad),
        gw=b.gws[0] if b.gws else None,
        xi_proj=js_round(sum(p.proj for p in xi.xi)) if xi else 0,
        rank=me.rank if me else None,
        top_claim=claim,
        injured=injured,
        live=S.FplLiveHome(gw=lv.gw, state=lv.state, secured=lv.secured, played=lv.played,
                           starters=lv.starters)
        if lv else None,
    )
    if out.active and injured:
        alerts.append(S.Alert(
            league="FPL", tone="warn", href="/fpl",
            text=f"{injured} player{'s' if injured > 1 else ''} in your FPL squad flagged "
            "injured/doubtful — check your lineup.",
        ))
    if claim:
        alerts.append(S.Alert(
            league="FPL", tone="accent", href="/fpl",
            text=f"Waiver upgrade available: {claim.name} projects +{claim.gain} over your weakest starter.",
        ))
    return out


def _nfl(session: Session, alerts: list[S.Alert]) -> S.NflHome:
    lg = nfl_views.load(session)
    roster = lg.my_roster
    lineup = NA.optimal_lineup(roster, lg.slots, 0) if roster else None
    issues = 0
    if lineup:
        start_ids = {s.player.ext_id for s in lineup.starters if s.player}
        issues += sum(
            1 for s in lineup.starters if s.player and (s.player.injury in OUT_STATUS or s.player.on_bye)
        )
        bench_best = max([0.0, *(NA.week_points(p, 0) for p in roster if p.ext_id not in start_ids)])
        start_worst = min(
            (NA.week_points(s.player, 0) for s in lineup.starters
             if s.player and s.slot not in ("K", "DST")),
            default=math.inf,
        )
        if bench_best > start_worst + 2:
            issues += 1
    opp, match = nfl_views._opponent(lg)
    live = None
    if match is not None:
        home = match.home_entry == str(lg.my_team_id)
        mine_pts = (match.home_points if home else match.away_points) or 0.0
        opp_pts = (match.away_points if home else match.home_points) or 0.0
        if mine_pts > 0 or opp_pts > 0:
            live = S.NflLiveHome(mine=js_round(mine_pts * 10) / 10, opp=js_round(opp_pts * 10) / 10,
                                 final=match.winner in ("HOME", "AWAY", "TIE"))
    opp_lineup = NA.optimal_lineup(opp.players, lg.slots, 0) if opp and opp.players else None
    my_proj = js_round(lineup.total) if lineup else 0
    opp_proj = js_round(opp_lineup.total) if opp_lineup else None
    win_pct = js_round(100 / (1 + math.exp(-(my_proj - opp_proj) / 19))) if opp_proj is not None else None
    mine = {p.ext_id for p in roster}
    free = sorted(
        (p for p in lg.players if p.available and p.ext_id not in mine and p.injury not in OUT_STATUS),
        key=lambda p: -(p.vor * NA.opp_factor(p)),
    )
    worst = min((NA.adj_ros(s.player) for s in lineup.starters if s.player), default=0.0) if lineup else 0.0
    claim = None
    if free and NA.adj_ros(free[0]) - worst > 12:
        claim = S.Claim(name=free[0].name, gain=js_round(NA.adj_ros(free[0]) - worst))
    out = S.NflHome(
        active=bool(roster), week=lg.week if roster or lg.matchups else None, my_proj=my_proj,
        opp_name=opp.name if opp else None, opp_proj=opp_proj, win_pct=win_pct,
        lineup_issues=issues, top_claim=claim, live=live,
    )
    if out.active and issues:
        alerts.append(S.Alert(
            league="NFL", tone="bad", href="/nfl",
            text=f"Your NFL lineup has {issues} issue{'s' if issues > 1 else ''} (a starter is "
            "OUT/on bye, or a bench player out-projects a starter).",
        ))
    if out.active and win_pct is not None and win_pct < 45:
        alerts.append(S.Alert(
            league="NFL", tone="warn", href="/nfl",
            text=f"You're the underdog vs {out.opp_name} this week ({win_pct}% win) — consider a "
            "ceiling play or a waiver move.",
        ))
    return out


def _nba(session: Session, alerts: list[S.Alert]) -> S.NbaHome:
    lg = nba_views.load(session)
    roster = lg.my_roster
    if not roster:
        return S.NbaHome(active=False, period=lg.period if lg.periods else None, days_left=0,
                         my_proj=0, opp_name=None, opp_proj=None, win_pct=None, live=None,
                         tonight=0, top_stream=None)
    left = lg.days_left
    plan = BA.plan_days(roster, left, lg.games, lg.slots)
    score = nba_views._score(lg, lg.period, left)
    start, _ = nba_views._today_moves(lg, roster)
    streams = BA.streams(roster, nba_views._free(lg), left, lg.games, lg.slots,
                         nba_views._ros(lg), lg.limits)
    top = next((s for s in streams if s.ros_delta >= -50 and s.gain >= 10), None)
    if nba_views._moves(lg).left == 0:
        top = None  # no pickups left this matchup
    live = None
    if score and (score.my_points or score.opp_points):
        live = S.NflLiveHome(mine=score.my_points, opp=score.opp_points, final=False)
    out = S.NbaHome(
        active=True, period=lg.period, days_left=len(left),
        my_proj=js_round(score.my_proj if score else plan.total),
        opp_name=score.opp_name if score else None,
        opp_proj=js_round(score.opp_proj) if score else None,
        win_pct=score.win_pct if score else None, live=live, tonight=len(start),
        top_stream=S.Claim(name=top.add.name, gain=js_round(top.gain)) if top else None,
    )
    when = nba_views._when(lg, lg.pinned)
    if start:
        alerts.append(S.Alert(
            league="NBA", tone="bad", href="/nba/lineup",
            text=f"{when}: start {', '.join(p.name for p in start)} — benched with a game.",
        ))
    healthy_ir = [p for p in roster if p.slot == "IR" and p.injury not in NBA_OUT]
    if healthy_ir:
        alerts.append(S.Alert(
            league="NBA", tone="bad", href="/nba/lineup",
            text=f"{healthy_ir[0].name} is healthy but on IR — activate him before ESPN blocks "
            "your other moves.",
        ))
    if out.win_pct is not None and out.win_pct < 40:
        alerts.append(S.Alert(
            league="NBA", tone="warn", href="/nba/players",
            text=f"You're the underdog vs {out.opp_name} this matchup ({out.win_pct}% win) — "
            "stream for games.",
        ))
    return out


def _freshness(session: Session, alerts: list[S.Alert], active: dict[str, bool]) -> list[S.Freshness]:
    now = datetime.now(UTC)
    ucl_at = session.scalar(select(func.max(M.Player.updated_at)))
    board = {
        sport: at
        for sport, at in session.execute(
            select(M.DraftPlayer.sport, func.max(M.DraftPlayer.updated_at)).group_by(M.DraftPlayer.sport)
        ).tuples()
    }
    out = []
    for tag, at in (("UCL", ucl_at), ("FPL", board.get("fpl")), ("NFL", board.get("nfl")),
                    ("NBA", board.get("nba"))):
        stale = bool(active[tag] and at and now - at > STALE_AFTER)
        out.append(S.Freshness(league=tag, updated_at=at.isoformat() if at else None, stale=stale))  # type: ignore[arg-type]
        if stale and at:
            hours = js_round((now - at).total_seconds() / 3600)
            alerts.append(S.Alert(
                league=tag, tone="warn", href="/settings",  # type: ignore[arg-type]
                text=f"{tag} data is {hours}h old — the home runner may be off or a login expired.",
            ))
    return out


def summary(session: Session) -> S.HomeSummary:
    alerts: list[S.Alert] = []
    ucl = _ucl(session, alerts)
    fpl = _fpl(session, alerts)
    nfl = _nfl(session, alerts)
    nba = _nba(session, alerts)
    fresh = _freshness(session, alerts, {"UCL": ucl.active, "FPL": fpl.active, "NFL": nfl.active,
                                         "NBA": nba.active})
    # most urgent first; stable within a tone so the order above still reads
    alerts.sort(key=lambda a: TONE_ORDER[a.tone])
    return S.HomeSummary(ucl=ucl, fpl=fpl, nfl=nfl, nba=nba, alerts=alerts, freshness=fresh)
