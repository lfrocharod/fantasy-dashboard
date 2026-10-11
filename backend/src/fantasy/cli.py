"""`fantasy` — one entry point for every job, locally, on the home runner and in
the Cloud Run job image.

    fantasy sync ucl [--mode fast|full|live] [--if-live]   # Champions League
    fantasy sync fpl | nfl                                 # board + league sync
    fantasy sync all [--mode fast|full]                    # every league
    fantasy draft-board --sport nfl --sync --loop 15       # draft-night pick tracker
    fantasy calibrate [--matchday N] [--played-only]       # grade the UCL model
    fantasy db upgrade | current | stamp REV               # Alembic migrations
    fantasy serve [--port 8000] [--reload]                 # the API (+ built SPA)

Configuration comes from the environment, falling back to $FANTASY_ENV_FILE or
./.env (see .env.example). A league that fails is logged and the others still
run; the exit code is non-zero if anything failed.
"""

from __future__ import annotations

import argparse
import functools
import os
import sys
import time
import traceback
from collections.abc import Callable

from fantasy.config import load_env_file

LEAGUES = ("ucl", "fpl", "nfl")


def _log(msg: str) -> None:
    print(f"[fantasy] {msg}", flush=True)


# ---- sync ---------------------------------------------------------------------


def _sync_ucl(args: argparse.Namespace) -> int:
    from fantasy.leagues.ucl import live_window, pipeline

    mode = args.mode
    if args.if_live and not live_window.should_run_live():
        # Nothing in play: exit before touching the network or the database.
        return 0
    ns = argparse.Namespace(
        matchday=args.matchday,
        skip_sources=mode != "full",
        live=mode == "live",
        samples=args.samples,
        dry_run=args.dry_run,
    )
    return pipeline.run(ns)


def _sync_draft(sport: str, args: argparse.Namespace) -> int:
    from fantasy.config import Env
    from fantasy.core.db import DB
    from fantasy.leagues.draft import sync

    env = Env.load()
    db = DB(env.database_url)
    try:
        sync.build_board(db, sport, sync.config_for(db, sport), env)
        if not getattr(args, "board_only", False):
            sync.sync_picks(db, env, sport, sync.config_for(db, sport))
    finally:
        db.close()
    return 0


def _run_isolated(label: str, fn: Callable[[], int]) -> bool:
    _log(f"── {label} " + "─" * max(4, 60 - len(label)))
    started = time.monotonic()
    try:
        rc = fn()
    except Exception:  # noqa: BLE001 - one league failing must not stop the rest
        traceback.print_exc()
        rc = 1
    took = time.monotonic() - started
    _log(f"   {'✓' if rc == 0 else '✗'} {label} ({took:.0f}s)")
    return rc == 0


def cmd_sync(args: argparse.Namespace) -> int:
    if args.league == "all":
        wanted = [x.strip() for x in os.environ.get("FANTASY_LEAGUES", ",".join(LEAGUES)).split(",")]
        failed: list[str] = []
        for lg in (x for x in LEAGUES if x in wanted):
            if lg == "ucl":
                ok = _run_isolated("Champions League", functools.partial(_sync_ucl, args))
            else:
                ok = _run_isolated(lg.upper(), functools.partial(_sync_draft, lg, args))
            if not ok:
                failed.append(lg)
        if failed:
            _log(f"done, with failures: {', '.join(failed)}")
            return 1
        _log("done — all leagues refreshed")
        return 0
    if args.league == "ucl":
        return _sync_ucl(args)
    return _sync_draft(args.league, args)


# ---- other commands -------------------------------------------------------------


def cmd_draft_board(args: argparse.Namespace) -> int:
    from fantasy.config import Env
    from fantasy.core.db import DB
    from fantasy.leagues.draft import sync

    env = Env.load()
    db = DB(env.database_url)
    sync.build_board(db, args.sport, sync.config_for(db, args.sport), env)
    if args.sync:
        sync.sync_picks(db, env, args.sport, sync.config_for(db, args.sport))
    if args.loop:
        _log(f"looping every {args.loop}s — Ctrl-C to stop")
        try:
            while True:
                time.sleep(args.loop)
                if args.sync:
                    sync.sync_picks(db, env, args.sport, sync.config_for(db, args.sport))
        except KeyboardInterrupt:
            _log("stopped")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    from fantasy.config import Env
    from fantasy.core.db import DB
    from fantasy.leagues.ucl import calibrate

    db = DB(Env.load().database_url)
    print(calibrate.report(calibrate.fetch_rows(db, args.matchday, args.played_only)))
    return 0


def cmd_db(args: argparse.Namespace) -> int:
    from fantasy.core import migrations

    if args.action == "upgrade":
        migrations.upgrade(args.revision or "head")
    elif args.action == "current":
        migrations.current()
    elif args.action == "stamp":
        if not args.revision:
            raise SystemExit("stamp needs a revision")
        migrations.stamp(args.revision)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    if args.action == "record":
        from fantasy.demo.record import record

        print(record())
    else:
        from fantasy.demo.seed import seed

        seed()
        _log("demo data seeded")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "fantasy.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


# ---- parser ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fantasy", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--env-file", help="KEY=VALUE file to load (default: $FANTASY_ENV_FILE or ./.env)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync", help="pull a league's data, rebuild projections, write the database")
    s.add_argument("league", choices=(*LEAGUES, "all"))
    s.add_argument(
        "--mode",
        choices=("fast", "full", "live"),
        default="fast",
        help="UCL only — fast: feeds + projections (~1 min); full: + the recent-form "
        "scrape; live: matchday refresh (~15 s)",
    )
    s.add_argument(
        "--if-live",
        action="store_true",
        help="UCL only — exit immediately unless a match is in play (for a frequent timer)",
    )
    s.add_argument("--matchday", type=int, default=None, help="UCL only — force a matchday")
    s.add_argument("--samples", default=None, help="UCL only — read feeds from a samples dir")
    s.add_argument("--dry-run", action="store_true", help="UCL only — no database writes")
    s.add_argument("--board-only", action="store_true", help="FPL/NFL only — skip the league sync")
    s.set_defaults(func=cmd_sync)

    d = sub.add_parser("draft-board", help="draft-night board + live pick sync")
    d.add_argument("--sport", choices=("nfl", "fpl"), default="nfl")
    d.add_argument("--sync", action="store_true")
    d.add_argument("--loop", type=int, default=0, help="repeat the pick sync every N seconds")
    d.set_defaults(func=cmd_draft_board)

    c = sub.add_parser("calibrate", help="grade UCL projections against real matchday points")
    c.add_argument("--matchday", type=int, default=None)
    c.add_argument("--played-only", action="store_true")
    c.set_defaults(func=cmd_calibrate)

    m = sub.add_parser("db", help="database migrations (Alembic)")
    m.add_argument("action", choices=("upgrade", "current", "stamp"))
    m.add_argument("revision", nargs="?", default=None)
    m.set_defaults(func=cmd_db)

    dm = sub.add_parser("demo", help="the public demo dataset")
    dm.add_argument("action", choices=("record", "seed"),
                    help="record: refresh the public snapshots; seed: build the demo database "
                    "(WIPES league data in $DATABASE_URL)")
    dm.set_defaults(func=cmd_demo)

    v = sub.add_parser("serve", help="run the API")
    v.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    v.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    v.add_argument("--reload", action="store_true")
    v.set_defaults(func=cmd_serve)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env_file(args.env_file)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
