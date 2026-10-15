"""Champions League pages, assembled from the database.

Ported from the old web app (lib/ucl/queries.ts and the logic that lived
inline in the page components): the player/squad/fixture queries, team
dossiers, rival projections, the league-phase strategy, the captaincy verdict,
the pre-deadline checklist and the finish-position simulation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import numpy as np
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session, aliased

from fantasy.api.schemas import ucl as S
from fantasy.api.schemas.common import CheckItem
from fantasy.config import Docs, Keys
from fantasy.core import models as M
from fantasy.core.store import get_document, get_settings
from fantasy.football.fdr import blended_rate, pos_fdr
from fantasy.football.formation import pick_formation_xi
from fantasy.football.jsmath import js_round, round1
from fantasy.leagues.ucl.model.projections import MIN_XG_MINUTES

XG_MIN_MINUTES = MIN_XG_MINUTES  # the bar the projection model trusts a matched xG sample at
XG_MIN_MATCHES = 3
LAST_LEAGUE_MD = 8
POSITIONS = ("GK", "DEF", "MID", "FWD")
RIVAL_STALE_SECONDS = 2 * 24 * 60 * 60


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---- matchday -----------------------------------------------------------------------


def current_matchday(session: Session) -> int:
    league = session.get(M.League, "ucl")
    if league and league.current_round:
        return league.current_round
    md = session.scalar(select(func.max(M.Fixture.matchday)))
    return int(md or 1)


def played_matchday(session: Session) -> int:
    """The latest matchday with a game kicked off (0 before MD1). From one
    matchday's final whistle to the next one's first kickoff, the current
    matchday — the one open for transfers — is one ahead of it."""
    md = session.scalar(
        select(func.max(M.Fixture.matchday)).where(M.Fixture.status.in_(("live", "finished")))
    )
    return int(md or 0)


# ---- players -------------------------------------------------------------------------


def _confirmed(components: dict[str, Any] | None) -> Literal["start", "bench"] | None:
    v = (components or {}).get("confirmed")
    return "start" if v == 1 else "bench" if v == -1 else None


def _player_row(cls: type[S.PlayerRow], r: Any, **extra: Any) -> Any:
    p, team_name = r.Player, r.team_name
    pr: M.Projection | None = r.Projection
    fm: M.PlayerForm | None = r.PlayerForm
    st: M.PlayerStat | None = r.PlayerStat
    usable = bool(st and st.matches >= XG_MIN_MATCHES and st.minutes >= XG_MIN_MINUTES)
    comps = pr.components if pr and isinstance(pr.components, dict) else None
    conf = _confirmed(comps)
    if conf == "start":
        start_pct: float | None = 1.0
    elif conf == "bench":
        start_pct = 0.0
    else:
        start_pct = pr.p_start if pr else (fm.start_prob if fm else None)
    role = fm.role if fm else None
    return cls(
        player_id=p.uefa_player_id,
        name=p.name,
        position=p.position,
        team_id=p.team_id,
        team_name=team_name,
        price=p.price,
        selected_pct=p.selected_pct,
        status_code=p.status_code,
        status_detail=p.status_detail,
        uefa_form=p.uefa_form,
        price_momentum=p.price_momentum,
        set_piece=p.set_piece,
        xpts=pr.xpts if pr else None,
        xpts_captain=pr.xpts_captain if pr else None,
        xpts_high=pr.xpts_high if pr else None,
        xpts_low=pr.xpts_low if pr else None,
        value=pr.value if pr else None,
        p_start=pr.p_start if pr else None,
        exp_minutes=pr.exp_minutes if pr else None,
        components=comps,
        role=role,
        role_note=fm.role_note if fm else None,
        team_ok=fm.team_ok if fm else None,
        start_prob=fm.start_prob if fm else None,
        hot_score=fm.hot_score if fm else None,
        avg_rating=fm.avg_rating if fm else None,
        matches14d=fm.matches_14d if fm else None,
        comps=fm.comps if fm else None,
        recent_goals=fm.recent_goals if fm else None,
        recent_assists=fm.recent_assists if fm else None,
        recent_starts=fm.recent_starts if fm else None,
        recent_matches=fm.recent_matches if fm else None,
        recent_minutes=fm.recent_minutes if fm else None,
        npxg90=st.npxg90 if usable and st else None,
        xa90=st.xag90 if usable and st else None,
        xgi90=(st.npxg90 + st.xag90) if usable and st else None,
        shots90=st.shots90 if usable and st else None,
        xg_matches=st.matches if st else None,
        xg_minutes=st.minutes if st else None,
        confirmed=conf,
        start_pct=start_pct,
        start_disagreement=0.0 if conf else float((comps or {}).get("start_disagreement") or 0.0),
        leverage_role=role if role and role != p.position and role in ("FWD", "MID") else None,
        recent_goal_involvements=(
            (fm.recent_goals or 0) + (fm.recent_assists or 0)
            if fm and fm.recent_matches
            else None
        ),
        **extra,
    )


def _player_select(
    matchday: int,
) -> Select[M.Player, str, M.Projection, M.PlayerForm, M.PlayerStat]:
    return (
        select(M.Player, M.Team.name.label("team_name"), M.Projection, M.PlayerForm, M.PlayerStat)
        .join(M.Team, M.Team.uefa_team_id == M.Player.team_id)
        .outerjoin(
            M.Projection,
            and_(
                M.Projection.player_id == M.Player.uefa_player_id,
                M.Projection.matchday == matchday,
            ),
        )
        .outerjoin(M.PlayerForm, M.PlayerForm.player_id == M.Player.uefa_player_id)
        .outerjoin(
            M.PlayerStat,
            and_(
                M.PlayerStat.player_id == M.Player.uefa_player_id,
                M.PlayerStat.scope == "combined",
            ),
        )
    )


def projected_players(
    session: Session,
    matchday: int,
    *,
    position: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[S.PlayerRow]:
    q = _player_select(matchday).where(M.Projection.matchday == matchday)
    if position:
        q = q.where(M.Player.position == position)
    if max_price is not None:
        q = q.where(M.Player.price <= max_price)
    if min_price is not None:
        q = q.where(M.Player.price >= min_price)
    if search:
        q = q.where(M.Player.name.ilike(f"%{search}%"))
    q = q.order_by(M.Projection.xpts.desc()).limit(limit)
    return [_player_row(S.PlayerRow, r) for r in session.execute(q)]


def all_players(session: Session, matchday: int) -> list[S.PlayerRow]:
    return [_player_row(S.PlayerRow, r) for r in session.execute(_player_select(matchday))]


def my_squad(session: Session, matchday: int) -> list[S.UclSquadRow]:
    q = (
        _player_select(matchday)
        .add_columns(M.MySquad)
        .join(M.MySquad, M.MySquad.player_id == M.Player.uefa_player_id)
        .where(M.MySquad.matchday == matchday)
    )
    out = []
    for r in session.execute(q):
        sq: M.MySquad = r.MySquad
        out.append(
            _player_row(
                S.UclSquadRow, r, is_starter=sq.is_starter, is_captain=sq.is_captain,
                is_vice=sq.is_vice, bench_order=sq.bench_order, purchase_price=sq.purchase_price,
            )
        )
    return out


def players_page(
    session: Session,
    *,
    position: str | None,
    max_price: float | None,
    search: str | None,
    limit: int,
) -> S.UclPlayersResponse:
    md = current_matchday(session)
    rows = projected_players(
        session, md, position=position, max_price=max_price, search=search, limit=limit
    )
    owned = [r.player_id for r in my_squad(session, md)]
    return S.UclPlayersResponse(matchday=md, owned_ids=owned, players=rows)


# ---- fixtures ---------------------------------------------------------------------------


def fixtures(session: Session, matchday: int) -> list[S.FixtureRow]:
    home, away = aliased(M.Team), aliased(M.Team)
    q = (
        select(M.Fixture, home, away)
        .join(home, home.uefa_team_id == M.Fixture.home_team_id)
        .join(away, away.uefa_team_id == M.Fixture.away_team_id)
        .where(M.Fixture.matchday == matchday)
        .order_by(M.Fixture.kickoff)
    )
    return [
        S.FixtureRow(
            match_id=f.uefa_match_id, matchday=f.matchday, kickoff=_iso(f.kickoff),
            status=f.status, home_team=h.name, away_team=a.name, home_xg=f.home_xg_est,
            away_xg=f.away_xg_est, home_goals=f.home_goals, away_goals=f.away_goals,
        )
        for f, h, a in session.execute(q).tuples()
    ]


def fixture_ticker(session: Session, from_md: int, ahead: int = 5) -> list[S.TickerRow]:
    """Colour-coded fixture difficulty for every club over the next matchdays."""
    home, away = aliased(M.Team), aliased(M.Team)
    q = (
        select(M.Fixture, home, away)
        .join(home, home.uefa_team_id == M.Fixture.home_team_id)
        .join(away, away.uefa_team_id == M.Fixture.away_team_id)
        .where(M.Fixture.matchday.between(from_md, from_md + ahead - 1))
        .order_by(M.Fixture.matchday, M.Fixture.kickoff)
    )
    rows: dict[int, S.TickerRow] = {}

    def ensure(t: M.Team) -> S.TickerRow:
        if t.uefa_team_id not in rows:
            rows[t.uefa_team_id] = S.TickerRow(
                team_id=t.uefa_team_id, team=t.name, code=t.code or "", cells=[], avg_difficulty=0
            )
        return rows[t.uefa_team_id]

    for f, h, a in session.execute(q).tuples():
        for own, opp, is_home in ((h, a, True), (a, h, False)):
            att = pos_fdr(opp.attack_rating, opp.defence_rating, is_home, "FWD", "ucl",
                          own.attack_rating, own.defence_rating)
            dfn = pos_fdr(opp.attack_rating, opp.defence_rating, is_home, "DEF", "ucl",
                          own.attack_rating, own.defence_rating)
            ensure(own).cells.append(
                S.TickerCell(
                    matchday=f.matchday, opp=opp.name, opp_code=opp.code or "", home=is_home,
                    difficulty=blended_rate(opp.attack_rating, opp.defence_rating, is_home),
                    att_difficulty=att.att, def_difficulty=dfn.def_, kickoff=_iso(f.kickoff),
                )
            )
    out = list(rows.values())
    for r in out:
        r.cells.sort(key=lambda c: c.matchday)
        r.avg_difficulty = sum(c.difficulty for c in r.cells) / len(r.cells) if r.cells else 0.0
    return sorted(out, key=lambda r: (r.avg_difficulty, r.team.casefold()))


def fixtures_page(session: Session, ahead: int = 5) -> S.UclFixturesResponse:
    md = current_matchday(session)
    mds = [m for m in range(md, md + ahead) if m <= LAST_LEAGUE_MD] or [md]
    return S.UclFixturesResponse(matchdays=mds, rows=fixture_ticker(session, md, ahead))


# ---- team watch ------------------------------------------------------------------------


def _start_score(p: S.PlayerRow) -> float:
    if p.confirmed == "bench":
        return 0.0
    if p.confirmed == "start":
        return max(0.99, p.p_start if p.p_start is not None else 0.99)
    s = p.p_start if p.p_start is not None else p.start_prob
    if s is not None and s > 0:
        return s
    return max(0.12, min(0.7, (p.xpts or 0) / 6))


def _tier(atk: float, dfn: float) -> str:
    s = atk - (dfn - 1)
    if s >= 1.35:
        return "elite"
    if s >= 1.1:
        return "strong"
    if s >= 0.95:
        return "mid"
    if s >= 0.8:
        return "weak"
    return "minnow"


def teams_page(session: Session) -> S.UclTeamsResponse:
    md = current_matchday(session)
    ticker = {r.team_id: r for r in fixture_ticker(session, md, 5)}
    by_team: dict[int, list[S.PlayerRow]] = {}
    for p in all_players(session, md):
        by_team.setdefault(p.team_id, []).append(p)

    def has_tag(p: S.PlayerRow, tag: str) -> bool:
        return tag in [s.strip() for s in (p.set_piece or "").split(",")]

    out = []
    for t in session.scalars(select(M.Team).order_by(M.Team.name)):
        roster = by_team.get(t.uefa_team_id, [])
        tk = ticker.get(t.uefa_team_id)
        pool = [p for p in roster if p.team_ok is not False and p.status_code < 2]
        picked = pick_formation_xi(
            pool,
            is_gk=lambda p: p.position == "GK",
            is_def=lambda p: p.position == "DEF",
            is_mid=lambda p: p.position == "MID",
            is_fwd=lambda p: p.position == "FWD",
            score=_start_score,
        )
        out.append(
            S.TeamDossier(
                team_id=t.uefa_team_id, team=t.name, code=t.code or "",
                attack_rating=t.attack_rating, defence_rating=t.defence_rating,
                tier=_tier(t.attack_rating, t.defence_rating),
                fixtures=tk.cells if tk else [], avg_difficulty=tk.avg_difficulty if tk else 0.0,
                probable_xi=picked.xi, bench=picked.bench,
                set_pieces={
                    "pk": [p for p in roster if has_tag(p, "PK")],
                    "fk": [p for p in roster if has_tag(p, "FK")],
                    "ck": [p for p in roster if has_tag(p, "CK")],
                },
                doubts=sorted(
                    (p for p in roster if p.status_code >= 1),
                    key=lambda p: (-p.status_code, -(p.xpts or 0)),
                ),
                moved_on=[p for p in roster if p.team_ok is False],
                top_picks=sorted(
                    (p for p in roster if (p.xpts or 0) > 0), key=lambda p: -(p.xpts or 0)
                )[:5],
            )
        )
    out.sort(key=lambda d: (d.avg_difficulty, d.team.casefold()))
    return S.UclTeamsResponse(matchday=md, teams=out)


# ---- league table + strategy -----------------------------------------------------------


def _league_ids(session: Session) -> tuple[str | None, str | None]:
    s = get_settings(session, [Keys.LEAGUE_ID, Keys.ENTRY_ID])
    return s.get(Keys.LEAGUE_ID) or None, s.get(Keys.ENTRY_ID) or None


def league_table(session: Session, matchday: int) -> tuple[str | None, str | None, list[M.LeagueStanding]]:
    league_id, me = _league_ids(session)
    if not league_id:
        return None, me, []
    rows = session.scalars(
        select(M.LeagueStanding)
        .where(M.LeagueStanding.league_id == league_id, M.LeagueStanding.matchday == matchday)
        .order_by(M.LeagueStanding.rank)
    ).all()
    return league_id, me, list(rows)


class StandingLike(Protocol):
    entry_id: str
    rank: int
    total_points: int
    manager_name: str


def league_phase_strategy(
    standings: Sequence[StandingLike],
    my_entry_id: str | None,
    matchday: int,
    last_league_md: int = LAST_LEAGUE_MD,
) -> S.LeagueStrategy | None:
    """What the league-phase table position says about playing the armband and
    differentials: protect a lead, chase a gap, or just play the best XI."""
    mds_left = max(0, last_league_md - matchday + 1)
    me = next((r for r in standings if r.entry_id == my_entry_id), None)
    if me is None or me.rank is None:
        return None
    room = mds_left * 14  # ~a plausible points swing between two managers per MD
    behind = next((r for r in standings if r.rank == me.rank + 1), None)
    ahead = next((r for r in standings if r.rank == me.rank - 1), None)
    gap_ahead = ahead.total_points - me.total_points if ahead else None
    lead = me.total_points - behind.total_points if behind else None
    lead_txt = f"{lead:g}" if lead is not None else "—"
    if me.rank == 1:
        if (lead if lead is not None else 999) > room:
            return S.LeagueStrategy(
                mode="protect", mds_left=mds_left, captain="safe",
                text=f"You lead by {lead_txt} with {mds_left} MD left — protect it. Own what "
                "your rivals own (template), take the safe captain, and don't chase "
                "differentials that only help if they blow up.",
            )
        return S.LeagueStrategy(
            mode="hold", mds_left=mds_left, captain="match",
            text=f"Lead is only {lead_txt} with {mds_left} MD left — match your nearest "
            "rival's captain and their big differentials so a single haul can't flip the table.",
        )
    if gap_ahead is not None and gap_ahead <= room:
        name = (ahead.manager_name if ahead else "") or "the spot ahead"
        return S.LeagueStrategy(
            mode="chase", mds_left=mds_left, captain="differential",
            text=f"{gap_ahead:g} pts behind {name} with {mds_left} MD left — you need variance. "
            "Fade template, take the aggressive (differential) captain, and prioritise "
            "low-owned high-xPts players from the list below.",
        )
    return S.LeagueStrategy(
        mode="free", mds_left=mds_left, captain="best",
        text="Out of realistic range of a prize place — just play the highest expected "
        "points every matchday, no need to hedge or gamble.",
    )


# ---- captaincy + checklist ----------------------------------------------------------------


def best_xi_plus_captain(rows: Sequence[S.UclSquadRow]) -> float:
    """Best 11 by xPts plus the captain doubled (the flagged captain if he made
    the XI, else the top scorer) — matches the live model's pre-match total."""
    xi = sorted(rows, key=lambda r: -(r.xpts or 0))[:11]
    base = sum(r.xpts or 0 for r in xi)
    cap = next((r for r in xi if r.is_captain), None)
    bonus = (cap.xpts or 0) if cap else max((r.xpts or 0 for r in xi), default=0.0)
    return round1(base + bonus)


