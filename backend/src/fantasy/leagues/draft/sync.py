"""FPL Draft + ESPN NFL sync: build the player board, then pull league state
(ownership, standings, schedule, your lineup, live scores).

    fantasy sync fpl | nfl                          # board + league sync
    fantasy draft-board --sport nfl --sync --loop 20  # draft night: poll ESPN picks
"""

from __future__ import annotations

import json

from fantasy.config import Docs, Env
from fantasy.core.db import DB
from fantasy.core.secretbox import decrypt
from fantasy.leagues.draft.types import DEFAULT_ROSTER


def _log(m: str) -> None:
    print(f"[draft] {m}", flush=True)


def config_for(db: DB, sport: str) -> dict:
    keys = [
        f"draft.{sport}.league_id", f"draft.{sport}.espn_s2", f"draft.{sport}.swid",
        f"draft.{sport}.my_team_id", f"draft.{sport}.teams", f"draft.{sport}.roster",
        f"draft.{sport}.scoring", f"draft.{sport}.year",
        # FPL Draft
        f"draft.{sport}.pl_profile", f"draft.{sport}.entry_id",
        f"draft.{sport}.role_overrides",
    ]
    s = db.get_settings(keys)
    return {k.split(".")[-1]: v for k, v in s.items()}


def _espn_cookies(cfg: dict, env: Env | None) -> tuple[str | None, str | None]:
    s2, swid = cfg.get("espn_s2"), cfg.get("swid")
    if not (s2 and swid):
        return None, None
    if env and env.web_crypto_key:
        try:
            return decrypt(s2), decrypt(swid)
        except Exception as e:  # noqa: BLE001
            _log(f"could not decrypt ESPN cookies: {e}")
            return None, None
    return s2, swid  # allow plaintext for local use


def sync_picks(db: DB, env: Env, sport: str, cfg: dict) -> int:
    if sport == "fpl":
        return _sync_fpl(db, env, cfg)

    if sport == "nfl":
        # in-season NFL: rosters + schedule + projections are all done inside
        # build_board when cookies are present, so there's nothing extra here
        # unless we're still pre-draft.
        from fantasy.leagues.nfl import espn_league

        s2, swid = _espn_cookies(cfg, env)
        lid = cfg.get("league_id")
        if not (s2 and swid and lid):
            _log("nfl sync skipped — set league_id + espn_s2 + swid in Settings")
            return 0
        year = int(cfg.get("year") or 2026)
        data = espn_league.fetch_league(year, lid, s2, swid)
        settings = espn_league.parse_settings(data)
        # detected league rules: settings feed the board build, the leagues row
        # feeds the UI
        db.set_setting("draft.nfl.roster", json.dumps(settings["roster"]))
        db.set_setting("draft.nfl.teams", str(settings["teams"]))
        db.set_setting("draft.nfl.scoring", settings["scoring"])
        db.upsert_league(
            "nfl", name=settings["name"] or "", scoring=settings["scoring"],
            roster=settings["roster"], n_teams=int(settings["teams"]),
        )
        # In-season, rosters come from mRoster (handled in build_board); the
        # draft_picks table isn't used.
        _log(f"nfl league synced · {settings['name']} · {settings['teams']} teams · {settings['scoring']}")
        return 0

    from fantasy.leagues.nfl import espn_league

    lid = cfg.get("league_id")
    s2, swid = cfg.get("espn_s2"), cfg.get("swid")
    if not (lid and s2 and swid and env.web_crypto_key):
        _log("league sync skipped — set league_id + espn_s2 + swid in Settings")
        return 0
    try:
        s2, swid = decrypt(s2), decrypt(swid)
    except Exception as e:  # noqa: BLE001
        _log(f"could not decrypt ESPN cookies: {e}")
        return 0
    year = int(cfg.get("year") or 2026)
    data = espn_league.fetch_league(year, lid, s2, swid)
    settings = espn_league.parse_settings(data)
    my_team = int(cfg["my_team_id"]) if cfg.get("my_team_id") else None
    picks = espn_league.parse_picks(data, my_team)
    db.replace_draft_picks(sport, picks)
    # persist detected roster rules so the board's VBD matches the real league
    db.set_setting(f"draft.{sport}.roster", json.dumps(settings["roster"]))
    db.set_setting(f"draft.{sport}.teams", str(settings["teams"]))
    db.set_setting(f"draft.{sport}.scoring", settings["scoring"])
    _log(f"synced {len(picks)} ESPN picks · {settings['name']} · "
         f"{settings['teams']} teams · {settings['scoring']} · roster {settings['roster']}")
    return len(picks)


