"""Live-matchday state for the Champions League overview.

Once the first game of a matchday kicks off this turns the submitted squad into:

  * points **secured** so far (UEFA's `curGDPts` for players whose game is
    live/finished),
  * the **projected finish** — secured points plus xPts for the players still to
    play — after UEFA's *automatic* substitutions (a starter who ends the
    matchday with no appearance is replaced by the first eligible bench player).
    UCL Fantasy 2025/26 has **no vice-captain**, but the armband can be moved
    from day to day within the matchday — even off a captain who has already
    played (they revert to their base score, the new captain's still-to-come
    score is doubled). So the captain call stays live until there's no
    not-yet-kicked-off XI player left to move it to.
  * **manual-sub** levers that are still legal and worth pulling — between match
    days you may swap up to 4 not-yet-played starters for bench players whose
    teams are also still to play (a subbed-out player scores 0, so we only ever
    suggest moving one who hasn't kicked off). Any manual change — a sub or a
    new captain — switches UEFA's auto-subs off for the matchday (rules
    2026/27), so a lever has to beat what that gives up. None of this is
    possible on a matchday where every game kicks off together (MD8, the
    final).

Pure function of plain dataclasses; unit-tested in tests/test_live.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fantasy import MODEL_VERSION
from fantasy.leagues.ucl.types import Fixture, Player, Projection, SquadPick, Team, TeamSheet

# Starting-XI shape UEFA allows once the keeper is fixed.
_XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
_XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}

# Don't nag about a manual sub unless it clearly gains.
MANUAL_SUB_MIN_GAIN = 1.5
# Don't suggest moving the armband for a marginal xPts edge.
CAPTAIN_SWITCH_MIN_GAIN = 1.0
MAX_MANUAL_SUBS = 4
# UEFA scores a matchday hours after its final whistle (Player of the Match
# bonuses, its own total): its numbers count as the result after this long.
SETTLE_AFTER = timedelta(hours=8)

_LIVE = ("live", "finished")
_PENDING = ("upcoming", "none")


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _f1(x: float | None) -> str:
    """One-decimal string for prose (`6.4`, not `6.400000001`)."""
    return f"{float(x or 0):.1f}"


def _count(rows: list[dict]) -> dict[str, int]:
    c = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for r in rows:
        c[r["position"]] = c.get(r["position"], 0) + 1
    return c


def _formation_ok(counts: dict[str, int]) -> bool:
    if sum(counts.values()) != 11:
        return False
    return all(_XI_MIN[p] <= counts.get(p, 0) <= _XI_MAX[p] for p in _XI_MIN)


def matchday_settled(md_fixtures: list[Fixture], now: datetime | None = None) -> bool:
    """Every game over, and long enough ago that UEFA has scored the matchday."""
    if not md_fixtures or any(f.status != "finished" for f in md_fixtures):
        return False
    kos = [f.kickoff if f.kickoff.tzinfo else f.kickoff.replace(tzinfo=UTC)
           for f in md_fixtures if f.kickoff]
    return bool(kos) and (now or datetime.now(UTC)) - max(kos) >= SETTLE_AFTER


def _secured(r: dict) -> float:
    return float(r["actual"] or 0) if r["matchState"] in _LIVE else 0.0


def _projected(r: dict) -> float:
    if r["matchState"] == "finished":
        return float(r["actual"] or 0)
    if r["matchState"] == "live":
        # banked so far + the share of the pre-match xPts still to be earned,
        # by how much of the match is left. (A player 2 up at 20' keeps most
        # of the upside; one who's blanked to 80' keeps almost none.)
        left = max(0.0, 1.0 - min(90, r.get("minute") or 0) / 90.0)
        return float(r["actual"] or 0) + left * r["xpts"]
    return float(r["xpts"])


def _swap_ok(out_pos: str, in_pos: str, counts: dict[str, int]) -> dict[str, int] | None:
    """Formation after replacing an `out_pos` player with an `in_pos` one, or
    None if that would be illegal. A keeper can only be swapped for a keeper."""
    if (out_pos == "GK") != (in_pos == "GK"):
        return None
    trial = dict(counts)
    trial[out_pos] = trial.get(out_pos, 0) - 1
    trial[in_pos] = trial.get(in_pos, 0) + 1
    return trial if _formation_ok(trial) else None


def build_live_state(
    players: list[Player],
    teams: dict[int, Team],
    fixtures: list[Fixture],
    projections: list[Projection],
    picks: list[SquadPick],
    matchday: int,
    *,
    subs_allowed: int = 0,  # deprecated — CL Fantasy has no per-matchday sub cap
    confirmed: dict[int, str] | None = None,
    reprojected: list[Projection] | None = None,
    sheet: TeamSheet | None = None,
) -> dict | None:
    """Returns the live-state blob, or None if the matchday hasn't started (or we
    have no squad / fixtures for it). `projections` are the frozen pre-match
    ones; `confirmed` the published team sheets ({player: "start"|"bench"}) and
    `reprojected` this run's projections, which know them: a player still to
    play whose team sheet is out is valued with those. `sheet` is UEFA's own
    summary of the matchday: changes made in play (after which it makes no
    automatic subs) and, once it has scored the matchday, the result."""
    pmap = {p.uefa_player_id: p for p in players}
    proj = {pr.player_id: pr for pr in projections}
    confirmed = confirmed or {}
    fresh = {pr.player_id: pr for pr in reprojected or []}
    md_fx = [f for f in fixtures if f.matchday == matchday]
    if not md_fx or not picks:
        return None
    if not any(f.status in _LIVE for f in md_fx):
        return None  # nothing has kicked off yet
    # UEFA's result stands in for ours once it has had time to settle
    final = bool(sheet and sheet.points is not None and matchday_settled(md_fx))
    changed = bool(sheet and sheet.changed)

    days = sorted({f.kickoff.date() for f in md_fx if f.kickoff})
    day_of = {d: i + 1 for i, d in enumerate(days)}
    # In-play changes (manual subs, moving the armband) happen *between* match
    # days. When the whole matchday is one slot — MD8, the final — there is no
    # gap, so nothing can be changed once it's under way.
    in_play_open = len(days) > 1

    ctx: dict[int, dict] = {}
    for f in md_fx:
        h, a = teams.get(f.home_team_id), teams.get(f.away_team_id)
        d = day_of.get(f.kickoff.date(), 1) if f.kickoff else 1
        minute = 90 if f.status == "finished" else int(getattr(f, "live_minute", 0) or 0)
        if h:
            ctx[f.home_team_id] = {"status": f.status, "kickoff": _iso(f.kickoff), "minute": minute,
                                   "opp": a.name if a else "?", "home": True, "day": d}
        if a:
            ctx[f.away_team_id] = {"status": f.status, "kickoff": _iso(f.kickoff), "minute": minute,
                                   "opp": h.name if h else "?", "home": False, "day": d}

    def mk_row(pk: SquadPick) -> dict | None:
        p = pmap.get(pk.player_id)
        if not p:
            return None
        c = ctx.get(p.team_id)
        state = c["status"] if c else "none"
        pr = proj.get(pk.player_id)
        pre = round(pr.xpts, 1) if pr else 0.0
        if state in _PENDING and pk.player_id in confirmed and pk.player_id in fresh:
            pr = fresh[pk.player_id]
        xpts = round(pr.xpts, 1) if pr else 0.0
        actual = p.live_points if state in _LIVE else None
        if final and pk.points is not None:
            # UEFA's points (the captain's already doubled; the page doubles it)
            actual = pk.points / 2 if pk.is_captain else pk.points
        played = bool(p.live_played) or bool(pk.is_played)
        # Definitely didn't play: their game is over and they never featured.
        dnp = state == "finished" and not played and not actual
        return {
            "playerId": pk.player_id, "name": p.name, "position": p.position,
            "team": teams[p.team_id].name if p.team_id in teams else "",
            "opp": c["opp"] if c else None, "home": c["home"] if c else None,
            "mdDay": c["day"] if c else None, "kickoff": c["kickoff"] if c else None,
            "matchState": state, "played": played, "actual": actual, "xpts": xpts,
            "minute": c["minute"] if c else 0,
            "isStarter": pk.is_starter, "isCaptain": pk.is_captain, "isVice": pk.is_vice,
            "benchOrder": pk.bench_order, "dnp": dnp, "effRole": None,
            "confirmed": confirmed.get(pk.player_id), "_pre": pre,
        }

    rows = [r for pk in picks if (r := mk_row(pk))]
    by_id = {r["playerId"]: r for r in rows}
    starters = [r for r in rows if r["isStarter"]]
    bench = sorted((r for r in rows if not r["isStarter"]), key=lambda r: r["benchOrder"])

    # ---- UEFA automatic substitutions --------------------------------------
    xi_ids = {r["playerId"] for r in starters}
    counts = _count(starters)
    auto: list[dict] = []
    auto_pairs: list[tuple[dict, dict]] = []
    used: set[int] = set()
    # none at all once the team was changed in play: UEFA won't make them
    for s in [] if changed else sorted((r for r in starters if r["dnp"]), key=lambda r: -r["xpts"]):
        for b in bench:
            if b["playerId"] in used or b["dnp"]:
                continue
            trial = _swap_ok(s["position"], b["position"], counts)
            if trial is None:
                continue
            counts = trial
            xi_ids.discard(s["playerId"])
            xi_ids.add(b["playerId"])
            used.add(b["playerId"])
            s["effRole"], b["effRole"] = "auto-out", "auto-in"
            auto_pairs.append((s, b))
            auto.append({"outName": s["name"], "outPos": s["position"],
                         "inName": b["name"], "inPos": b["position"],
                         "reason": f"{s['name']} did not feature"})
            break

    # UEFA only auto-subs a team nobody touched during the matchday: one manual
    # sub or a new captain and the auto-subs are off. One that brings in a bench
    # player still to play can be redone by hand, for one of the 4 subs; the
    # points of a bench player who has already played can't — that's what any
    # manual change gives up.
    redo = [(s, b) for s, b in auto_pairs if b["matchState"] in _PENDING]
    lost = [(s, b) for s, b in auto_pairs if b["matchState"] not in _PENDING]
    manual_cost = round(sum(_projected(b) for _, b in lost), 1)
    redo_note = "; ".join(f"sub {s['name']} out for {b['name']} by hand" for s, b in redo)
    lost_note = ", ".join(f"{b['name']}'s {_projected(b):.0f}" for _, b in lost)

    # ---- captain ------------------------------------------------------
    # UCL Fantasy 2025/26 has NO vice-captain. You CAN move the armband from day
    # to day within a matchday — even away from a captain who has already played:
    # they revert to their base score and the new captain (whose team must still
    # be to play) is doubled instead. So the decision stays live as long as there
    # is a not-yet-kicked-off XI player to move it to. It closes only on a
    # single-slot matchday (MD8 / the final) where everything starts at once.
    cap = next((r for r in rows if r["isCaptain"]), None)
    vice = next((r for r in rows if r["isVice"]), None)  # shown as "(V)" only
    cap_eff, cap_note, cap_switch, cap_rec = cap, None, None, None
    cap_locked = True
    if cap:
        cap_played = cap["matchState"] in _LIVE
        cap_banked = float(cap["actual"] or 0) if cap_played else None
        # what the armband is worth right now if left alone: banked points once
        # the captain has featured, otherwise their projection.
        held = cap_banked if cap_played else cap["xpts"]

        alts = sorted(
            (r for r in starters
             if r["matchState"] in _PENDING and r["playerId"] != cap["playerId"]),
            key=lambda r: -r["xpts"],
        ) if in_play_open else []
        best_alt = alts[0] if alts else None
        cap_locked = best_alt is None

        gross = best_alt["xpts"] - held if best_alt else 0.0
        if best_alt and gross - manual_cost >= CAPTAIN_SWITCH_MIN_GAIN:
            gain = round(gross - manual_cost, 1)
            cap_switch = {
                "toPlayerId": best_alt["playerId"], "toName": best_alt["name"],
                "toXpts": best_alt["xpts"], "fromName": cap["name"],
                "fromXpts": round(held, 1), "gain": gain,
            }
            cap_rec = "switch"
            cap_note = (
                f"CHANGE the (C): {cap['name']} keeps {cap_banked:.0f} as base — "
                f"double {best_alt['name']} ({_f1(best_alt['xpts'])} proj) instead, +{gain}"
                if cap_played else
                f"CHANGE the (C): {cap['name']} ({_f1(cap['xpts'])}) → "
                f"{best_alt['name']} ({_f1(best_alt['xpts'])}) — +{gain} projected, "
                "neither has kicked off"
            )
            if auto_pairs:
                cap_note += (" — a new captain switches off UEFA's auto-subs"
                             + (f": {redo_note}" if redo else "")
                             + (f" (net of {lost_note} you give up)" if lost else ""))
        elif best_alt and gross >= CAPTAIN_SWITCH_MIN_GAIN:
            cap_rec = "keep"
            cap_note = (
                f"KEEP the (C) on {cap['name']} — moving it to {best_alt['name']} "
                f"(+{_f1(gross)}) would switch off UEFA's auto-subs and give up {lost_note}"
            )
        elif best_alt:
            cap_rec = "keep"
            if cap_played:
                cap_note = (
                    f"KEEP the (C) on {cap['name']} — {cap_banked:.0f} banked (×2 = "
                    f"{cap_banked * 2:.0f}) already beats {best_alt['name']}'s "
                    f"{_f1(best_alt['xpts'])} projection"
                )
            else:
                edge = f", {_f1(cap['xpts'] - best_alt['xpts'])} clear of {best_alt['name']}"
                cap_note = f"KEEP the (C) on {cap['name']} — still your top projection{edge}"
        elif not in_play_open and cap["matchState"] in _PENDING:
            cap_rec = "locked"
            cap_note = (
                f"(C) on {cap['name']} is locked — every game kicks off together, so "
                "the armband can't be moved once the matchday is under way"
            )
        elif cap["dnp"]:
            cap_eff, cap_rec = None, "locked"
            cap_note = (
                f"{cap['name']} didn't feature and no one's left to move the armband to "
                "— no captain double this matchday"
            )
        else:
            cap_rec = "locked"
            top = max(starters, key=lambda r: r["xpts"], default=None)
            hind = (
                f" (model's top pick was {top['name']})"
                if top and top["playerId"] != cap["playerId"]
                and top["xpts"] - cap["xpts"] >= CAPTAIN_SWITCH_MIN_GAIN else ""
            )
            cap_note = f"{cap['name']}: {(cap['actual'] or 0) * 2} pts (×2), locked in{hind}"

    # ---- points --------------------------------------------------------
    eff_xi = [by_id[i] for i in xi_ids]
    secured_pts = sum(_secured(r) for r in eff_xi)
    proj_pts = sum(_projected(r) for r in eff_xi)
    if cap_eff and cap_eff["playerId"] in xi_ids:
        secured_pts += _secured(cap_eff)
        proj_pts += _projected(cap_eff)
    if final and sheet and sheet.points is not None:
        secured_pts = proj_pts = float(sheet.points)  # UEFA's own result
    pre_match = sum(r["_pre"] for r in starters) + (cap["_pre"] if cap else 0.0)

    # ---- manual-sub levers still worth pulling ------------------------
    # Between match days you may sub out up to 4 starters *whose team hasn't
    # played yet* for bench players whose team also hasn't played. A subbed-out
    # player scores 0, so there's never a reason to move one who has featured —
    # UEFA's auto-subs cover the players who end the matchday on 0 minutes, but
    # only if nothing was changed by hand: the subs worth making have to beat
    # what's lost, and the auto-subs that can be redone are listed first.
    # Nothing can be moved on a single-slot matchday (MD8, the final).
    manual: list[dict] = []
    subs_left = MAX_MANUAL_SUBS - (sheet.in_play_subs if sheet else 0)
    if in_play_open:
        auto_in = {b["playerId"] for _, b in auto_pairs}
        pend_starters = sorted(
            (by_id[i] for i in xi_ids
             if by_id[i]["matchState"] in _PENDING and i not in auto_in),
            key=lambda r: r["xpts"],  # weakest projected first
        )
        avail_bench = sorted(
            (b for b in bench if b["playerId"] not in used and b["matchState"] in _PENDING),
            key=lambda b: -b["xpts"],
        )
        m_counts = _count(eff_xi)
        taken: set[int] = set()
        for s in pend_starters:
            if len(manual) >= subs_left - len(redo):
                break
            for b in avail_bench:
                if b["playerId"] in taken or b["xpts"] - s["xpts"] < MANUAL_SUB_MIN_GAIN:
                    continue
                trial = _swap_ok(s["position"], b["position"], m_counts)
                if trial is None:
                    continue
                m_counts = trial
                taken.add(b["playerId"])
                manual.append({"outName": s["name"], "outPos": s["position"],
                               "outActual": None, "outXpts": round(s["xpts"], 1),
                               "inName": b["name"], "inPos": b["position"],
                               "inXpts": b["xpts"], "gain": round(b["xpts"] - s["xpts"], 1)})
                break
        if manual and sum(m["gain"] for m in manual) - manual_cost < MANUAL_SUB_MIN_GAIN:
            manual = []  # not worth switching UEFA's auto-subs off
        elif manual and redo:
            manual = [
                {"outName": s["name"], "outPos": s["position"], "outActual": 0.0, "outXpts": 0.0,
                 "inName": b["name"], "inPos": b["position"], "inXpts": b["xpts"],
                 "gain": round(b["xpts"], 1),
                 "reason": "redoes UEFA's auto-sub, which a manual change switches off"}
                for s, b in redo
            ] + manual

    for r in rows:
        if r["effRole"] is None:
            r["effRole"] = "start" if r["isStarter"] else "bench"
        del r["_pre"]

    all_done = all(f.status == "finished" for f in md_fx)
    return {
        "matchday": matchday,
        "generatedAt": datetime.now(UTC).isoformat(),
        "modelVersion": MODEL_VERSION,
        "state": "finished" if all_done else "live",
        "starters": len(starters),
        "played": sum(1 for r in starters if r["played"]),
        "toPlay": sum(1 for r in eff_xi if r["matchState"] in _PENDING),
        "securedPoints": round(secured_pts, 1),
        "projectedFinish": round(proj_pts, 1),
        "preMatchProjection": round(pre_match, 1),
        "benchSlots": len(bench),
        # up to 4 sub-outs are allowed between match days; false once the whole
        # matchday is a single kickoff slot (MD8, the final) — nothing can move.
        "inPlayOpen": in_play_open,
        "maxManualSubs": MAX_MANUAL_SUBS,
        # UEFA's own: subs made in play (they switch its auto-subs off), and the
        # result once it has scored the matchday
        "inPlaySubs": sheet.in_play_subs if sheet else 0,
        "autoSubsOff": changed,
        "official": float(sheet.points) if final and sheet and sheet.points is not None else None,
        "fixtures": [
            {"matchId": f.uefa_match_id,
             "home": teams[f.home_team_id].name if f.home_team_id in teams else "?",
             "away": teams[f.away_team_id].name if f.away_team_id in teams else "?",
             "homeGoals": f.home_goals, "awayGoals": f.away_goals,
             "status": f.status, "kickoff": _iso(f.kickoff)}
            for f in sorted(md_fx, key=lambda f: f.kickoff or datetime.max.replace(tzinfo=UTC))
        ],
        "squad": rows,
        "autoSubs": auto,
        "manualSubs": manual,
        "captain": None if not cap else {
            "playerId": cap["playerId"], "name": cap["name"], "actual": cap["actual"],
            "matchState": cap["matchState"], "xpts": cap["xpts"], "locked": cap_locked,
            "effectivePlayerId": cap_eff["playerId"] if cap_eff else None,
            "effectiveName": cap_eff["name"] if cap_eff else None,
            "viceName": vice["name"] if vice else None,
            "switch": cap_switch, "note": cap_note,
            # "keep" | "switch" | "locked" — the stick-or-move verdict.
            "recommendation": cap_rec,
        },
    }


# ---------------------------------------------------------------------------
# Live rival scoring — the same secured / projected-finish split for every
# mini-league squad, so the overview can say "you're +6 live vs the leader".


def _norm_squad(raw) -> tuple[list[int], int | None, set[int]]:
    """A saved squad is [{id,c,s,b}, …]; older rows are a bare list[int]."""
    if not isinstance(raw, list) or not raw:
        return [], None, set()
    if isinstance(raw[0], (int, float)):
        return [int(x) for x in raw], None, set()
    ids = [int(x["id"]) for x in raw if isinstance(x, dict) and "id" in x]
    cap = next((int(x["id"]) for x in raw if isinstance(x, dict) and x.get("c")), None)
    starters = {int(x["id"]) for x in raw if isinstance(x, dict) and x.get("s")}
    return ids, cap, starters


def _squad_extras(raw) -> tuple[dict[int, int], dict[int, float], bool]:
    """(bench order, UEFA's points per player where it has them, changed in
    play) from a saved squad; empty for older rows that don't carry them."""
    rows = [x for x in raw if isinstance(x, dict) and "id" in x] if isinstance(raw, list) else []
    bench = {int(x["id"]): int(x.get("b") or 0) for x in rows if not x.get("s")}
    points = {int(x["id"]): float(x["p"]) for x in rows if x.get("p") is not None}
    return bench, points, any(x.get("m") for x in rows)


