"""FPL Draft pages, assembled from the database.

Ported from the old web app's FPL pages, which loaded the whole board into
the browser and computed everything there (app/fpl/*.tsx).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from fantasy.api.schemas import fpl as S
from fantasy.api.schemas.common import CheckItem
from fantasy.config import Docs
from fantasy.core import models as M
from fantasy.core.store import get_document, get_setting
from fantasy.football.jsmath import js_round
from fantasy.leagues.fpl import analysis as A
from fantasy.leagues.fpl.players import FplPlayer

POS_ORDER = ("GKP", "DEF", "MID", "FWD")


def out(p: FplPlayer) -> S.FplPlayer:
    return S.FplPlayer.model_validate(p).model_copy(update={"opp_tag": A.opp_tag(p)})


def outs(ps: Sequence[FplPlayer]) -> list[S.FplPlayer]:
    return [out(p) for p in ps]


def _ext_key(ext: str) -> tuple[int, str]:
    return (int(ext), "") if ext.isdigit() else (1 << 62, ext)


@dataclass(slots=True)
class Board:
    players: list[FplPlayer]
    by_id: dict[str, FplPlayer]
    my_entry_id: str | None
    lineup: list[M.LineupSlot]
    league: M.League | None
    entries: list[M.LeagueEntry]

    @property
    def gws(self) -> list[int]:
        first = next((p for p in self.players if p.gws), None)
        return [g.gw for g in first.gws] if first else []

    @property
    def my_squad(self) -> list[FplPlayer]:
        return [self.by_id[s.ext_id] for s in self.lineup if s.ext_id in self.by_id]

    @property
    def fallback_names(self) -> dict[str, str]:
        return {e.entry_id: e.name for e in self.entries}

    def managers(self) -> list[A.Manager]:
        return A.group_by_manager(self.players, self.my_entry_id, self.fallback_names)


def load_board(session: Session) -> Board:
    rows = session.scalars(select(M.DraftPlayer).where(M.DraftPlayer.sport == "fpl")).all()
    players = sorted((FplPlayer.from_row(r) for r in rows), key=lambda p: _ext_key(p.ext_id))
    lineup = session.scalars(
        select(M.LineupSlot)
        .where(M.LineupSlot.sport == "fpl")
        .order_by(M.LineupSlot.position.nulls_last(), M.LineupSlot.ext_id)
    ).all()
    entries = session.scalars(
        select(M.LeagueEntry)
        .where(M.LeagueEntry.sport == "fpl")
        .order_by(M.LeagueEntry.rank.nulls_last(), M.LeagueEntry.entry_id)
    ).all()
    return Board(
        players=players,
        by_id={p.ext_id: p for p in players},
        my_entry_id=get_setting(session, "draft.fpl.entry_id") or None,
        lineup=list(lineup),
        league=session.get(M.League, "fpl"),
        entries=list(entries),
    )


def board_page(session: Session) -> S.BoardResponse:
    b = load_board(session)
    return S.BoardResponse(gws=b.gws, my_ids=[p.ext_id for p in b.my_squad], players=outs(b.players))


# ---- overview ------------------------------------------------------------------------------

STATUS_FORMATION_MIN = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
STATUS_FORMATION_MAX = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 10**9}


def _formation_ok(c: dict[str, int]) -> bool:
    return sum(c.values()) == 11 and all(
        STATUS_FORMATION_MIN[p] <= c.get(p, 0) <= STATUS_FORMATION_MAX[p] for p in STATUS_FORMATION_MIN
    )


def live_view(live: dict[str, Any], b: Board) -> S.FplLiveView | None:
    """Points banked, projected finish after FPL's automatic substitutions, and
    the head-to-head score. Draft has no captain — nothing is doubled."""
    elements: dict[str, list[int]] = live.get("elements") or {}
    finished = live.get("state") == "finished"

    @dataclass(slots=True)
    class Row:
        p: FplPlayer
        pts: int
        mins: int
        slot: int
        starter: bool
        dnp: bool
        proj: float
        role: str

    rows: list[Row] = []
    for s in b.lineup:
        p = b.by_id.get(s.ext_id)
        if p is None:
            continue
        pts, mins = (elements.get(s.ext_id) or [0, 0])[:2]
        fallback = p.gws[0].xpts if p.gws else p.proj
        rows.append(Row(
            p=p, pts=int(pts), mins=int(mins), slot=s.position or 0, starter=s.starter,
            dnp=finished and mins == 0, proj=float(pts) if mins > 0 or finished else fallback,
            role="start" if s.starter else "bench",
        ))
    by_id = {r.p.ext_id: r for r in rows}
    starters = [r for r in rows if r.starter]
    bench = sorted((r for r in rows if not r.starter), key=lambda r: r.slot)
    xi = [r.p.ext_id for r in starters]
    counts: dict[str, int] = {}
    for r in starters:
        counts[r.p.pos] = counts.get(r.p.pos, 0) + 1
    subs: list[S.LiveSubstitution] = []
    used: set[str] = set()
    if finished:
        for st in (r for r in starters if r.dnp):
            for bn in bench:
                if bn.p.ext_id in used or bn.dnp:
                    continue
                if (st.p.pos == "GKP") != (bn.p.pos == "GKP"):
                    continue
                trial = dict(counts)
                trial[st.p.pos] = trial.get(st.p.pos, 0) - 1
                trial[bn.p.pos] = trial.get(bn.p.pos, 0) + 1
                if not _formation_ok(trial):
                    continue
                counts = trial
                xi.remove(st.p.ext_id)
                xi.append(bn.p.ext_id)
                used.add(bn.p.ext_id)
                st.role, bn.role = "auto-out", "auto-in"
                subs.append(S.LiveSubstitution(out=st.p.name, in_=bn.p.name))
                break
    projected = sum(by_id[i].proj for i in xi)
    rank = {"auto-out": 2}
    ordered = sorted(
        rows,
        key=lambda r: (
            rank.get(r.role, 0 if r.starter else 1),
            POS_ORDER.index(r.p.pos) if r.p.pos in POS_ORDER else 9,
            -r.proj,
        ),
    )
    return S.FplLiveView(
        gw=int(live.get("gw") or 0),
        state="finished" if finished else "live",
        secured=float(live.get("secured") or 0),
        played=int(live.get("played") or 0),
        starters=int(live.get("starters") or 0),
        projected_finish=projected,
        not_played=[r.p.name for r in starters if r.mins == 0 and not finished],
        auto_subs=subs,
        rows=[
            S.LivePlayerRow(player=out(r.p), points=r.pts, minutes=r.mins, starter=r.starter,
                            dnp=r.dnp, proj=r.proj, role=r.role)  # type: ignore[arg-type]
            for r in ordered
        ],
        my_points=live.get("myPoints"),
        opp_points=live.get("oppPoints"),
        opp_name=live.get("oppName"),
    )


def _checklist(
    xi: Sequence[FplPlayer], bench: Sequence[FplPlayer], next_gw: int, src: str | None
) -> list[CheckItem]:
    c: list[CheckItem] = []
    live = src == "my-team"
    if live:
        text = "Showing your live Pick Team XI from FPL"
    elif src and src.startswith("event/"):
        text = (f"Showing your last fielded XI (GW{src[6:]}) — add the login token in Setup "
                "so we read your live Pick Team")
    else:
        text = "No lineup pulled yet — showing the model's best XI (run the FPL sync)"
    c.append(CheckItem(ok=live, text=text))
    not_nailed = [p for p in xi if 0 < p.p_start < 0.7]
    c.append(CheckItem(
        ok=not not_nailed,
        text=f"{len(not_nailed)} starter(s) not nailed: "
        + ", ".join(f"{p.name} {js_round(p.p_start * 100)}%" for p in not_nailed)
        if not_nailed else "Every starter is a nailed-on starter (≥70%)",
    ))
    inj = [p for p in xi if p.unavailable]
    c.append(CheckItem(
        ok=not inj,
        text=f"{len(inj)} unavailable in your XI: " + ", ".join(p.name for p in inj)
        if inj else "No injured / suspended players in your XI",
    ))
    susp = [p for p in xi if p.susp_risk]
    c.append(CheckItem(
        ok=not susp,
        text="One booking from a ban: " + ", ".join(p.name for p in susp)
        if susp else "No suspension risk in your XI this week",
    ))
    cover = sum(1 for p in bench if not p.unavailable and p.proj >= 2)
    c.append(CheckItem(
        ok=cover >= 2,
        text="Bench has cover if someone doesn't play"
        if cover >= 2 else "Thin bench — a non-starter could cost you points",
    ))
    c.append(CheckItem(ok=True, text=f"Set your lineup before the GW{next_gw or '?'} deadline"))
    return c


def _fixture_run(squad: Sequence[FplPlayer], n: int = 6) -> S.FixtureRun | None:
    """The squad's schedule swing: a squad-average difficulty strip, then each
    player's own run, easiest first."""
    if not squad or not squad[0].gws:
        return None
    cols = squad[0].gws[:n]

    def clamp_mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def axis(p: FplPlayer, i: int) -> int:
        g = p.gws[i]
        return g.fdr_att if g.fdr_att is not None else g.fdr

    col_mean = []
    for i in range(len(cols)):
        vals = [float(axis(p, i)) for p in squad if i < len(p.gws) and axis(p, i) > 0]
        col_mean.append(clamp_mean(vals))
    rows = []
    for p in squad:
        cells = p.gws[:n]
        vals = [float(c.fdr) for c in cells if c.fdr > 0]
        rows.append(S.FixtureRunRow(player=out(p), cells=[S.GwCell.model_validate(c) for c in cells],
                                    mean=clamp_mean(vals) if vals else 3.0))
    rows.sort(key=lambda r: r.mean)
    rated = [m for m in col_mean if m]
    return S.FixtureRun(gws=[c.gw for c in cols], col_mean=col_mean,
                        overall=sum(rated) / (len(rated) or 1), rows=rows)


