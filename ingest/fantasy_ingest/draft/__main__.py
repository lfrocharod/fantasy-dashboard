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
    ]
    s = db.get_settings(keys)
    return {k.split(".")[-1]: v for k, v in s.items()}


def sync_picks(db: DB, env: Env, sport: str, cfg: dict) -> int:
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


def build_board(db: DB, sport: str, cfg: dict) -> None:
    if sport != "nfl":
        _log(f"{sport} adapter not implemented yet")
        return
    from . import nfl

    year = int(cfg.get("year") or 2026)
    scoring = cfg.get("scoring") or "ppr"
    roster = json.loads(cfg["roster"]) if cfg.get("roster") else dict(DEFAULT_ROSTER)
    teams = int(cfg.get("teams") or 12)
    _log(f"building {sport} board · {year} · {scoring} · {teams} teams · roster {roster}")
    rows = nfl.build(year, scoring, roster, teams)
    db.replace_draft_players(sport, rows)
    _log(f"wrote {len(rows)} players "
         f"({sum(1 for r in rows if r.ecr_rank)} matched to FantasyPros)")


def main() -> int:
    ap = argparse.ArgumentParser(prog="fantasy_ingest.draft")
    ap.add_argument("--sport", default="nfl", choices=("nfl", "nba", "fpl"))
    ap.add_argument("--sync", action="store_true", help="also pull live ESPN draft picks")
    ap.add_argument("--loop", type=int, default=0, help="repeat every N seconds (Ctrl-C to stop)")
    ap.add_argument("--board-only", action="store_true", help="skip pick sync even with --loop")
    args = ap.parse_args()

    env = Env.load()
    db = DB(env.database_url)

    # Board changes rarely; picks change fast. On first pass do both.
    build_board(db, args.sport, _cfg(db, args.sport))
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