def _sync_fpl(db: DB, env: Env, cfg: dict) -> int:
    from fantasy.leagues.fpl.league import (
        _client,
        fetch_my_squad,
        has_auth,
        league_details,
        parse_choices,
        parse_standings,
    )

    league_id = cfg.get("league_id")
    if not league_id:
        _log("fpl sync skipped — set draft.fpl.league_id in Settings")
        return 0
    auth = _fpl_cookie(cfg, env)
    authed = has_auth(auth)
    entry_id = cfg.get("entry_id")
    with _client(auth) as c:
        # draft.premierleague.com increasingly wants a live session cookie even
        # for the "public" league endpoints. A stale/expired token must NOT sink
        # the whole FPL refresh — the player board + projections already built
        # fine before this. Fall back to whatever's stored and carry on.
        try:
            det = league_details(c, league_id)
            standings = parse_standings(det)
        except Exception as e:  # noqa: BLE001
            _log(f"fpl standings: keeping stored ({type(e).__name__}) — re-paste your "
                 "x-api-authorization Bearer token in Settings if this persists")
            det = {}
            standings = []
        try:
            picks = parse_choices(c, league_id)
        except Exception as e:  # noqa: BLE001
            _log(f"fpl draft board: keeping stored ({type(e).__name__})")
            picks = []
        my_ids: list[int] = []
        my_lineup: list[dict] = []
        if entry_id:
            try:
                ev = _bootstrap_events(c)
                next_gw = ev.get("next") or ev.get("current") or 1
                my_lineup = fetch_my_squad(c, entry_id, next_gw, authed=authed, log=_log)
                my_ids = [p["element"] for p in my_lineup]
                if my_lineup:
                    src = my_lineup[0].get("source", "?")
                    _log(f"fpl lineup: {len(my_ids)} picks from {src}"
                         + ("" if authed else "  (no login token — paste your "
                            "x-api-authorization Bearer token in Settings to read "
                            "your live Pick Team, not last week's)"))
            except Exception as e:  # noqa: BLE001
                _log(f"fpl my-squad skipped: {e}")
    for p in picks:
        p["is_mine"] = str(p.get("team_id")) == str(entry_id)
    if picks:  # never wipe a good stored board with an auth-failed empty pull
        db.replace_draft_picks("fpl", picks, source="fpl")
    if standings:
        db.replace_league_entries("fpl", [
            {
                "entry_id": r.get("entry_id"), "name": r.get("name"),
                "is_mine": str(r.get("entry_id")) == str(entry_id),
                "rank": r.get("rank"), "total": r.get("total"),
                "points_for": r.get("points_for"), "points_against": r.get("points_against"),
                "wins": r.get("w"), "draws": r.get("d"), "losses": r.get("l"),
            }
            for r in standings
        ])
    # H2H schedule (which manager you face each gameweek)
    le_name = {}
    le_entry = {}
    for e in det.get("league_entries", []):
        nm = (e.get("entry_name")
              or f"{e.get('player_first_name','')} {e.get('player_last_name','')}".strip())
        le_name[e["id"]] = nm
        le_entry[e["id"]] = e.get("entry_id")
    sched = [{
        "event": m.get("event"),
        "home": le_name.get(m.get("league_entry_1"), ""),
        "away": le_name.get(m.get("league_entry_2"), ""),
        "home_entry": le_entry.get(m.get("league_entry_1")),
        "away_entry": le_entry.get(m.get("league_entry_2")),
        "home_pts": m.get("league_entry_1_points"),
        "away_pts": m.get("league_entry_2_points"),
        "finished": bool(m.get("finished")),
    } for m in det.get("matches", []) if m.get("event")]
    if sched:
        db.replace_matchups("fpl", [
            {
                "round": m["event"], "home_entry": m["home_entry"], "away_entry": m["away_entry"],
                "home_name": m["home"], "away_name": m["away"], "home_points": m["home_pts"],
                "away_points": m["away_pts"], "finished": m["finished"],
            }
            for m in sched
        ])
    if det.get("league", {}).get("scoring"):
        db.upsert_league("fpl", scoring=det["league"]["scoring"],
                         name=str(det["league"].get("name") or ""))
    if my_ids:
        src = my_lineup[0].get("source", "?") if my_lineup else ""
        # Draft has no captaincy: the API's captain/vice flags are vestigial.
        db.replace_my_lineup("fpl", [
            {"ext_id": p["element"], "position": p["slot"], "starter": p["starter"],
             "source": src}
            for p in my_lineup
        ])
    if det.get("league_entries"):
        n = len(det["league_entries"])
        db.set_setting("draft.fpl.teams", str(n))  # the board's VBD baseline
        db.upsert_league("fpl", n_teams=n)

    # Live gameweek: per-player points + your H2H matchup score while the current
    # GW is in progress. Cleared once it's over / unavailable. The web FPL page
    # turns this into the same secured / projected-finish / auto-sub view the CL
    # overview has.
    live = None
    try:
        cur_gw = (_bootstrap_events(c).get("current")) if entry_id else None
        if cur_gw and my_lineup:
            live = _fpl_live_score(c, int(cur_gw), my_lineup, det, entry_id)
    except Exception as e:  # noqa: BLE001
        _log(f"fpl live skipped: {e}")
    db.put_document(Docs.FPL_LIVE, live)
    if live:
        _log(f"fpl live: GW{live['gw']} {live['state']} — {live['secured']} pts banked, "
             f"{live['played']}/{live['starters']} started"
             + (f", vs {live['oppName']} {live['myPoints']}-{live['oppPoints']}"
                if live.get("oppName") else ""))

    _log(f"fpl: {len(picks)} draft picks · {len(standings)} standings rows · "
         f"{len(my_ids)} in your squad")
    return 0