def overview(session: Session) -> S.FplOverview:
    b = load_board(session)
    squad = b.my_squad
    gws = b.gws
    next_gw = gws[0] if gws else 0
    set_xi = [b.by_id[s.ext_id] for s in b.lineup if s.starter and s.ext_id in b.by_id]
    set_bench = [b.by_id[s.ext_id] for s in b.lineup if not s.starter and s.ext_id in b.by_id]
    src = b.lineup[0].source if b.lineup else None
    from_app = len(set_xi) >= 11
    model = A.best_xi(squad) if len(squad) >= 11 else None
    xi = set_xi if from_app else (model.xi if model else [])
    bench = set_bench if from_app else (model.bench if model else [])
    formation = (
        f"{sum(p.pos == 'DEF' for p in xi)}-{sum(p.pos == 'MID' for p in xi)}-"
        f"{sum(p.pos == 'FWD' for p in xi)}" if xi else ""
    )

    swaps: list[S.Swap] = []
    if from_app and model:
        set_ids = {p.ext_id for p in set_xi}
        model_ids = {p.ext_id for p in model.xi}
        outs_ = [p for p in set_xi if p.ext_id not in model_ids]
        ins = [p for p in model.xi if p.ext_id not in set_ids]
        for o in outs_:
            i = next((x for x in ins if x.pos == o.pos), ins[0] if ins else None)
            if i is None:
                continue
            gain = (i.gws[0].xpts if i.gws else i.proj) - (o.gws[0].xpts if o.gws else o.proj)
            if gain > 0.4:
                swaps.append(S.Swap(out=out(o), in_=out(i), gain=gain))

    mine_entry = next((e for e in b.entries if e.is_mine), None)
    starting = {p.ext_id for p in xi}
    ordered = [
        p
        for pos in POS_ORDER
        for p in sorted(
            (x for x in squad if x.pos == pos),
            key=lambda x: (0 if x.ext_id in starting else 1, -x.ros),
        )
    ]
    live_doc = get_document(session, Docs.FPL_LIVE)
    live = live_view(live_doc, b) if live_doc and len(b.lineup) >= 11 else None
    return S.FplOverview(
        teams=(b.league.n_teams if b.league and b.league.n_teams else 8),
        gws=gws,
        next_gw=next_gw,
        has_squad=bool(squad),
        from_app=from_app,
        lineup_source=src if from_app else None,
        formation=formation,
        next_gw_proj=sum(p.gws[0].xpts if p.gws else p.proj for p in xi),
        ros_per_gw=A.squad_horizon(squad, range(len(gws))) / max(1, len(gws)) if squad else 0.0,
        my_rank=mine_entry.rank if mine_entry else None,
        league_size=len(b.entries),
        live=live,
        swaps=swaps,
        checklist=_checklist(xi, bench, next_gw, src if from_app else None),
        squad=[S.FplSquadRow(player=out(p), starting=p.ext_id in starting) for p in ordered],
        fixture_run=_fixture_run(squad),
    )