def captaincy_verdict(
    captains: S.CaptainAnalysis,
    squad_ids: set[int],
    current_captain_id: int | None,
    strategy: S.LeagueStrategy | None,
    current_captain: S.CaptainCandidate | None = None,
) -> S.CaptaincyVerdict | None:
    """The armband as a KEEP / CHANGE / SET call: the model's safe or
    differential pick, chosen by what the league position needs."""
    cands = [c for c in captains.candidates if c.player_id in squad_ids]
    if not cands:
        return None

    def in_squad(c: S.CaptainCandidate | None) -> S.CaptainCandidate | None:
        return c if c and c.player_id in squad_ids else None

    safe = in_squad(captains.safe_pick) or sorted(
        cands, key=lambda c: -(0.6 * c.ev + 0.4 * c.floor)
    )[0]
    diff = in_squad(captains.differential_pick)
    best = sorted(cands, key=lambda c: -c.ev)[0]
    mode = strategy.captain if strategy else "best"
    pick = diff if mode == "differential" and diff else safe if mode == "safe" else best
    if mode == "differential" and diff:
        why = "you're chasing — take the higher ceiling"
    elif mode == "safe":
        why = "protecting a lead — take the higher floor"
    elif mode == "match":
        why = "narrow lead — match the field, but this is the model's pick"
    else:
        why = "highest expected points"
    current = next((c for c in cands if c.player_id == current_captain_id), None)
    if current is None and current_captain_id is not None and current_captain is not None:
        # a captain is set but the model didn't shortlist him: still judge the move
        current = current_captain
    change = bool(current and pick.player_id != current.player_id and pick.ev - current.ev >= 0.6)
    rec: Literal["keep", "change", "set"] = (
        "set" if current is None else "change" if change else "keep"
    )
    return S.CaptaincyVerdict(
        recommendation=rec, pick=pick, current=current, why=why,
        differential=diff if diff and diff.player_id != pick.player_id else None,
        rows=sorted(cands, key=lambda c: -c.ev)[:4],
    )


