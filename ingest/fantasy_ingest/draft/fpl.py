"""FPL Draft board + multi-gameweek rotation planner.

All data from the official APIs (no scraping):
  * draft.premierleague.com/api/bootstrap-static — players, draft scoring,
    set-piece order, injury news, season xG/xA, DEFCON counts, FPL's own
    pre-season draft_rank (used as an expected-role prior).
  * draft.premierleague.com/api/event/{gw}/live — real per-GW minutes, so we
    know who is *actually* starting now (catches new signings the season
    totals haven't caught up with).
  * fantasy.premierleague.com/api/fixtures/ — the full 380-match schedule with
    official FDR (same team ids), for a horizon of gameweeks.

Playing time is modelled from: recent-GW minutes, season minutes, the
draft_rank role prior, and a depth-chart bump when the player ahead of them is
injured/doubtful. Optional per-player overrides via the `draft.fpl.role_overrides`
setting ({"<id or web_name>": 0.0-1.0}).
"""

from __future__ import annotations

import math

import httpx

from .types import FPL_CLUB_STRENGTH, FPL_POS, FPL_ROSTER, DraftRow

_DRAFT = "https://draft.premierleague.com/api"
_CLASSIC = "https://fantasy.premierleague.com/api"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"

HORIZON = 6
LEAGUE_AVG_GOALS = 1.42
SOT_PER_XG = 3.0

_SCORING = {
    "goals_scored_GKP": 10, "goals_scored_DEF": 6, "goals_scored_MID": 5, "goals_scored_FWD": 4,
    "assists": 3,
    "clean_sheets_GKP": 4, "clean_sheets_DEF": 4, "clean_sheets_MID": 1, "clean_sheets_FWD": 0,
    "goals_conceded_GKP": -1, "goals_conceded_DEF": -1, "goals_conceded_MID": 0, "goals_conceded_FWD": 0,
    "concede_limit": 2, "saves": 1, "saves_limit": 3,
    "defensive_contribution_DEF": 2, "defensive_contribution_MID": 2, "defensive_contribution_FWD": 2,
    "defensive_contribution_limit_DEF": 10, "defensive_contribution_limit_MID": 12,
    "defensive_contribution_limit_FWD": 12,
    "yellow_cards": -1, "bonus": 1, "long_play": 2, "short_play": 1,
}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": _UA}, timeout=30, follow_redirects=True)


def bootstrap(client: httpx.Client | None = None) -> dict:  # pragma: no cover - network
    c = client or _client()
    try:
        r = c.get(f"{_DRAFT}/bootstrap-static")
        r.raise_for_status()
        return r.json()
    finally:
        if client is None:
            c.close()


def fixtures_by_gw(client: httpx.Client) -> dict[int, list[dict]]:  # pragma: no cover - network
    r = client.get(f"{_CLASSIC}/fixtures/")
    r.raise_for_status()
    out: dict[int, list[dict]] = {}
    for f in r.json():
        if f.get("finished") or not f.get("event"):
            continue
        out.setdefault(int(f["event"]), []).append({
            "h": f["team_h"], "a": f["team_a"],
            "h_fdr": f.get("team_h_difficulty"), "a_fdr": f.get("team_a_difficulty"),
        })
    return out


def recent_minutes(client: httpx.Client, upto_gw: int, n: int = 3) -> dict[int, list[int]]:  # pragma: no cover - network
    """{element_id: [minutes in each of the last up-to-`n` completed GWs]}."""
    out: dict[int, list[int]] = {}
    for gw in range(max(1, upto_gw - n), upto_gw):
        try:
            r = client.get(f"{_DRAFT}/event/{gw}/live")
            r.raise_for_status()
            els = r.json().get("elements", {})
        except Exception:  # noqa: BLE001,S112
            continue
        items = els.items() if isinstance(els, dict) else ((str(e.get("id")), e) for e in els)
        for eid, e in items:
            m = ((e or {}).get("stats") or {}).get("minutes", 0)
            out.setdefault(int(eid), []).append(int(m or 0))
    return out