# ---- clubs / fixtures ----------------------------------------------------------------------


def fixtures_page(session: Session) -> S.FplFixturesResponse:
    b = load_board(session)
    return S.FplFixturesResponse(
        gws=b.gws, clubs=[S.ClubFix.model_validate(c) for c in A.club_fixtures(b.players)]
    )


def teams_page(session: Session) -> S.FplTeamsResponse:
    b = load_board(session)
    return S.FplTeamsResponse(clubs=[
        S.ClubDossier(
            team=d.team, fixtures=[S.ClubCell.model_validate(c) for c in d.fixtures],
            avg_fdr=d.avg_fdr, probable_xi=outs(d.probable_xi), bench=outs(d.bench),
            set_pieces={k: outs(v) for k, v in d.set_pieces.items()},
            doubts=outs(d.doubts), key_players=outs(d.key_players),
        )
        for d in A.club_dossiers(b.players)
    ])


# ---- optimizer ------------------------------------------------------------------------------


def optimizer_page(session: Session, horizon: str) -> S.FplOptimizerResponse:
    b = load_board(session)
    squad = b.my_squad
    mine = {p.ext_id for p in squad}
    gws = b.gws
    lineup = A.best_xi(squad) if len(squad) >= 11 else None
    free = [p for p in b.players if p.available and p.ext_id not in mine]
    upgrades = A.weak_spots(lineup.xi, free, horizon) if lineup else []
    per_gw = [
        float(sum(p.gw_xpts(i) for p in A.best_xi(squad, A._gw_score(i)).xi))
        for i in range(len(gws))
    ] if lineup else []
    targets: dict[str, list[S.FplPlayer]] = {}
    for pos in ("ALL", *POS_ORDER):
        pool = [p for p in free if pos == "ALL" or p.pos == pos]
        targets[pos] = outs(A.sort_players(pool, "horizon")[:30])
    return S.FplOptimizerResponse(
        horizon=horizon,  # type: ignore[arg-type]
        gws=gws,
        squad=outs(sorted(squad, key=lambda p: (POS_ORDER.index(p.pos) if p.pos in POS_ORDER else 9,
                                                -p.horizon))),
        best_xi_totals=per_gw,
        best_xi_horizon=A.squad_horizon(squad, range(len(gws))) if lineup else 0.0,
        targets=targets,
        upgrades=[
            S.Upgrade(out=out(u.out), in_=out(u.in_), gain=u.gain,
                      out_value=A.value_for(u.out, horizon))
            for u in upgrades
        ],
        stash=outs(A.stash_candidates(b.players, mine)),
    )