def _as_candidate(r: S.UclSquadRow | None) -> S.CaptainCandidate | None:
    if r is None:
        return None
    x = r.xpts or 0.0
    return S.CaptainCandidate(
        player_id=r.player_id, name=r.name, team=r.team_name, position=r.position,
        ev=round(2 * x, 2), ceiling=round(2 * (r.xpts_high or x), 2),
        floor=round(2 * (r.xpts_low or x), 2), owned=round(r.selected_pct, 1),
    )


def pre_deadline_checklist(squad: Sequence[S.UclSquadRow], opt: S.OptimizerOutput | None) -> list[CheckItem]:
    checks: list[CheckItem] = []
    ids = {r.player_id for r in squad}
    cap = next((r for r in squad if r.is_captain), None)
    raw_safe = opt.captains.safe_pick if opt and opt.captains else None
    # only trust the model's pick if it's one of YOUR players
    safe = raw_safe if raw_safe and raw_safe.player_id in ids else None
    if cap:
        text = (
            f"Captain is {cap.name} — model prefers {safe.name}"
            if safe and cap.player_id != safe.player_id
            else f"Captain set ({cap.name})"
        )
    else:
        text = "No captain set"
    checks.append(CheckItem(ok=cap is not None and (not safe or cap.player_id == safe.player_id), text=text))
    starters = [r for r in squad if r.is_starter]

    def flagged(r: S.UclSquadRow) -> bool:
        if r.confirmed == "start":
            return False
        if r.confirmed == "bench":
            return True
        return (r.status_code or 0) >= 1 or (r.start_prob if r.start_prob is not None else 1) < 0.5

    flags = [r for r in starters if flagged(r)]
    checks.append(CheckItem(
        ok=not flags,
        text=f"{len(flags)} starter(s) benched / injured / rotation risk: "
        + ", ".join(r.name for r in flags)
        if flags else "No injury or rotation flags in your XI",
    ))
    full = len(starters) >= 11
    checks.append(CheckItem(ok=full, text="Full XI selected" if full else f"Only {len(starters)} starters set"))
    timing = opt.matchday_timing if opt else None
    names = {r.name for r in squad}
    live_opts = [n for n in (timing.live_options if timing else []) if n in names]
    if timing and timing.days > 1 and live_opts:
        checks.append(CheckItem(
            ok=True,
            text=f"Bench your day-{timing.days} players as live options: {', '.join(live_opts[:3])}",
        ))
    if opt and opt.transfers:
        checks.append(CheckItem(
            ok=False, text=f"{len(opt.transfers)} transfer(s) suggested — see Optimizer",
            href="/ucl/optimizer",
        ))
    return checks