def _num(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _rank_pstart(rank) -> float:
    """FPL's own draft_rank as an expected-role prior: an elite asset starts
    even with thin season minutes; a deep-squad name doesn't, whatever a cameo
    suggests."""
    r = _num(rank, 9999)
    if r <= 1:
        return 0.92
    for hi, p in ((25, 0.88), (60, 0.80), (110, 0.68), (170, 0.55), (250, 0.42), (360, 0.28)):
        if r <= hi:
            return p
    return 0.14


def _avail(el: dict, assume_fit: bool) -> float:
    if assume_fit:
        return 1.0
    status = el.get("status", "a")
    if status in ("i", "s", "u", "n"):
        return 0.0
    chance = el.get("chance_of_playing_next_round")
    if chance is not None:
        return _num(chance) / 100.0
    return 0.55 if status == "d" else 1.0


def _depth_bump(el: dict, siblings: list[dict]) -> float:
    """Extra start probability when a higher-ranked same-position team-mate is
    injured/doubtful (their minutes come to you)."""
    my_rank = _num(el.get("draft_rank"), 9999)
    bump = 0.0
    for s in siblings:
        if s["id"] == el["id"]:
            continue
        if _num(s.get("draft_rank"), 9999) >= my_rank:
            continue  # only players ahead of me in the pecking order
        out_prob = 1.0 - _avail(s, False)
        if out_prob > 0.15:
            bump += 0.14 * out_prob
    return min(0.30, bump)


def _p_start(el: dict, games: int, recent: list[int], depth_bump: float,
             override: float | None, assume_fit: bool) -> tuple[float, float]:
    avail = _avail(el, assume_fit)
    if override is not None:
        base = override
    else:
        if avail <= 0:
            return 0.0, 0.0
        starts = _num(el.get("starts"))
        mins = _num(el.get("minutes"))
        season = 0.7 * min(1.0, starts / max(1, games)) + 0.3 * min(1.0, mins / (max(1, games) * 90.0))
        if recent:
            rec = 0.8 * (sum(1 for m in recent if m >= 60) / len(recent)) + \
                  0.2 * min(1.0, sum(recent) / (len(recent) * 90.0))
        else:
            rec = season
        rank = _rank_pstart(el.get("draft_rank"))
        base = 0.50 * rec + 0.22 * season + 0.28 * rank
        # Thin sample (new signing, came back from injury, hasn't debuted): the
        # season/recent minutes say ~0 but that's not "benched", it's "no data".
        # Fall back to FPL's own expected-role ranking.
        if mins < 200 and sum(recent) < 120:
            base = max(base, rank - 0.05)
        base = min(base, rank + 0.22)       # can't be "nailed" on a fluke cameo
        base += depth_bump
    p_start = max(0.0, min(0.98, base)) * (1.0 if assume_fit else max(0.0, avail))
    p_any = min(0.99, p_start + 0.14 * (1 - p_start))
    return round(p_start, 3), round(p_any, 3)


def _set_piece(el: dict) -> str:
    t = ""
    if el.get("penalties_order") == 1:
        t += "P"
    if el.get("direct_freekicks_order") == 1:
        t += "F"
    if el.get("corners_and_indirect_freekicks_order") == 1:
        t += "C"
    return t


def _team_factor(code: str | None) -> tuple[float, float]:
    return FPL_CLUB_STRENGTH.get(code or "", (1.0, 1.0))


def _gw_projection(
    el: dict, pos: str, sc: dict, own_code: str, opp_code: str, is_home: bool,
    p_start: float, p_any: float,
) -> tuple[float, float, dict]:
    """(xpts, clean_sheet_prob, components) for one player in one fixture."""
    if p_any <= 0:
        opp_atk, own_def = _team_factor(opp_code)[0], _team_factor(own_code)[1]
        conc = max(0.05, LEAGUE_AVG_GOALS * opp_atk * own_def)
        return 0.0, round(math.exp(-conc), 3), {}
    xmins = p_start * 80 + (p_any - p_start) * 24
    mf = xmins / 90.0

    _own_atk, own_def = _team_factor(own_code)
    opp_atk, opp_def = _team_factor(opp_code)
    ha = 1.12 if is_home else 1.0 / 1.12

    mins = max(1.0, _num(el.get("minutes")))
    # per-90 rates from a tiny sample are noise — shrink toward a position
    # default in proportion to minutes played.
    conf = min(1.0, mins / 320.0)
    dflt_xg = {"FWD": 0.34, "MID": 0.18, "DEF": 0.05, "GKP": 0.0}[pos]
    dflt_xa = {"FWD": 0.14, "MID": 0.16, "DEF": 0.06, "GKP": 0.0}[pos]
    xg90 = min(1.2, _num(el.get("expected_goals")) / (mins / 90.0)) * conf + (1 - conf) * dflt_xg
    xa90 = min(0.9, _num(el.get("expected_assists")) / (mins / 90.0)) * conf + (1 - conf) * dflt_xa
    if "P" in _set_piece(el):
        xg90 += 0.12 * 0.79
    off_factor = max(0.35, opp_def * ha)
    exp_g = xg90 * mf * off_factor
    exp_a = xa90 * mf * off_factor
    g_pts = exp_g * sc[f"goals_scored_{pos}"]
    a_pts = exp_a * sc["assists"]

    app_pts = p_any * sc["short_play"] + p_start * 0.86 * (sc["long_play"] - sc["short_play"])

    conc = max(0.05, LEAGUE_AVG_GOALS * opp_atk * own_def * (1.0 / ha))
    cs_prob = math.exp(-conc)
    p60 = p_start * 0.86
    cs_pts = p60 * cs_prob * sc[f"clean_sheets_{pos}"]
    conc_pts = 0.0
    if sc[f"goals_conceded_{pos}"]:
        conc_pts = p60 * (conc / sc["concede_limit"]) * sc[f"goals_conceded_{pos}"]

    save_pts = 0.0
    if pos == "GKP":
        opp_sot = conc * SOT_PER_XG
        save_pts = mf * (max(0.0, opp_sot - conc) / sc["saves_limit"]) * sc["saves"]

    dc_pts = 0.0
    limit = sc.get(f"defensive_contribution_limit_{pos}", 0)
    dc_award = sc.get(f"defensive_contribution_{pos}", 0)
    if limit and dc_award:
        dc90 = min(limit * 1.6, _num(el.get("defensive_contribution")) / (mins / 90.0)) * conf
        p_hit = max(0.0, min(0.9, (dc90 - limit * 0.55) / (limit * 0.55)))
        dc_pts = mf * p_hit * dc_award

    bps90 = min(38.0, _num(el.get("bps")) / (mins / 90.0)) * conf
    bonus_pts = mf * max(0.0, (bps90 - 20) / 12.0)
    disc_pts = p_any * sc["yellow_cards"] * 0.16

    total = g_pts + a_pts + app_pts + cs_pts + conc_pts + save_pts + dc_pts + bonus_pts + disc_pts
    comp = {
        "goals": round(g_pts, 2), "assists": round(a_pts, 2), "appearance": round(app_pts, 2),
        "clean_sheet": round(cs_pts, 2), "conceded": round(conc_pts, 2), "saves": round(save_pts, 2),
        "defcon": round(dc_pts, 2), "bonus": round(bonus_pts, 2), "discipline": round(disc_pts, 2),
        "xmins": round(xmins, 0),
    }
    return max(0.0, total), round(cs_prob, 3), comp


def _fdr_from_strength(opp_code: str, is_home: bool) -> int:
    atk, dfn = _team_factor(opp_code)
    raw = 0.55 * (atk - 1) + 0.55 * (1 - dfn) + (-0.35 if is_home else 0.35)
    return max(1, min(5, round(3 + 2.2 * raw)))


def _rank_output(rank, pos: str) -> float:
    """Rough expected points/90 by FPL draft_rank — a fallback for players with
    too few minutes for a real rate (new signings, injury returnees)."""
    r = _num(rank, 9999)
    tier = (6.0 if r <= 8 else 5.2 if r <= 20 else 4.6 if r <= 45
            else 4.0 if r <= 90 else 3.4 if r <= 160 else 2.8 if r <= 280 else 2.2)
    return tier * (0.82 if pos in ("GKP", "DEF") else 1.0)


def _anchor(el: dict, pos: str, ppg: float, frm: float, opp_code: str, is_home: bool,
            p_start: float) -> float:
    """Season scoring-rate fallback. For GK/DEF the raw ppg is a poor early-season
    signal (clean sheets haven't accrued), so weight it lightly — the structural
    model already values a strong defence. For MID/FWD, ppg+form carry the
    attacking output the model can under-rate. When there's barely a sample,
    fall back to an expected output from FPL's own draft ranking."""
    _atk, opp_def = _team_factor(opp_code)
    fix_mult = 0.80 + 0.28 * max(0.35, opp_def * (1.12 if is_home else 1 / 1.12))
    rot = 0.28 + 0.72 * p_start
    base = (0.6 * ppg + 0.4 * frm) * fix_mult * rot
    if pos in ("GKP", "DEF"):
        base *= 0.7
    if _num(el.get("minutes")) < 200:
        base = max(base, _rank_output(el.get("draft_rank"), pos) * rot * (0.85 + 0.15 * fix_mult))
    return base


def _w_model(pos: str, mins_seen: float) -> float:
    """How much to trust the structural xPts model vs the season-rate anchor."""
    if pos in ("GKP", "DEF"):
        return 0.68  # two-sided clean-sheet model is the right tool here
    return 0.35 + 0.45 * (1.0 - min(1.0, mins_seen / 450.0))


def _blend_gw(el, pos, sc, own_code, oc, ish, ps, pa, ppg, frm, wm):
    """One fixture: structural model blended with the season-rate anchor."""
    model, cs, cmp = _gw_projection(el, pos, sc, own_code, oc, ish, ps, pa)
    anchor = _anchor(el, pos, ppg, frm, oc, ish, ps)
    x = wm * model + (1 - wm) * anchor if anchor > 0 else model
    return round(x, 2), cs, cmp


def build(next_gw: int, roster: dict[str, int], teams: int, league_id: str | None,
          cookie: str | None, horizon: int = HORIZON,
          role_overrides: dict | None = None) -> list[DraftRow]:  # pragma: no cover - network
    role_overrides = role_overrides or {}
    with _client() as c:
        data = bootstrap(c)
        fx = fixtures_by_gw(c)
        cur_gw = data.get("events", {}).get("current") or (next_gw - 1)
        rec = recent_minutes(c, cur_gw + 1)
        ownership: dict[int, int] = {}
        owner_names: dict[int, str] = {}
        if league_id:
            from . import fpl_league

            try:
                ownership, owner_names = fpl_league.fetch_ownership(c, league_id, cookie)
            except Exception as e:  # noqa: BLE001
                print(f"[draft] fpl ownership skipped: {e}", flush=True)

    sc = dict(_SCORING)
    sc.update({k: v for k, v in (data.get("settings", {}).get("scoring", {}) or {}).items()
               if k in _SCORING})
    club = {t["id"]: t["short_name"] for t in data["teams"]}
    games = max(1, (data.get("events", {}).get("current") or next_gw) - 1)
    gw_list = list(range(next_gw, next_gw + horizon))

    # depth charts: {(team, element_type): [elements]}
    depth: dict[tuple, list] = {}
    for el in data["elements"]:
        depth.setdefault((el["team"], el["element_type"]), []).append(el)

    def _override_for(el: dict) -> float | None:
        v = role_overrides.get(str(el["id"])) or role_overrides.get(el.get("web_name", ""))
        if v is None:
            return None
        if isinstance(v, str):
            return {"start": 0.85, "bench": 0.15, "out": 0.0}.get(v.lower())
        return max(0.0, min(1.0, float(v)))

    rows: list[DraftRow] = []
    for el in data["elements"]:
        pos = FPL_POS.get(el["element_type"], "MID")
        own_code = club.get(el["team"], "")
        ppg = _num(el.get("points_per_game"))
        frm = _num(el.get("form"))
        mins_seen = _num(el.get("minutes"))
        r_mins = rec.get(el["id"], [])
        bump = _depth_bump(el, depth.get((el["team"], el["element_type"]), []))
        ovr = _override_for(el)

        p_start, p_any = _p_start(el, games, r_mins, bump, ovr, assume_fit=False)
        fit_ps, fit_pa = _p_start(el, games, r_mins, bump, ovr, assume_fit=True)
        wm = _w_model(pos, mins_seen)

        gws, fit_gws = [], []
        for gw in gw_list:
            fixtures = [f for f in fx.get(gw, []) if el["team"] in (f["h"], f["a"])]
            if not fixtures:
                gws.append({"gw": gw, "opp": "", "home": None, "fdr": 0, "xpts": 0.0, "cs": 0.0})
                fit_gws.append(0.0)
                continue
            gx = fx_x = gcs = 0.0
            opps = []
            off_fdr = 3
            for f in fixtures:
                ish = f["h"] == el["team"]
                oc = club.get(f["a"] if ish else f["h"], "")
                x, cs, _c = _blend_gw(el, pos, sc, own_code, oc, ish, p_start, p_any, ppg, frm, wm)
                fxx, _fcs, _fc = _blend_gw(el, pos, sc, own_code, oc, ish, fit_ps, fit_pa, ppg, frm, wm)
                gx += x
                fx_x += fxx
                gcs = max(gcs, cs)
                off_fdr = (f["h_fdr"] if ish else f["a_fdr"]) or _fdr_from_strength(oc, ish)
                opps.append(f"{oc} ({'H' if ish else 'A'})")
            gws.append({"gw": gw, "opp": " + ".join(opps),
                        "home": fixtures[0]["h"] == el["team"], "fdr": off_fdr,
                        "xpts": round(gx, 2), "cs": gcs})
            fit_gws.append(round(fx_x, 2))

        next_x = gws[0]["xpts"] if gws else 0.0
        horizon_x = round(sum(g["xpts"] for g in gws), 2)
        fit_next = fit_gws[0] if fit_gws else next_x
        fit_horizon = round(sum(fit_gws), 2)

        # rest-of-season: every remaining GW (lightweight — just sum xpts)
        ros_x = 0.0
        ros_gws = 0
        for gw in sorted(g for g in fx if g >= next_gw):
            fixtures = [f for f in fx.get(gw, []) if el["team"] in (f["h"], f["a"])]
            if not fixtures:
                continue
            ros_gws += 1
            for f in fixtures:
                ish = f["h"] == el["team"]
                oc = club.get(f["a"] if ish else f["h"], "")
                gx, _cs, _c = _blend_gw(el, pos, sc, own_code, oc, ish,
                                        p_start, p_any, ppg, frm, wm)
                ros_x += gx
        ros_x = round(ros_x, 1)

        # yellow-card / suspension watch. PL milestones are every 5 bookings
        # (5 -> 1-game ban, 10 -> 2, ...). Bookings until the next milestone:
        yc = int(_num(el.get("yellow_cards")))
        yc_to_ban = 5 - (yc % 5)
        yc90 = round(_num(el.get("yellow_cards")) / max(1.0, mins_seen / 90.0), 2)

        comp: dict = {}
        cs0 = gws[0]["cs"] if gws else 0.0
        first = next((f for f in fx.get(next_gw, []) if el["team"] in (f["h"], f["a"])), None)
        if first:
            ish = first["h"] == el["team"]
            oc = club.get(first["a"] if ish else first["h"], "")
            _m, cs0, comp = _gw_projection(el, pos, sc, own_code, oc, ish, p_start, p_any)

        unavailable = el.get("status", "a") in ("i", "s", "u", "n") or (
            el.get("chance_of_playing_next_round") is not None
            and _num(el.get("chance_of_playing_next_round")) < 75
        )
        owner = ownership.get(el["id"], 0)
        rows.append(DraftRow(
            sport="fpl", ext_id=str(el["id"]),
            name=el.get("web_name") or f"{el.get('first_name','')} {el.get('second_name','')}".strip(),
            team=own_code, positions=[pos], primary_pos=pos,
            proj_points=round(next_x, 2),
            adp=_num(el.get("draft_rank")) or 9999,
            provider_rank=el.get("draft_rank"),
            injury_status=el.get("status", "a"),
            outlook=el.get("news") or "",
            owner=str(owner) if owner else "",
            owner_name=owner_names.get(owner, "") if owner else "",
            available=not owner,
            set_piece=_set_piece(el),
            next_opp=gws[0]["opp"] if gws else "",
            next_fdr=int(gws[0]["fdr"]) if gws else 0,
            form=frm, minutes=int(mins_seen),
            raw={
                "gws": gws, "horizon_xpts": horizon_x, "cs_prob": round(cs0, 3),
                "components": comp,
                "fit_next": fit_next, "fit_horizon": fit_horizon, "unavailable": bool(unavailable),
                "ros_xpts": ros_x, "ros_gws": ros_gws,
                "ros_ppg": round(ros_x / ros_gws, 2) if ros_gws else 0.0,
                "yellows": yc, "yc_to_ban": yc_to_ban, "yc90": yc90,
                "susp_risk": yc_to_ban <= 1,
                "p_start": round(p_start, 2), "depth_bump": round(bump, 2),
                "ppg": ppg, "total_points": el.get("total_points"),
                "ict": _num(el.get("ict_index")),
                "xgi90": round(_num(el.get("expected_goal_involvements")) /
                               max(1.0, mins_seen / 90.0), 2),
            },
        ))

    _compute_vbd(rows, roster or FPL_ROSTER, teams)
    rows.sort(key=lambda r: (-(r.raw or {}).get("horizon_xpts", 0), -(r.proj_points or 0)))
    return rows


def _compute_vbd(rows: list[DraftRow], roster: dict[str, int], teams: int) -> None:
    by_pos: dict[str, list[DraftRow]] = {}
    for r in rows:
        by_pos.setdefault(r.primary_pos, []).append(r)
    for pos, lst in by_pos.items():
        lst.sort(key=lambda r: -(r.raw or {}).get("horizon_xpts", 0))
        demand = max(1, round(roster.get(pos, 3) * teams * 0.7))
        idx = max(0, min(len(lst) - 1, demand - 1))
        repl = (lst[idx].raw or {}).get("horizon_xpts", 0.0) if lst else 0.0
        for r in lst:
            r.vbd = round((r.raw or {}).get("horizon_xpts", 0.0) - repl, 2)