def _fpl_live_score(c, gw: int, lineup: list[dict], det: dict,
                    entry_id) -> dict | None:  # pragma: no cover - network
    """Per-player live points for the user's squad this GW plus the H2H matchup
    score. Returns None if nobody has kicked off yet (caller clears the value)."""
    r = c.get(f"https://draft.premierleague.com/api/event/{gw}/live")
    r.raise_for_status()
    els = r.json().get("elements", {})
    items = els if isinstance(els, dict) else {str(e.get("id")): e for e in els}

    def stat(eid) -> tuple[int, int]:
        st = ((items.get(str(eid)) or {}).get("stats")) or {}
        return int(st.get("total_points") or 0), int(st.get("minutes") or 0)

    elements: dict[str, list[int]] = {}
    starters = [p for p in lineup if p.get("starter")]
    secured = played = 0
    any_minutes = False
    for p in lineup:
        pts, mins = stat(p["element"])
        elements[str(p["element"])] = [pts, mins]
        if p.get("starter"):
            secured += pts  # draft scores every starter once — no captain
            if mins > 0:
                played += 1
                any_minutes = True
    if not any_minutes:
        return None

    # H2H matchup score for this GW (live points update in league_details)
    le_entry = {e["id"]: e.get("entry_id") for e in det.get("league_entries", [])}
    le_name = {
        e["id"]: (e.get("entry_name")
                  or f"{e.get('player_first_name', '')} {e.get('player_last_name', '')}".strip())
        for e in det.get("league_entries", [])
    }
    my_pts = opp_pts = None
    opp_name = None
    finished = False
    for m in det.get("matches", []):
        if m.get("event") != gw:
            continue
        h, a = m.get("league_entry_1"), m.get("league_entry_2")
        if str(le_entry.get(h)) == str(entry_id):
            my_pts, opp_pts, opp_name = m.get("league_entry_1_points"), m.get("league_entry_2_points"), le_name.get(a)
        elif str(le_entry.get(a)) == str(entry_id):
            my_pts, opp_pts, opp_name = m.get("league_entry_2_points"), m.get("league_entry_1_points"), le_name.get(h)
        else:
            continue
        finished = bool(m.get("finished"))
        break

    return {
        "gw": gw, "state": "finished" if finished else "live",
        "secured": secured, "played": played, "starters": len(starters),
        "elements": elements,
        "myPoints": my_pts, "oppPoints": opp_pts, "oppName": opp_name,
    }


def _bootstrap_events(c) -> dict:
    from fantasy.leagues.fpl.board import bootstrap

    return bootstrap(c).get("events", {}) or {}