# ---- documents -----------------------------------------------------------------------------


def optimizer_output(session: Session) -> S.OptimizerOutput | None:
    doc = get_document(session, Docs.UCL_OPTIMIZER)
    return S.OptimizerOutput.model_validate(doc) if doc else None


def live_state(session: Session) -> S.LiveState | None:
    doc = get_document(session, Docs.UCL_LIVE_STATE)
    if not doc or not isinstance(doc.get("squad"), list):
        return None
    return S.LiveState.model_validate(doc)


def live_rivals(session: Session) -> S.LiveRivals | None:
    doc = get_document(session, Docs.UCL_LIVE_RIVALS)
    if not doc or not isinstance(doc.get("rows"), list):
        return None
    return S.LiveRivals.model_validate(doc)


def live_history(session: Session, matchday: int) -> list[S.LiveSnapshotPoint]:
    """The in-play graph, first kickoff to final whistle. Snapshots taken after
    the matchday finished add nothing, so the graph stops at the first one."""
    rows = session.scalars(
        select(M.LiveSnapshot)
        .where(M.LiveSnapshot.matchday == matchday)
        .order_by(M.LiveSnapshot.captured_at)
        .limit(400)
    )
    out: list[S.LiveSnapshotPoint] = []
    for r in rows:
        out.append(S.LiveSnapshotPoint(
            captured_at=r.captured_at.isoformat(), secured=r.secured, projected=r.projected,
            pre_match=r.pre_match, state=r.state,
        ))
        if r.state == "finished":
            break
    return out