# ---- rivals -----------------------------------------------------------------------------------


def _manager_out(m: A.Manager) -> S.Manager:
    return S.Manager(
        entry_id=m.entry_id, name=m.name, is_mine=m.is_mine, players=outs(m.players),
        by_pos={k: outs(v) for k, v in m.by_pos.items()},
        total_medium=m.total_medium, total_season=m.total_season,
    )


def _next_gw_points(p: FplPlayer) -> float:
    return p.gws[0].xpts if p.gws else p.proj


def rivals_page(session: Session) -> S.FplRivalsResponse:
    b = load_board(session)
    managers = b.managers()
    me = next((m for m in managers if m.is_mine), None)
    mine = {p.ext_id for p in me.players} if me else set()

    eff: list[S.FplEffectiveOwnership] = []
    if len(managers) >= 2:
        count: dict[str, tuple[FplPlayer, int]] = {}
        for mg in managers:
            for p in mg.players:
                prev = count.get(p.ext_id)
                count[p.ext_id] = (p, (prev[1] if prev else 0) + 1)
        ranked = sorted(count.values(), key=lambda t: -t[0].ros)[:30]
        eff = [
            S.FplEffectiveOwnership(player=out(p), owners=n, pct=js_round(100 * n / len(managers)),
                                 mine=p.ext_id in mine)
            for p, n in ranked
        ]

    def proj(m: A.Manager) -> float:
        return sum(_next_gw_points(p) for p in A.best_xi(m.players, _next_gw_points).xi)

    rivals = sorted(
        (
            S.RivalProjection(
                entry_id=m.entry_id, name=m.name, proj=proj(m),
                diffs=outs(sorted((p for p in m.players if p.ext_id not in mine),
                                  key=lambda p: -p.ros)[:4]),
            )
            for m in managers
            if not m.is_mine
        ),
        key=lambda r: -r.proj,
    ) if me else []
    claims = A.predict_claims(managers, b.players, b.my_entry_id)
    return S.FplRivalsResponse(
        my_proj=proj(me) if me else 0.0,
        rivals=rivals,
        claims=[
            S.ClaimPrediction(rival_name=c.rival_name, weak_pos=c.weak_pos,
                              weak_starter=c.weak_starter, target=out(c.target), gain=c.gain)
            for c in claims
        ],
        effective_ownership=eff,
        managers=[_manager_out(m) for m in managers],
        league_size=len(managers),
    )