def _has_points(sc: tuple[int, bool, bool] | None) -> bool:
    return bool(sc and (sc[2] or sc[0] or sc[1]))


def build_live_rivals(
    standings: list,
    my_entry_id: str | None,
    players: list[Player],
    teams: dict[int, Team],
    projections: list[Projection],
    scores: dict[int, tuple[int, bool, bool]],
    matchday: int,
    *,
    my_live: dict | None = None,
    settled: bool = False,
) -> dict | None:
    """`standings`: LeagueEntry rows (each with `.squad`). `scores`: player_id ->
    (points, played, final). `my_live`: the full `build_live_state` result, so the
    "mine" row uses the same numbers the overview shows. A rival is scored from
    their XI and captain, with UEFA's automatic subs unless they changed their
    team in play; once the matchday has `settled`, from UEFA's own points.
    Returns {ready, matchday, rows, …}."""
    proj = {pr.player_id: pr for pr in projections}
    pmap = {p.uefa_player_id: p for p in players}
    with_sq = [e for e in standings if _norm_squad(getattr(e, "squad", None))[0]]
    if not with_sq:
        return None

    def val(pid: int) -> float:
        sc = scores.get(pid)
        if _has_points(sc):
            return float(sc[0])
        pr = proj.get(pid)
        return pr.xpts if pr else 0.0

    def dnp(pid: int) -> bool:
        sc = scores.get(pid)
        return bool(sc and sc[2] and not sc[1] and not sc[0])  # over, never on

    def auto_subbed(xi: list[int], bench: dict[int, int]) -> list[int]:
        """UEFA's automatic subs: each starter who didn't feature makes way for
        the first bench player, in bench order, who keeps the formation legal."""
        xi = list(xi)
        counts = _count([{"position": pmap[p].position} for p in xi])
        used: set[int] = set()
        for out in [p for p in xi if dnp(p)]:
            for b in sorted((b for b in bench if b in pmap), key=lambda b: bench[b]):
                if b in used or dnp(b):
                    continue
                trial = _swap_ok(pmap[out].position, pmap[b].position, counts)
                if trial is None:
                    continue
                counts = trial
                xi[xi.index(out)] = b
                used.add(b)
                break
        return xi

    def score_one(ids: list[int], cap_id: int | None, starter_ids: set[int], raw):
        known = [p for p in ids if p in pmap]
        bench, uefa_pts, changed = _squad_extras(raw)
        if len(starter_ids) >= 11:
            xi = [p for p in known if p in starter_ids]
            if settled and all(p in uefa_pts for p in xi):
                # UEFA's own points: the captain's already doubled
                total = round(sum(uefa_pts[p] for p in xi), 1)
                return total, total, sum(1 for p in xi if _has_points(scores.get(p))), True
            if not changed:
                xi = auto_subbed(xi, bench)
        else:
            xi = sorted(known, key=lambda p: -val(p))[:11]
        secured = sum(scores.get(p, (0, 0, 0))[0] for p in xi)
        projected = sum(val(p) for p in xi)
        # no vice-captain: a known captain out of the XI doubles nobody; with
        # none known (older rows) the best scorer stands in
        capp = (cap_id if cap_id in xi else None) if cap_id is not None else (
            max(xi, key=val) if xi else None)
        if capp is not None:
            secured += scores.get(capp, (0, 0, 0))[0] if _has_points(scores.get(capp)) else 0
            projected += val(capp)
        played = sum(1 for p in xi if _has_points(scores.get(p)))
        return round(secured, 1), round(projected, 1), played, False

    rows = []
    for e in sorted(with_sq, key=lambda e: e.rank or 999):
        ids, cap_id, starters = _norm_squad(e.squad)
        sec, prj, played, official = score_one(ids, cap_id, starters, e.squad)
        mine = e.entry_id == my_entry_id
        if mine and my_live:
            sec = my_live.get("securedPoints", sec)
            prj = my_live.get("projectedFinish", prj)
            played = my_live.get("played", played)
            official = my_live.get("official") is not None
        rows.append({
            "entryId": e.entry_id, "managerName": e.manager_name,
            "teamName": e.team_name, "rank": e.rank, "totalPoints": e.total_points,
            "mine": mine, "secured": sec, "projected": prj, "played": played,
            "official": official,
        })
    me = next((r for r in rows if r["mine"]), None)
    if me:
        for r in rows:
            r["liveGapVsMe"] = round(r["projected"] - me["projected"], 1)
    rows.sort(key=lambda r: -r["projected"])
    return {"ready": True, "matchday": matchday, "myEntryId": my_entry_id, "rows": rows}