# ---- overview ----------------------------------------------------------------------------


def overview(session: Session) -> S.UclOverview:
    md = current_matchday(session)
    league = session.get(M.League, "ucl")
    live = live_state(session)
    # the live document may be for a just-finished matchday during the
    # roll-over window: key its history and rivals off its own matchday, and
    # everything about the squad (opponents, fixtures) off the current one
    live_md = live.matchday if live else md
    squad = my_squad(session, md)
    fx = fixtures(session, md)
    _, me, table = league_table(session, md)
    opt = optimizer_output(session)
    rivals_doc = live_rivals(session)
    deadline = _iso(league.deadline) if league else None
    if not squad:
        return S.UclOverview(
            matchday=md, deadline_iso=deadline, has_squad=False, cards=None, live=live,
            live_history=[], live_rivals=None, strategy=None, captaincy=None, checklist=[],
            squad=[], fixtures_matchday=md, fixtures=fx,
        )

    ctx: dict[str, tuple[str, bool, M.Team, M.Team]] = {}
    teams = {t.uefa_team_id: t for t in session.scalars(select(M.Team))}
    for f in session.scalars(select(M.Fixture).where(M.Fixture.matchday == md)):
        h, a = teams.get(f.home_team_id), teams.get(f.away_team_id)
        if h and a:
            ctx[h.name] = (a.name, True, a, h)
            ctx[a.name] = (h.name, False, h, a)

    captain_pick = max(squad, key=lambda r: r.xpts or 0)
    my_row = next((r for r in table if r.entry_id == me), None)
    strategy = league_phase_strategy(table, me, md)
    rows: list[S.SquadTableRow] = []
    for pos in POSITIONS:
        for r in sorted((r for r in squad if r.position == pos), key=lambda r: -(r.xpts or 0)):
            c = ctx.get(r.team_name)
            opponent = None
            if c:
                opp_name, is_home, opp, own = c
                d = pos_fdr(opp.attack_rating, opp.defence_rating, is_home, r.position, "ucl",
                            own.attack_rating, own.defence_rating)
                opponent = S.Opponent(
                    name=opp_name, home=is_home,
                    fdr=S.FixtureDifficulty(att=d.att, def_=d.def_, pos=d.pos),
                )
            rows.append(S.SquadTableRow(
                **r.model_dump(), opponent=opponent,
                recommended_captain=r.player_id == captain_pick.player_id,
            ))
    return S.UclOverview(
        matchday=md,
        deadline_iso=deadline,
        has_squad=True,
        cards=S.OverviewCards(
            proj_total=best_xi_plus_captain(squad),
            captain_pick_name=captain_pick.name,
            captain_pick_xpts=captain_pick.xpts,
            squad_value=round(sum(r.price for r in squad), 1),
            rank=my_row.rank if my_row else None,
            league_size=len(table),
        ),
        live=live,
        live_history=live_history(session, live_md) if live else [],
        live_rivals=rivals_doc if rivals_doc and rivals_doc.matchday == live_md else None,
        strategy=strategy,
        captaincy=captaincy_verdict(
            opt.captains if opt and opt.captains else S.CaptainAnalysis(),
            {r.player_id for r in squad},
            next((r.player_id for r in squad if r.is_captain), None),
            strategy,
            current_captain=_as_candidate(next((r for r in squad if r.is_captain), None)),
        ),
        checklist=pre_deadline_checklist(squad, opt),
        squad=rows,
        fixtures_matchday=md,
        fixtures=fx,
    )