# ---- standings ----------------------------------------------------------------------------------


def simulate_season(
    entries: Sequence[tuple[str, float, float]],
    gws_left: int,
    iters: int = 4000,
    rng: np.random.Generator | None = None,
) -> dict[str, tuple[float, float, float]] | None:
    """Monte Carlo a total-points season: each team's remaining gameweeks drawn
    from its best-XI per-GW rate (ROS ÷ GWs left) with a ~32% spread (a draft
    XI is far less boom/bust than one player). entries: (id, now, ros).
    Returns id -> (first %, top-half %, mean rank)."""
    if gws_left < 1 or len(entries) < 2 or all(ros <= 0 for _, _, ros in entries):
        return None
    rng = rng or np.random.default_rng()
    n = len(entries)
    per_gw = np.array([ros / gws_left for _, _, ros in entries])
    now = np.array([now for _, now, _ in entries])
    draws = np.maximum(0, rng.normal(per_gw, 0.32 * per_gw + 4, size=(iters, gws_left, n)))
    finals = now[None, :] + draws.sum(axis=1)
    order = np.argsort(-finals, axis=1, kind="stable")
    rank = np.empty_like(order)
    rank[np.arange(iters)[:, None], order] = np.arange(n)[None, :]
    half = math.ceil(n / 2)
    return {
        eid: (
            float((rank[:, i] == 0).mean() * 100),
            float((rank[:, i] < half).mean() * 100),
            float(rank[:, i].mean() + 1),
        )
        for i, (eid, _, _) in enumerate(entries)
    }


