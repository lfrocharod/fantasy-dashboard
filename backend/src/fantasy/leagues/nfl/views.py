"""ESPN NFL in-season pages, assembled from the database.

Ported from the old web app's NFL pages, which loaded the whole board into the
browser and computed everything there (app/nfl/*.tsx).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from fantasy.api.schemas import nfl as S
from fantasy.api.schemas.common import CheckItem
from fantasy.core import models as M
from fantasy.core.store import get_setting
from fantasy.football.jsmath import js_round, js_to_fixed
from fantasy.leagues.nfl import analysis as A
from fantasy.leagues.nfl.players import OUT_STATUS, NflPlayer

POS_SORT = ("QB", "RB", "WR", "TE", "K", "DST")


def out(p: NflPlayer) -> S.NflPlayer:
    lo, hi = A.week_range(p, 0)
    return S.NflPlayer.model_validate(p).model_copy(update={
        "week_points": A.week_points(p, 0), "lo": lo, "hi": hi,
        "usage_tag": A.usage_tag(p), "opp_tag": A.opp_tag(p),
    })


def outs(ps: Sequence[NflPlayer]) -> list[S.NflPlayer]:
    return [out(p) for p in ps]


@dataclass(slots=True)
class League:
    players: list[NflPlayer]
    my_team_id: int | None
    my_roster: list[NflPlayer]
    week: int
    slots: dict[str, int]
    seeding_rule: str
    reg_weeks: int
    playoff_weeks: list[int]
    playoff_teams: int
    matchups: list[M.Matchup]
    entries: list[M.LeagueEntry]

    def teams(self) -> list[A.NflManager]:
        return A.group_teams(self.players, self.my_team_id)

    def my_match(self) -> M.Matchup | None:
        me = str(self.my_team_id)
        return next(
            (m for m in self.matchups if m.round == self.week and me in (m.home_entry, m.away_entry)),
            None,
        )


def load(session: Session) -> League:
    rows = session.scalars(select(M.DraftPlayer).where(M.DraftPlayer.sport == "nfl")).all()
    players = sorted(
        (NflPlayer.from_row(r) for r in rows),
        key=lambda p: (int(p.ext_id), "") if p.ext_id.isdigit() else (1 << 62, p.ext_id),
    )
    lg = session.get(M.League, "nfl")
    mine_ids = {
        s.ext_id for s in session.scalars(select(M.LineupSlot).where(M.LineupSlot.sport == "nfl"))
    }
    my_team = get_setting(session, "draft.nfl.my_team_id")
    reg = (lg.regular_rounds if lg and lg.regular_rounds else None)
    playoff_weeks = list(lg.playoff_rounds) if lg and lg.playoff_rounds else []
    return League(
        players=players,
        my_team_id=int(my_team) if my_team and my_team.isdigit() else None,
        my_roster=[p for p in players if p.ext_id in mine_ids],
        week=(lg.current_round if lg and lg.current_round else 1),
        slots=dict(lg.lineup_slots) if lg and lg.lineup_slots else dict(A.DEFAULT_SLOTS),
        seeding_rule=(lg.seeding_rule if lg and lg.seeding_rule else "H2H_RECORD"),
        reg_weeks=reg if reg else (playoff_weeks[0] - 1 if playoff_weeks else 15),
        playoff_weeks=playoff_weeks,
        playoff_teams=(lg.playoff_teams if lg and lg.playoff_teams else 4),
        matchups=list(session.scalars(select(M.Matchup).where(M.Matchup.sport == "nfl"))),
        entries=list(session.scalars(select(M.LeagueEntry).where(M.LeagueEntry.sport == "nfl"))),
    )


def _opponent(lg: League) -> tuple[A.NflManager | None, M.Matchup | None]:
    match = lg.my_match()
    if match is None:
        return None, None
    opp_id = match.away_entry if match.home_entry == str(lg.my_team_id) else match.home_entry
    team = next((t for t in lg.teams() if str(t.team_id) == opp_id), None)
    return team, match


def _seed_by_points(lg: League) -> bool:
    return lg.seeding_rule == "TOTAL_POINTS_SCORED"


# ---- overview ------------------------------------------------------------------------------


def overview(session: Session) -> S.NflOverview:
    lg = load(session)
    roster = lg.my_roster
    opp, match = _opponent(lg)
    mine = A.optimal_lineup(roster, lg.slots, 0)
    theirs = A.optimal_lineup(opp.players, lg.slots, 0) if opp else None
    win_pct = A.win_prob_from_margin(mine.total - theirs.total) if theirs else 50
    seed_by_points = _seed_by_points(lg)
    mode = A.lineup_mode(win_pct, seed_by_points)
    opt_ids = {s.player.ext_id for s in mine.starters if s.player}

    live = None
    if match is not None:
        i_am_home = match.home_entry == str(lg.my_team_id)
        mine_pts = (match.home_points if i_am_home else match.away_points) or 0.0
        opp_pts = (match.away_points if i_am_home else match.home_points) or 0.0
        if mine_pts > 0 or opp_pts > 0:
            live = S.LiveScore(mine=mine_pts, opp=opp_pts,
                               final=match.winner in ("HOME", "AWAY", "TIE"))

    changes = sum(
        1 for s in mine.starters if s.player and s.player.slot in ("BE", "IR", "")
    ) + sum(1 for p in roster if p.ext_id not in opt_ids and p.slot not in ("", "BE", "IR"))
    injured = [p for p in roster if p.injury != "ACTIVE" and p.ext_id in opt_ids]
    byes = [p for p in roster if p.on_bye and p.ext_id in opt_ids]
    if seed_by_points:
        mode_text = "League seeds on total points — start your highest-ceiling lineup every week"
    elif mode == "ceiling":
        mode_text = f"Underdog this week ({win_pct}%) — start the higher-ceiling options, chase the upset"
    elif mode == "floor":
        mode_text = f"Favoured this week ({win_pct}%) — start the safe floor, don't hand back the edge"
    else:
        mode_text = f"Close matchup ({win_pct}%) — start your best straight projection"
    checklist = [
        CheckItem(ok=changes == 0,
                  text="ESPN lineup matches the optimal one" if changes == 0
                  else f"{changes} lineup change(s) recommended",
                  href="/nfl/optimizer", link_text="open Optimizer →"),
        CheckItem(ok=True, text=mode_text, href="/nfl/optimizer", link_text="open Optimizer →"),
        CheckItem(ok=not injured,
                  text=f"{len(injured)} starter(s) carrying an injury tag: "
                  + ", ".join(p.name for p in injured)
                  if injured else "No injury tags on your projected starters"),
        CheckItem(ok=not byes,
                  text=f"{len(byes)} projected starter(s) on BYE — fill the slot"
                  if byes else "No starters on bye this week"),
    ]
    ordered = sorted(
        roster,
        key=lambda p: (POS_SORT.index(p.pos) if p.pos in POS_SORT else 9, -A.week_points(p, 0)),
    )
    return S.NflOverview(
        week=lg.week, has_roster=bool(roster), my_proj=mine.total,
        opp_name=opp.name if opp else None, opp_proj=theirs.total if theirs else None,
        win_pct=win_pct if theirs else None, mode=mode, live=live, checklist=checklist,
        roster=[S.RosterRow(player=out(p), starting=p.ext_id in opt_ids) for p in ordered],
    )


# ---- optimizer -------------------------------------------------------------------------------


def optimizer_page(session: Session) -> S.NflOptimizer:
    lg = load(session)
    roster = lg.my_roster
    opp, _ = _opponent(lg)
    mean_mine = A.optimal_lineup(roster, lg.slots, 0).total
    mean_opp = A.optimal_lineup(opp.players, lg.slots, 0).total if opp else None
    win_pct = A.win_prob_from_margin(mean_mine - mean_opp) if mean_opp is not None else 50
    seed_by_points = _seed_by_points(lg)
    mode = A.lineup_mode(win_pct, seed_by_points)
    lineup = A.optimal_lineup(roster, lg.slots, 0, A.mode_score(mode))
    starters = [s.player for s in lineup.starters if s.player]
    starter_ids = {p.ext_id for p in starters}
    return S.NflOptimizer(
        week=lg.week, has_roster=bool(roster), mode=mode, win_pct=win_pct,
        seed_by_points=seed_by_points,
        mean_total=sum(A.week_points(p, 0) for p in starters),
        lo_total=sum(A.week_range(p, 0)[0] for p in starters),
        hi_total=sum(A.week_range(p, 0)[1] for p in starters),
        lineup=[S.SlotRow(slot=s.slot, player=out(s.player) if s.player else None)
                for s in lineup.starters],
        to_start=outs([p for p in starters if p.slot in ("BE", "IR", "")]),
        to_bench=outs([p for p in roster if p.ext_id not in starter_ids
                       and p.slot not in ("", "BE", "IR")]),
        start_sit=[
            S.StartSitRow(player=out(p), call=A.start_sit_call(p, starter_ids))
            for p in sorted(roster, key=lambda p: -A.week_points(p, 0))
        ],
    )


# ---- players & free agents -------------------------------------------------------------------


def players_page(session: Session, horizon: str, position: str) -> S.NflPlayersResponse:
    lg = load(session)
    mine_ids = {p.ext_id for p in lg.my_roster}
    lineup = A.optimal_lineup(lg.my_roster, lg.slots, 0)

    def value(p: NflPlayer) -> float:
        return A.week_points(p, 0) if horizon == "week" else A.adj_ros(p)

    # your worst starter per position — the bar a pickup must clear
    worst: dict[str, float] = {}
    for s in lineup.starters:
        if s.player is None:
            continue
        key = "FLEX" if s.slot == "FLEX" else s.player.pos
        v = value(s.player)
        worst[key] = min(worst.get(key, float("inf")), v)
        worst[s.player.pos] = min(worst.get(s.player.pos, float("inf")), v)
    free = [p for p in lg.players if p.available and p.ext_id not in mine_ids and (p.team or p.pos == "DST")]

    def best_at(pos: str, week: bool) -> NflPlayer | None:
        cands = [p for p in free if p.pos == pos and p.injury not in OUT_STATUS]
        cands.sort(key=lambda p: -(A.week_points(p, 0) if week else A.adj_ros(p)))
        return cands[0] if cands else None

    holes = []
    for s in lineup.starters:
        if s.player is None:
            continue
        reason = "BYE" if s.player.on_bye else s.player.injury if s.player.injury in OUT_STATUS else ""
        if not reason:
            continue
        fill = best_at("RB" if s.slot == "FLEX" else s.player.pos, True)
        holes.append(S.Hole(gap=out(s.player), reason=reason, fill=out(fill) if fill else None))

    def weeks_left(i: int) -> int:
        return max(3, 15 - (lg.week + i))

    stream = []
    for pos in ("DST", "K", "QB", "TE"):
        options = []
        for p in (p for p in free if p.pos == pos and p.injury not in OUT_STATUS):
            wk = [
                S.StreamWeek(
                    opp=p.matchups[i].opp if i < len(p.matchups) else "",
                    fdr=p.matchups[i].fdr if i < len(p.matchups) else 0,
                    proj=A.week_points(p, i, weeks_left(i)),
                )
                for i in range(3)
            ]
            best = max(range(3), key=lambda i: (wk[i].proj, -i))
            options.append(S.StreamOption(player=out(p), weeks=wk, best=best,
                                          total3=sum(w.proj for w in wk)))
        options.sort(key=lambda o: -o.total3)
        if options:
            stream.append(S.StreamGroup(position=pos, options=options[:3]))

    pool = [p for p in free if p.injury not in OUT_STATUS and (position == "ALL" or p.pos == position)]
    rows = []
    for p in pool:
        v = value(p)
        bar = worst.get(p.pos, worst.get("FLEX", 0.0))
        rows.append((p, v, v - bar))
    if horizon == "week":
        rows.sort(key=lambda t: (-t[1], -t[2]))
    else:
        rows.sort(key=lambda t: (-(t[0].vor * A.opp_factor(t[0])), -t[2]))
    return S.NflPlayersResponse(
        week=lg.week, horizon=horizon, position=position,  # type: ignore[arg-type]
        holes=holes, stream=stream,
        free_agents=[S.FreeAgentRow(player=out(p), value=v, upgrade=u) for p, v, u in rows[:40]],
    )


# ---- clubs -------------------------------------------------------------------------------------


def fixtures_page(session: Session) -> S.NflFixturesResponse:
    lg = load(session)
    clubs = A.nfl_club_fixtures(lg.players)
    return S.NflFixturesResponse(
        weeks=[c.week for c in clubs[0].cells] if clubs else [],
        clubs=[S.NflClubFix.model_validate(c) for c in clubs],
    )


def teams_page(session: Session) -> S.NflTeamsResponse:
    lg = load(session)
    return S.NflTeamsResponse(clubs=[
        S.NflClubDossier(team=d.team, fixtures=[S.WeekOpp.model_validate(c) for c in d.fixtures],
                         avg_fdr=d.avg_fdr, starters=outs(d.starters), bench=outs(d.bench),
                         doubts=outs(d.doubts), bye=d.bye)
        for d in A.nfl_club_dossiers(lg.players)
    ])


# ---- rivals ------------------------------------------------------------------------------------


def _manager_out(m: A.NflManager) -> S.NflManager:
    return S.NflManager(team_id=m.team_id, name=m.name, is_mine=m.is_mine, players=outs(m.players),
                        by_pos={k: outs(v) for k, v in m.by_pos.items()}, ros_total=m.ros_total)


def rivals_page(session: Session) -> S.NflRivalsResponse:
    lg = load(session)
    teams = lg.teams()
    opp, _ = _opponent(lg)
    my_proj = A.optimal_lineup(lg.my_roster, lg.slots, 0).total
    opponent = None
    if opp:
        theirs = A.optimal_lineup(opp.players, lg.slots, 0)
        margin = my_proj - theirs.total
        if _seed_by_points(lg):
            advice = ("This league seeds by total points, so play your highest-ceiling lineup "
                      "regardless of this matchup — the W/L doesn't affect seeding.")
        elif margin >= 4:
            advice = "You're a clear favourite — play your safe floor."
        elif margin <= -4:
            advice = "You're the underdog — play ceiling / make a differential move."
        else:
            advice = "Coin-flip — every start/sit call matters."
        opponent = S.OpponentView(
            name=opp.name, my_proj=my_proj, their_proj=theirs.total, advice=advice,
            lineup=[S.SlotRow(slot=s.slot, player=out(s.player) if s.player else None)
                    for s in theirs.starters],
        )
    return S.NflRivalsResponse(week=lg.week, opponent=opponent, teams=[_manager_out(t) for t in teams])


# ---- standings ----------------------------------------------------------------------------------


def standings_page(session: Session, seeding: str | None) -> S.NflStandingsResponse:
    lg = load(session)
    espn_rule = lg.seeding_rule if lg.seeding_rule in ("H2H_RECORD", "TOTAL_POINTS_SCORED") else "H2H_RECORD"
    rule = seeding if seeding in ("H2H_RECORD", "TOTAL_POINTS_SCORED") else espn_rule
    by_points = rule == "TOTAL_POINTS_SCORED"
    standings = [
        A.Standing(team_id=int(e.entry_id), name=e.name, wins=e.wins or 0, losses=e.losses or 0,
                   ties=e.draws or 0, pf=e.points_for or 0.0)
        for e in lg.entries if e.entry_id.isdigit()
    ]
    teams = lg.teams()
    schedule = [
        A.Game(week=m.round, home=int(m.home_entry), away=int(m.away_entry))
        for m in lg.matchups if m.home_entry.isdigit() and m.away_entry.isdigit()
    ]
    odds = (
        A.sim_playoffs(teams, standings, schedule, lg.slots, lg.week, lg.reg_weeks,
                       lg.playoff_teams, lg.my_team_id, rule)
        if teams and schedule else []
    )
    by_team = {o.team_id: o for o in odds}
    table = sorted(
        standings,
        key=lambda s: (-s.pf, -s.wins) if by_points else (-s.wins, s.losses, -s.pf),
    )
    rows = [
        S.NflStandingRow(
            team_id=s.team_id, name=s.name, wins=s.wins, losses=s.losses, ties=s.ties, pf=s.pf,
            mine=s.team_id == lg.my_team_id, in_line=i < lg.playoff_teams,
            proj_wins=by_team[s.team_id].proj_wins if s.team_id in by_team else None,
            proj_pf=by_team[s.team_id].proj_pf if s.team_id in by_team else None,
            playoff_pct=by_team[s.team_id].playoff_pct if s.team_id in by_team else None,
            bye_pct=by_team[s.team_id].bye_pct if s.team_id in by_team else None,
        )
        for i, s in enumerate(table)
    ]

    pace = None
    me_s = next((s for s in standings if s.team_id == lg.my_team_id), None)
    if by_points and me_s:
        played = max(1, lg.week - 1)
        weeks_left = max(1, lg.reg_weeks - lg.week + 1)
        my_pace = me_s.pf / played
        cut_idx = lg.playoff_teams - 1
        cur_cut = table[cut_idx].pf if cut_idx < len(table) else 0.0
        cur_rank = next((i + 1 for i, s in enumerate(table) if s.team_id == lg.my_team_id), 0)
        by_pf = sorted(odds, key=lambda o: -o.proj_pf)
        proj_cut = by_pf[cut_idx].proj_pf if cut_idx < len(by_pf) else 0.0
        me_o = by_team.get(me_s.team_id)
        my_proj_pf = me_o.proj_pf if me_o else me_s.pf + my_pace * weeks_left
        margin = my_proj_pf - proj_cut
        pace = S.Pace(
            cur_rank=cur_rank, cur_gap=me_s.pf - cur_cut, played=played, weeks_left=weeks_left,
            my_pace=my_pace, proj_margin=margin,
            per_week_gap=0.0 if margin >= 0 else -margin / weeks_left,
            playoff_pct=me_o.playoff_pct if me_o else None,
        )

    playoff_weeks = lg.playoff_weeks or [16, 17]
    roster = sorted(lg.my_roster, key=lambda p: -p.ros_proj)
    byes = []
    for w in range(lg.week, min(lg.week + 8, lg.reg_weeks) + 1):
        off = [p for p in roster if p.bye == w and p.pos in POS_SORT]
        if off:
            byes.append(S.ByeGap(week=w, players=outs(off)))
    runs = []
    for p in roster:
        pw = [m for m in p.matchups if m.week in playoff_weeks and m.fdr]
        src = pw or [m for m in p.matchups if m.fdr]
        avg = sum(m.fdr for m in src) / len(src) if src else 3.0
        runs.append(S.PlayoffRun(player=out(p), avg=avg,
                                 weeks=[S.WeekOpp.model_validate(m) for m in p.matchups
                                        if m.week in playoff_weeks]))
    runs.sort(key=lambda r: r.avg)
    return S.NflStandingsResponse(
        rule=rule, espn_rule=espn_rule, by_points=by_points,  # type: ignore[arg-type]
        playoff_teams=lg.playoff_teams, reg_weeks=lg.reg_weeks, playoff_weeks=playoff_weeks,
        rows=rows, pace=pace, byes=byes, playoff_runs=runs,
    )


# ---- trades --------------------------------------------------------------------------------------


def trade_lab(session: Session, rival_id: int | None) -> S.NflTradeLab:
    lg = load(session)
    teams = lg.teams()
    me = next((t for t in teams if t.is_mine), None)
    rivals = [t for t in teams if not t.is_mine]
    rival = next((t for t in rivals if t.team_id == rival_id), rivals[0] if rivals else None)
    surplus: list[S.SurplusRow] = []
    if rival:
        starters = {s.player.ext_id for s in A.optimal_lineup(rival.players, lg.slots, 0).starters
                    if s.player}
        my_by_pos = me.by_pos if me else {}

        def thin(k: str) -> bool:
            slot_n = max(0, lg.slots.get(k, 1))
            ranked = my_by_pos.get(k, [])
            return (ranked[slot_n].ros_proj if slot_n < len(ranked) else 0.0) < 100

        need = {k for k in ("RB", "WR", "TE", "QB") if thin(k)}
        cands = sorted(
            (p for p in rival.players if p.ext_id not in starters and p.injury not in OUT_STATUS
             and p.pos not in ("K", "DST")),
            key=lambda p: (-p.vor, -A.adj_ros(p)),
        )[:8]
        surplus = [S.SurplusRow(player=out(p), fills_need=p.pos in need, tag=A.opp_tag(p))
                   for p in cands]
    ideas = A.nfl_trade_ideas(me, rivals, lg.slots) if me else []
    return S.NflTradeLab(
        me=_manager_out(me) if me else None,
        rivals=[_manager_out(t) for t in rivals],
        rival=_manager_out(rival) if rival else None,
        ideas=[S.NflTradeIdea(rival_name=t.rival_name, rival_team_id=t.rival_team_id,
                           give=out(t.give), get=out(t.get), my_gain=t.my_gain,
                           their_gain=t.their_gain) for t in ideas],
        their_surplus=surplus,
    )


def evaluate_trade(session: Session, give_ids: Sequence[str], get_ids: Sequence[str]) -> S.NflTradeEvaluation:
    """Your side on opportunity-adjusted ROS; the rival's on the raw provider
    projection — how a typical manager would value it."""
    lg = load(session)
    by_id = {p.ext_id: p for p in lg.players}
    give = [by_id[x] for x in give_ids if x in by_id]
    get = [by_id[x] for x in get_ids if x in by_id]
    me = next((t for t in lg.teams() if t.is_mine), None)
    me_week = sum(p.week_proj for p in get) - sum(p.week_proj for p in give)
    me_ros = sum(A.adj_ros(p) for p in get) - sum(A.adj_ros(p) for p in give)
    them_ros = sum(p.ros_proj for p in give) - sum(p.ros_proj for p in get)
    warns: list[str] = []
    for p in get:
        if p.injury in OUT_STATUS:
            warns.append(f"{p.name} is {p.injury}")
        if p.pct_started < 40 and p.pos not in ("DST", "K"):
            warns.append(f"{p.name} is a bench/flex piece ({js_to_fixed(p.pct_started, 0)}% started)")
        if A.opp_tag(p) == "sell-high":
            warns.append(f"{p.name} is scoring +{js_to_fixed(p.fp_oe, 1)}/g over expected — likely to regress "
                         "down, you may be buying the peak")
    for p in give:
        if A.opp_tag(p) == "buy-low":
            warns.append(f"you're giving up {p.name}, who is {js_to_fixed(p.fp_oe, 1)}/g UNDER expected — a "
                         "bounce-back candidate")
    by_pos = me.by_pos if me else {}
    need = [k for k in ("RB", "WR", "TE")
            if (by_pos.get(k, [])[2].ros_proj if len(by_pos.get(k, [])) > 2 else 0.0) < 90]
    helps = any(p.pos in need for p in get)
    if me_ros > 12 and them_ros < -20:
        warns.append("Lopsided in your favour on raw projection — the rival probably won't accept as-is.")
    if me_ros > 15 and me_week > 1:
        verdict = ("Clear win — better now and for the season, and a fair ask."
                   if them_ros > -15 else
                   "Better for you, but skewed on raw value — sweeten it or expect a no.")
    elif me_ros > 15:
        verdict = "Long-term win; roughly flat this week."
    elif me_ros < -15:
        verdict = "You lose season value — pass unless you're desperate for a Week win."
    elif helps and abs(me_ros) < 15:
        verdict = "Even on value but fills a roster hole — worth proposing."
    else:
        verdict = "Marginal — roughly even."
    return S.NflTradeEvaluation(
        me_week=js_round(me_week * 10) / 10, me_ros=js_round(me_ros), them_ros=js_round(them_ros),
        warnings=warns, verdict=verdict, need_pos=need,
    )