def optimizer_page(session: Session) -> S.UclOptimizerResponse:
    opt = optimizer_output(session)
    return S.UclOptimizerResponse(available=opt is not None, output=opt)


# ---- rivals --------------------------------------------------------------------------------


def _norm_squad(raw: Any) -> tuple[list[int], int | None, set[int]]:
    """A rival's saved squad: new rows are [{id,c,s,b}], older ones a bare list."""
    if not isinstance(raw, list) or not raw:
        return [], None, set()
    if isinstance(raw[0], int):
        return [int(x) for x in raw], None, set()
    ids = [int(x["id"]) for x in raw if isinstance(x, dict) and "id" in x]
    cap = next((int(x["id"]) for x in raw if isinstance(x, dict) and x.get("c")), None)
    starters = {int(x["id"]) for x in raw if isinstance(x, dict) and x.get("s")}
    return ids, cap, starters


def rival_report(session: Session, matchday: int) -> S.RivalReport:
    league_id, me = _league_ids(session)
    empty = S.RivalReport(
        ready=False, my_projected_points=0, my_rank=None, rivals=[], template_risk=[],
        common_threats=[], effective_ownership=[], captain_picks=[], strategy=None,
        rival_count=0, squads_as_of=None, squads_matchday=None, stale=False,
    )
    if not league_id:
        return empty

    def rows_for(md: int) -> list[M.LeagueStanding]:
        return list(session.scalars(
            select(M.LeagueStanding)
            .where(M.LeagueStanding.league_id == league_id, M.LeagueStanding.matchday == md)
            .order_by(M.LeagueStanding.rank)
        ))

    squads_md = matchday
    standings = rows_for(matchday)
    if not any(_norm_squad(r.squad)[0] for r in standings):
        # nothing for this matchday yet: fall back to the latest earlier one
        # that has squads, and flag it as stale
        prev = session.scalar(
            select(M.LeagueStanding.matchday)
            .where(
                M.LeagueStanding.league_id == league_id,
                M.LeagueStanding.matchday <= matchday,
                M.LeagueStanding.squad.is_not(None),
            )
            .order_by(M.LeagueStanding.matchday.desc())
            .limit(1)
        )
        if prev is not None and prev != matchday:
            squads_md = prev
            standings = rows_for(prev)
    parsed = {r.entry_id: _norm_squad(r.squad) for r in standings}
    with_squads = [r for r in standings if parsed[r.entry_id][0]]
    if not with_squads:
        return empty

    as_of = min(r.updated_at for r in with_squads)
    stale = squads_md != matchday or (datetime.now(UTC) - as_of).total_seconds() > RIVAL_STALE_SECONDS

    mine = my_squad(session, matchday)
    my_ids = {r.player_id for r in mine}
    my_starters = {r.player_id for r in mine if r.is_starter}
    my_captain = next((r.player_id for r in mine if r.is_captain), None)
    all_ids = set(my_ids)
    for r in with_squads:
        all_ids.update(parsed[r.entry_id][0])

    meta: dict[int, tuple[str, str, str, float]] = {}
    q = (
        select(M.Player.uefa_player_id, M.Player.name, M.Player.position, M.Team.name, M.Projection.xpts)
        .join(M.Team, M.Team.uefa_team_id == M.Player.team_id)
        .outerjoin(
            M.Projection,
            and_(M.Projection.player_id == M.Player.uefa_player_id, M.Projection.matchday == matchday),
        )
        .where(M.Player.uefa_player_id.in_(all_ids))
    )
    for pid, name, pos, team, xpts in session.execute(q).tuples():
        meta[pid] = (name, pos, team, xpts or 0.0)

    def project(ids: list[int], captain: int | None, starters: set[int]) -> float:
        rows = [(i, meta[i][3]) for i in ids if i in meta]
        xi = (
            [r for r in rows if r[0] in starters]
            if len(starters) >= 11
            else sorted(rows, key=lambda r: -r[1])[:11]
        )
        total = sum(x for _, x in xi)
        cap = meta[captain][3] if captain is not None and captain in meta else max(
            [0.0, *(x for _, x in xi)]
        )
        return total + cap

    my_proj = round1(project(list(my_ids), my_captain, my_starters))
    my_rank = next((r.rank for r in standings if r.entry_id == me), None)

    def player(pid: int, is_mine: bool) -> S.RivalPlayer | None:
        if pid not in meta:
            return None
        name, pos, team, xpts = meta[pid]
        return S.RivalPlayer(player_id=pid, name=name, position=pos, team=team, xpts=xpts, mine=is_mine)

    rivals_st = [r for r in with_squads if r.entry_id != me]
    rivals: list[S.RivalRow] = []
    for r in rivals_st:
        ids, cap, starters = parsed[r.entry_id]
        theirs = set(ids)
        diffs = sorted(
            (p for i in ids if i not in my_ids and (p := player(i, False))), key=lambda p: -p.xpts
        )
        edges = sorted(
            (p for i in my_ids if i not in theirs and (p := player(i, True))), key=lambda p: -p.xpts
        )
        proj = round1(project(ids, cap, starters))
        rivals.append(S.RivalRow(
            entry_id=r.entry_id, manager_name=r.manager_name, team_name=r.team_name, rank=r.rank,
            total_points=r.total_points, projected_points=proj, gap_vs_me=round1(proj - my_proj),
            overlap=15 - len(diffs), their_differentials=diffs[:6], my_edges=edges[:6],
        ))
    rivals.sort(key=lambda x: x.rank)

    own_count: dict[int, int] = {}
    for r in rivals_st:
        for i in parsed[r.entry_id][0]:
            own_count[i] = own_count.get(i, 0) + 1

    def owned(pid: int, n: int) -> S.OwnedPlayer:
        name = meta[pid][0] if pid in meta else str(pid)
        return S.OwnedPlayer(player_id=pid, name=name, xpts=meta[pid][3] if pid in meta else 0.0,
                             owned_by_rivals=n)

    template = sorted(
        (owned(i, own_count.get(i, 0)) for i in my_ids if own_count.get(i, 0) > 0),
        key=lambda o: (-o.owned_by_rivals, -o.xpts),
    )
    half = math.ceil(len(rivals_st) / 2)
    threats = sorted(
        (owned(i, n) for i, n in own_count.items() if n >= half and i not in my_ids),
        key=lambda o: (-o.owned_by_rivals, -o.xpts),
    )
    size = len(with_squads)
    own_all: dict[int, int] = {}
    for r in with_squads:
        for i in parsed[r.entry_id][0]:
            own_all[i] = own_all.get(i, 0) + 1
    eff = sorted(
        (
            S.UclEffectiveOwnership(
                player_id=i, name=meta[i][0] if i in meta else str(i),
                team=meta[i][2] if i in meta else "", xpts=meta[i][3] if i in meta else 0.0,
                owned_pct=js_round(100 * own_all.get(i, 0) / size), mine=i in my_ids,
            )
            for i in all_ids
        ),
        key=lambda e: -e.xpts,
    )
    eff = [e for e in eff if e.xpts > 0]
    cap_count: dict[int, int] = {}
    for r in with_squads:
        cid = parsed[r.entry_id][1]
        if cid:
            cap_count[cid] = cap_count.get(cid, 0) + 1
    captain_picks = sorted(
        (
            S.CaptainCount(player_id=i, name=meta[i][0] if i in meta else str(i), count=n,
                           mine=my_captain == i)
            for i, n in cap_count.items()
        ),
        key=lambda c: -c.count,
    )
    return S.RivalReport(
        ready=True, my_projected_points=my_proj, my_rank=my_rank, rivals=rivals,
        template_risk=template, common_threats=threats, effective_ownership=eff,
        captain_picks=captain_picks, strategy=league_phase_strategy(standings, me, matchday),
        rival_count=len(rivals_st), squads_as_of=as_of.isoformat(), squads_matchday=squads_md,
        stale=stale,
    )


