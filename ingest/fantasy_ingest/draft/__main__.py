"""Draft board ingestion.

    python -m fantasy_ingest.draft --sport nfl                  # rankings + VBD
    python -m fantasy_ingest.draft --sport nfl --sync           # + live ESPN picks
    python -m fantasy_ingest.draft --sport nfl --sync --loop 20 # poll every 20s during the draft
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from ..config import Env
from ..db import DB
from ..secretbox import decrypt
from .types import DEFAULT_ROSTER


def _log(m: str) -> None:
    print(f"[draft] {m}", flush=True)


def _cfg(db: DB, sport: str) -> dict:
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


def sync_picks(db: DB, env: Env, sport: str, cfg: dict) -> int:
    if sport == "fpl":
        return _sync_fpl(db, env, cfg)

    from . import espn_league

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
    from .fpl_league import (
        _client,
        fetch_my_squad,
        league_details,
        parse_choices,
        parse_standings,
    )

    league_id = cfg.get("league_id")
    if not league_id:
        _log("fpl sync skipped — set draft.fpl.league_id in Settings")
        return 0
    cookie = _fpl_cookie(cfg, env)
    entry_id = cfg.get("entry_id")
    with _client(cookie) as c:
        det = league_details(c, league_id)
        standings = parse_standings(det)
        picks = parse_choices(c, league_id)
        my_ids: list[int] = []
        if entry_id:
            try:
                ev = _bootstrap_events(c)
                gw = ev.get("current") or ev.get("next") or 1
                my_ids = [p["element"] for p in fetch_my_squad(c, entry_id, gw)]
            except Exception as e:  # noqa: BLE001
                _log(f"fpl my-squad skipped: {e}")
    for p in picks:
        p["is_mine"] = str(p.get("team_id")) == str(entry_id)
    db.replace_draft_picks("fpl", picks, source="fpl")
    db.set_setting("draft.fpl.standings", json.dumps(standings))
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
    db.set_setting("draft.fpl.schedule", json.dumps(sched))
    db.set_setting("draft.fpl.mode", det.get("league", {}).get("scoring", "c"))
    if my_ids:
        db.set_setting("draft.fpl.my_squad", json.dumps([str(i) for i in my_ids]))
    db.set_setting("draft.fpl.teams", str(len(det.get("league_entries", [])) or 8))
    _log(f"fpl: {len(picks)} draft picks · {len(standings)} standings rows · "
         f"{len(my_ids)} in your squad")
    return len(picks)


def _bootstrap_events(c) -> dict:
    from .fpl import bootstrap

    return bootstrap(c).get("events", {}) or {}


def build_board(db: DB, sport: str, cfg: dict, env: Env | None = None) -> None:
    if sport == "nfl":
        from . import nfl

        year = int(cfg.get("year") or 2026)
        scoring = cfg.get("scoring") or "ppr"
        roster = json.loads(cfg["roster"]) if cfg.get("roster") else dict(DEFAULT_ROSTER)
        teams = int(cfg.get("teams") or 12)
        _log(f"building nfl board · {year} · {scoring} · {teams} teams · roster {roster}")
        rows = nfl.build(year, scoring, roster, teams)
        db.replace_draft_players(sport, rows)
        _log(f"wrote {len(rows)} players "
             f"({sum(1 for r in rows if r.ecr_rank)} matched to FantasyPros)")
        return

    if sport == "fpl":
        from .fpl import bootstrap, build
        from .types import FPL_ROSTER

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


def main() -> int:
    ap = argparse.ArgumentParser(prog="fantasy_ingest.draft")
    ap.add_argument("--sport", default="nfl", choices=("nfl", "nba", "fpl"))
    ap.add_argument("--sync", action="store_true",
                    help="also pull league data (ESPN draft picks / FPL ownership + standings + your squad)")
    ap.add_argument("--loop", type=int, default=0, help="repeat every N seconds (Ctrl-C to stop)")
    ap.add_argument("--board-only", action="store_true", help="skip pick sync even with --loop")
    args = ap.parse_args()

    env = Env.load()
    db = DB(env.database_url)

    # Board changes rarely; picks change fast. On first pass do both.
    build_board(db, args.sport, _cfg(db, args.sport), env)
    if args.sync:
        sync_picks(db, env, args.sport, _cfg(db, args.sport))

    if args.loop:
        _log(f"looping every {args.loop}s — Ctrl-C to stop")
        try:
            while True:
                time.sleep(args.loop)
                if args.sync and not args.board_only:
                    sync_picks(db, env, args.sport, _cfg(db, args.sport))
        except KeyboardInterrupt:
            _log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