def standings_page(session: Session) -> S.FplStandingsResponse:
    b = load_board(session)
    managers = b.managers()
    by_entry = {m.entry_id: m for m in managers}
    is_h2h = bool(b.league and b.league.scoring == "h")
    next_gw = b.gws[0] if b.gws else 0
    gws_left = max(1, 39 - (next_gw or 1))

    base = []
    for e in b.entries:
        mg = by_entry.get(e.entry_id)
        ros = mg.total_season if mg else 0.0
        base.append((e, ros, (e.total or 0) + ros))
    proj_order = sorted(base, key=lambda t: -t[2])
    proj_rank = {t[0].entry_id: i + 1 for i, t in enumerate(proj_order)}
    leader_final = proj_order[0][2] if proj_order else 0.0
    odds = None if is_h2h else simulate_season(
        [(e.entry_id, float(e.total or 0), ros) for e, ros, _ in base], gws_left
    )
    rows = [
        S.FplStandingRow(
            entry_id=e.entry_id, name=e.name, rank=e.rank or 0, total=e.total or 0,
            wins=e.wins, draws=e.draws, losses=e.losses, ros=ros, final_pts=final,
            proj_rank=proj_rank[e.entry_id], gap=leader_final - final, mine=e.is_mine,
            first_pct=odds[e.entry_id][0] if odds else None,
            top_half_pct=odds[e.entry_id][1] if odds else None,
            mean_rank=odds[e.entry_id][2] if odds else None,
        )
        for e, ros, final in sorted(base, key=lambda t: t[0].rank or 0)
    ]

    path = None
    me_row = next((r for r in rows if r.mine), None)
    if me_row and rows:
        ahead = sorted((r for r in rows if r.final_pts > me_row.final_pts), key=lambda r: r.final_pts)
        leader = max(rows, key=lambda r: r.final_pts)
        my_mg = by_entry.get(me_row.entry_id)
        xi_ros = [p.ros for p in A.best_xi(my_mg.players).xi] if my_mg else []
        worst = min(xi_ros) if xi_ros else 0.0
        mine_ids = {p.ext_id for p in my_mg.players} if my_mg else set()
        fa = sorted((p for p in b.players if p.available and p.ext_id not in mine_ids
                     and not p.unavailable), key=lambda p: -p.ros)
        best_fa = fa[0] if fa else None
        move = best_fa if best_fa and best_fa.ros - worst > 20 else None
        path = S.Path(
            proj_rank=me_row.proj_rank,
            to_next=js_round(ahead[0].final_pts - me_row.final_pts) if ahead else 0,
            next_name=ahead[0].name if ahead else None,
            to_leader=js_round(leader.final_pts - me_row.final_pts),
            leader_name=leader.name,
            move_name=move.name if move else None,
            move_gain=js_round(move.ros - worst) if move else None,
        )

    schedule: list[S.H2hFixture] = []
    if is_h2h:
        upcoming = session.scalars(
            select(M.Matchup)
            .where(M.Matchup.sport == "fpl", M.Matchup.finished.is_(False), M.Matchup.round >= next_gw)
            .order_by(M.Matchup.round)
            .limit(10)
        )

        def proj_gw(mg: A.Manager | None, gi: int) -> float:
            if mg is None:
                return 0.0
            return sum(p.gw_xpts(gi) for p in A.best_xi(mg.players, lambda p: p.gw_xpts(gi)).xi)

        for m in upcoming:
            gi = m.round - next_gw
            hm, am = by_entry.get(m.home_entry), by_entry.get(m.away_entry)
            hp, ap = proj_gw(hm, gi), proj_gw(am, gi)
            lean = "toss-up" if abs(hp - ap) < 4 else m.home_name if hp > ap else m.away_name
            schedule.append(S.H2hFixture(
                gw=m.round, home=m.home_name, away=m.away_name, home_proj=hp, away_proj=ap,
                mine=bool((hm and hm.is_mine) or (am and am.is_mine)), lean=lean,
            ))
    return S.FplStandingsResponse(
        is_h2h=is_h2h, gws_left=gws_left, simulated=odds is not None, rows=rows, path=path,
        schedule=schedule,
    )


# ---- trades ------------------------------------------------------------------------------------


def trade_lab(session: Session, horizon: str) -> S.FplTradeLab:
    b = load_board(session)
    managers = b.managers()
    me = next((m for m in managers if m.is_mine), None)
    rivals = [m for m in managers if not m.is_mine]
    owners = {m.entry_id: (m.name, {p.ext_id for p in m.players}) for m in rivals}
    ideas = A.trade_ideas(me.players, b.players, owners, 4, horizon) if me else []
    return S.FplTradeLab(
        horizon=horizon,  # type: ignore[arg-type]
        me=_manager_out(me) if me else None,
        rivals=[_manager_out(m) for m in rivals],
        suggestions=[
            S.FplTradeIdea(rival_name=t.rival_name, give=outs(t.give), get=outs(t.get),
                        my_gain=t.my_gain, their_gain=t.their_gain)
            for t in ideas
        ],
    )


def evaluate_trade(session: Session, give: Sequence[str], get: Sequence[str]) -> S.FplTradeEvaluation:
    b = load_board(session)
    me = next((m for m in b.managers() if m.is_mine), None)
    ev = A.evaluate_trade(
        [b.by_id[x] for x in give if x in b.by_id],
        [b.by_id[x] for x in get if x in b.by_id],
        me.players if me else [],
    )
    return S.FplTradeEvaluation.model_validate(ev)