def rivals_page(session: Session) -> S.UclRivalsResponse:
    md = current_matchday(session)
    live = live_rivals(session)
    return S.UclRivalsResponse(
        matchday=md, report=rival_report(session, md), live=live if live and live.rows else None
    )


# ---- league (standings, power ranking, finish odds, calibration) -----------------------------


def project_finish(
    aggs: Sequence[S.EntryAggregate],
    played_md: int,
    iters: int = 4000,
    rng: np.random.Generator | None = None,
) -> list[S.FinishOdds]:
    """Monte Carlo the rest of the league phase: each entry's remaining
    matchdays drawn from their per-MD mean (nudged toward the last 3) with the
    observed spread, floored so a 1-2 MD sample doesn't look certain."""
    remaining = max(0, LAST_LEAGUE_MD - played_md)
    if remaining == 0 or len(aggs) < 2:
        return []
    rng = rng or np.random.default_rng()
    n = len(aggs)
    rate = np.array([0.65 * e.avg + 0.35 * (e.form3 / min(3, max(1, e.matchdays))) for e in aggs])
    sd = np.array([max(6.0, e.stdev) for e in aggs])
    draws = np.maximum(0, rng.normal(rate[None, None, :], sd[None, None, :], size=(iters, remaining, n)))
    finals = np.array([e.total for e in aggs])[None, :] + draws.sum(axis=1)
    order = np.argsort(-finals, axis=1, kind="stable")
    rank = np.empty_like(order)
    rank[np.arange(iters)[:, None], order] = np.arange(n)[None, :]
    half = math.ceil(n / 2)
    return [
        S.FinishOdds(
            entry_id=e.entry_id, name=e.name, now=e.total,
            proj_points=js_round(e.total + remaining * rate[i]),
            mean_rank=float(rank[:, i].mean() + 1),
            first_pct=float((rank[:, i] == 0).mean() * 100),
            top_half_pct=float((rank[:, i] < half).mean() * 100),
            mine=e.mine,
        )
        for i, e in enumerate(aggs)
    ]