def build_board(db: DB, sport: str, cfg: dict, env: Env | None = None) -> None:
    if sport == "nfl":
        year = int(cfg.get("year") or 2026)
        scoring = cfg.get("scoring") or "ppr"
        s2, swid = _espn_cookies(cfg, env)
        lid = cfg.get("league_id")
        # In-season if we can reach the league; otherwise the pre-draft board.
        if s2 and swid and lid:
            from fantasy.leagues.nfl import season as nfl_season

            _log(f"building nfl IN-SEASON board · {year} · league {lid}")
            rows, meta = nfl_season.build(
                year, lid, s2, swid, scoring,
                int(cfg["my_team_id"]) if cfg.get("my_team_id") else None,
            )
            db.replace_draft_players(sport, rows)
            _store_nfl_league(db, meta, rows, cfg.get("my_team_id"))
            _log(f"wrote {len(rows)} players · week {meta['week']} · "
                 f"{len(meta['my_roster'])} on your roster · "
                 f"playoffs weeks {meta['playoff_weeks']} · seeding {meta['seeding_rule']}")
            return

        from fantasy.leagues.nfl import draft_board as nfl

        roster = json.loads(cfg["roster"]) if cfg.get("roster") else dict(DEFAULT_ROSTER)
        teams = int(cfg.get("teams") or 12)
        _log(f"building nfl DRAFT board · {year} · {scoring} · {teams} teams")
        rows = nfl.build(year, scoring, roster, teams)
        db.replace_draft_players(sport, rows)
        _log(f"wrote {len(rows)} players "
             f"({sum(1 for r in rows if r.ecr_rank)} matched to FantasyPros)")
        return

    if sport == "fpl":
        from fantasy.leagues.draft.types import FPL_ROSTER
        from fantasy.leagues.fpl.board import bootstrap, build

        data = bootstrap()
        next_gw = data.get("events", {}).get("next") or data.get("events", {}).get("current") or 1
        roster = json.loads(cfg["roster"]) if cfg.get("roster") else dict(FPL_ROSTER)
        teams = int(cfg.get("teams") or 8)
        league_id = cfg.get("league_id")
        cookie = _fpl_cookie(cfg, env)
        try:
            overrides = json.loads(cfg["role_overrides"]) if cfg.get("role_overrides") else {}
        except (ValueError, TypeError):
            overrides = {}
        _log(f"building fpl board · GW{next_gw} · {teams} teams · league {league_id or '—'}"
             + (f" · {len(overrides)} role overrides" if overrides else ""))
        rows = build(next_gw, roster, teams, league_id, cookie, role_overrides=overrides)
        db.replace_draft_players(sport, rows)
        db.upsert_league("fpl", current_round=int(next_gw))
        try:
            from fantasy.ml import serve
        except ImportError:  # the ml extra isn't installed here
            pass
        else:
            serve.run(db, data, int(next_gw), {r.ext_id: float(r.proj_points or 0) for r in rows},
                      say=lambda m: _log(f"ml: {m}"))
        owned = sum(1 for r in rows if not r.available)
        _log(f"wrote {len(rows)} players · {owned} owned in league · "
             f"{len(rows) - owned} free agents")
        return

    _log(f"{sport} adapter not implemented yet")


def _fpl_cookie(cfg: dict, env: Env | None) -> str | None:
    raw = cfg.get("pl_profile")
    if not raw:
        return None
    if env and env.web_crypto_key:
        try:
            return decrypt(raw)
        except Exception as e:  # noqa: BLE001
            _log(f"pl_profile decrypt failed, using as-is: {e}")
    return raw  # allow a plaintext cookie for local use


def _store_nfl_league(db: DB, meta: dict, rows: list, my_team_id: str | None) -> None:
    """In-season NFL league state from one ESPN pull."""
    db.upsert_league(
        "nfl",
        current_round=int(meta["week"]),
        regular_rounds=int(meta["reg_weeks"]),
        playoff_rounds=[int(w) for w in meta["playoff_weeks"]],
        playoff_teams=int(meta["playoff_teams"]),
        seeding_rule=meta["seeding_rule"],
        lineup_slots=meta["slots"],
        n_teams=len(meta["teams"]),
    )
    db.replace_league_entries("nfl", [
        {
            "entry_id": r["team_id"], "name": r["name"],
            "is_mine": str(r["team_id"]) == str(my_team_id or ""),
            "wins": r.get("wins"), "draws": r.get("ties"), "losses": r.get("losses"),
            "points_for": r.get("pf"), "points_against": r.get("pa"),
        }
        for r in meta["standings"]
    ])
    db.replace_matchups("nfl", [
        {
            "round": m["week"], "home_entry": m["home"], "away_entry": m["away"],
            "home_name": m.get("home_name"), "away_name": m.get("away_name"),
            "home_points": m.get("home_pts"), "away_points": m.get("away_pts"),
            "winner": m.get("winner"), "finished": m.get("winner") in ("HOME", "AWAY", "TIE"),
        }
        for m in meta["schedule"]
        if m.get("week") is not None
    ])
    slot_of = {str(r.ext_id): (r.raw or {}).get("slot", "") for r in rows}
    db.replace_my_lineup("nfl", [
        {"ext_id": x, "starter": slot_of.get(str(x), "") not in ("", "BE", "IR"),
         "source": "espn"}
        for x in meta["my_roster"]
    ])