def league_page(session: Session) -> S.LeagueResponse:
    md = current_matchday(session)
    league_id, me, table = league_table(session, md)
    cal_doc = get_document(session, Docs.UCL_CALIBRATION)
    calibration = S.Calibration.model_validate(cal_doc) if cal_doc else None
    if not league_id:
        return S.LeagueResponse(matchday=md, league_id=None, standings=[], leader_points=0,
                                power_ranking=[], mds_left=0, finish=[], calibration=calibration)
    # Each sync files the table under the current matchday, so from the
    # moment a matchday becomes current to its first kickoff there's a row
    # for it with no points of its own. Only matchdays that have kicked off
    # count.
    kicked_off = played_matchday(session)
    history = session.scalars(
        select(M.LeagueStanding)
        .where(M.LeagueStanding.league_id == league_id, M.LeagueStanding.matchday <= kicked_off)
        .order_by(M.LeagueStanding.matchday, M.LeagueStanding.rank)
    ).all()
    if history:
        md = history[-1].matchday
        table = [r for r in history if r.matchday == md]
    per: dict[str, list[M.LeagueStanding]] = {}
    for r in history:
        per.setdefault(r.entry_id, []).append(r)
    aggs: list[S.EntryAggregate] = []
    for entry, rows in per.items():
        pts = [r.points for r in rows]
        n = len(pts) or 1
        avg = sum(pts) / n
        aggs.append(S.EntryAggregate(
            entry_id=entry, name=rows[-1].manager_name, team=rows[-1].team_name, matchdays=n,
            total=rows[-1].total_points, avg=avg, best=max(pts, default=0),
            worst=min(pts, default=0), stdev=math.sqrt(sum((p - avg) ** 2 for p in pts) / n),
            form3=sum(pts[-3:]), last_rank=rows[-1].rank, mine=entry == me,
        ))
    played = max((r.matchday for r in history), default=0)
    finish = sorted(project_finish(aggs, played), key=lambda o: o.mean_rank)
    return S.LeagueResponse(
        matchday=md,
        league_id=league_id,
        standings=[
            S.UclStandingRow(
                entry_id=r.entry_id, manager_name=r.manager_name, team_name=r.team_name,
                rank=r.rank, prev_rank=r.prev_rank, points=r.points, total_points=r.total_points,
                mine=r.entry_id == me,
            )
            for r in table
        ],
        leader_points=max((r.total_points for r in table), default=0),
        power_ranking=sorted(aggs, key=lambda e: -e.form3),
        mds_left=max(0, LAST_LEAGUE_MD - played),
        finish=finish,
        calibration=calibration,
    )


# ---- for the home page ------------------------------------------------------------------------


def dashboard_summary(session: Session) -> dict[str, Any]:
    md = current_matchday(session)
    league = session.get(M.League, "ucl")
    squad = my_squad(session, md)
    _, me, table = league_table(session, md)
    run = session.scalars(select(M.IngestRun).order_by(M.IngestRun.started_at.desc()).limit(1)).first()
    live = live_state(session)
    my_row = next((r for r in table if r.entry_id == me), None)
    return {
        "matchday": md,
        "deadline_iso": _iso(league.deadline) if league else None,
        "squad_size": len(squad),
        "projected": best_xi_plus_captain(squad),
        "rank": my_row.rank if my_row else None,
        "league_size": len(table),
        "ingest_ok": run.ok if run else None,
        "ingest_at": _iso(run.finished_at or run.started_at) if run else None,
        "live": live,
    }
