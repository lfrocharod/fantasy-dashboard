"""Orchestrator for one ingestion pass. Idempotent (all upserts are keyed) and
degrades: a failure fetching your squad or the external xG source doesn't stop
the public data + projections from being written.

    python -m fantasy_ingest.run                 # live
    python -m fantasy_ingest.run --skip-sources  # no FBref/Understat scrape
    python -m fantasy_ingest.run --samples ./samples --dry-run   # offline, no DB
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from . import MODEL_VERSION
from .config import Env, Keys
from .db import DB
from .model import club_strength, team_strength
from .model.optimizer import OptPlayer, optimise
from .model.params import ModelParams
from .model.projections import blank_projection, project_player
from .types import Fixture, Team
from .ucl import fetch
from .ucl.client import UefaAuthError, UefaClient


def _log(m: str) -> None:
    print(f"[ingest] {m}", flush=True)


class _DryDB:
    def get_settings(self, keys):
        return {}

    def load_my_squad(self, md):
        return []

    def load_player_stats(self):
        return {}

    def conn(self):
        raise RuntimeError("dry-run: no database")

    def __getattr__(self, name):
        return lambda *a, **k: None


def _load_samples(path: Path) -> dict:
    out = {}
    for name in ("players", "fixtures", "teams", "my_team", "league", "private_leagues", "form"):
        f = path / f"{name}.json"
        out[name] = json.loads(f.read_text()) if f.exists() else None
    return out


def _decrypt_token(db, env: Env) -> str | None:
    enc = db.get_settings([Keys.UEFA_TOKEN]).get(Keys.UEFA_TOKEN)
    if not enc or not env.web_crypto_key:
        return None
    try:
        from .secretbox import decrypt

        return decrypt(enc)
    except Exception as e:  # noqa: BLE001
        _log(f"could not decrypt stored UEFA token: {e}")
        return None


def run(args: argparse.Namespace) -> int:
    env = Env.load()
    # --live is a fast matchday refresh: no scraping, current MD only.
    if getattr(args, "live", False):
        args.skip_sources = True
    db = _DryDB() if args.dry_run else DB(env.database_url)
    run_id = db.start_run("start") if not args.dry_run else -1
    notes: list[str] = []
    ok = True

    try:
        cfg = db.get_settings(
            [Keys.MODEL_PARAMS, Keys.CURRENT_MATCHDAY, Keys.LEAGUE_ID,
             Keys.LEAGUE_CODE, Keys.ENTRY_ID]
        )
        params = ModelParams.load(cfg.get(Keys.MODEL_PARAMS))
        samples = _load_samples(Path(args.samples)) if args.samples else None
        token = None if samples else _decrypt_token(db, env)

        with UefaClient(token=token, bust_cache=getattr(args, "live", False)) as client:
            # ---- 1. public feeds -----------------------------------
            teams: dict[int, Team] = {}
            if samples:
                players, tp = fetch.parse_players(samples["players"] or {})
                fixtures, tf, md_info = fetch.parse_fixtures(samples["fixtures"] or {})
                tt = fetch.parse_teams(samples["teams"] or {})
                league_codes = []
            else:
                conf = client.get_config()
                league_codes = _league_codes(conf)
                tt = fetch.parse_teams(client.get_teams())
                fixtures, tf, md_info = fetch.parse_fixtures(client.get_fixtures())
                md_guess = _resolve_md(cfg, md_info, args.matchday)
                players, tp = fetch.parse_players(client.get_players(md_guess))

            for src in (tt, tf, tp):
                for tid, t in src.items():
                    teams.setdefault(tid, t)

            matchday = _resolve_md(cfg, md_info, args.matchday)
            _log(f"parsed {len(players)} players, {len(fixtures)} fixtures, "
                 f"{len(teams)} teams; matchday {matchday}")

            # Hand-edited set-piece overrides win over the computed guess.
            sp_over = db.load_set_piece_overrides() if not args.dry_run else {}
            if sp_over:
                by_id = {p.uefa_player_id: p for p in players}
                for pid, o in sp_over.items():
                    p = by_id.get(pid)
                    if not p:
                        continue
                    tags = []
                    if o.get("pen_rank") == 1:
                        tags.append("PK")
                    elif o.get("pen_rank") == 2:
                        tags.append("PK2")
                    if o.get("fk_rank") == 1:
                        tags.append("FK")
                    if o.get("ck_rank") == 1:
                        tags.append("CK")
                    p.set_piece = ",".join(tags)
                _log(f"applied {len(sp_over)} set-piece overrides")

            if not args.dry_run:
                db.upsert_teams(list(teams.values()))
                db.upsert_players(players)
                if fixtures:
                    db.upsert_fixtures(fixtures)
                _write_matchday_meta(db, md_info, matchday)
                if league_codes and not cfg.get(Keys.LEAGUE_CODE):
                    db.set_setting(Keys.LEAGUE_CODE, league_codes[0])

            # ---- 2. authed: squad + mini-league ------------------
            picks: list = []
            guid = cfg.get(Keys.ENTRY_ID) or ""
            if samples:
                picks = _private_from_samples(db, samples, matchday, args.dry_run)
            elif token and guid:
                picks = _private_live(
                    db, client, guid, matchday,
                    cfg.get(Keys.LEAGUE_ID), cfg.get(Keys.LEAGUE_CODE) or (league_codes[0] if league_codes else ""),
                    notes,
                )
            elif token and not guid:
                notes.append("token present but no entry/GUID set in Settings")
                _log(notes[-1])
            db.set_setting(Keys.UEFA_AUTH_STATE, client.auth_state)

            # ---- 3. external form (Understat) + xG/xA ----------
            stats = {}
            form_by_id: dict = {}
            if not args.skip_sources and not env.skip_sources:
                try:
                    stats = _sources(db, env, players, teams, args.dry_run)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"xG source failed: {e}")
                    _log(notes[-1])
                try:
                    # Sofascore per-league season xG — covers EVERY CL player,
                    # not just the big-5 that Understat sees. Overwrites the
                    # `combined` player_stats rows _sources wrote.
                    ss_stats = _season_xg_source(db, env, players, teams, args.dry_run)
                    if ss_stats:
                        stats = {**stats, **ss_stats}
                except Exception as e:  # noqa: BLE001
                    notes.append(f"season xG source failed: {e}")
                    _log(notes[-1])
                try:
                    form_by_id = _form_source(db, env, players, teams, args.dry_run)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"form source failed: {e}")
                    _log(notes[-1])
            elif samples and samples.get("form"):
                form_by_id = _form_from_sample(db, samples, players, teams, args.dry_run)
            if not stats:
                stats = db.load_player_stats() if not args.dry_run else {}
            if not form_by_id and not args.dry_run:
                form_by_id = db.load_player_form()

            # ---- 3b. confirmed XIs (matchday only) ------------
            # Once Sofascore marks a lineup `confirmed` (~1h pre-KO) it's ground
            # truth and overrides the model. Cheap (~40 calls) and only fires in
            # the matchday window, so it's safe to run even on --fast.
            confirmed_xi: dict[int, str] = {}
            if not args.dry_run and not getattr(args, "live", False):
                try:
                    confirmed_xi = _confirmed_xi(players, teams, fixtures, matchday)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"confirmed XI unavailable ({type(e).__name__})")
                    _log(notes[-1])

            # ---- 3c. live scoring overlay (matchday only) -----
            # The static players_/fixtures_ feeds lag: `curGDPts` stays 0 during
            # play and `matchStatus` sits at "1" long after FT. UEFA's dedicated
            # scoring feeds carry the truth — fold real points / minutes / FT
            # status onto the parsed objects so everything downstream (team
            # strength, projection freeze, live stage) sees reality.
            if not args.dry_run and any(
                f.status in ("live", "finished")
                for f in fixtures if f.matchday == matchday
            ):
                try:
                    _apply_live_scoring(client, players, fixtures, matchday)
                    db.upsert_fixtures([f for f in fixtures if f.matchday == matchday])
                except Exception as e:  # noqa: BLE001
                    notes.append(f"live scoring overlay skipped: {e}")
                    _log(notes[-1])

            # ---- 4. team strength -----------------------------
            # Start from static club priors (coefficients + squad quality), then
            # blend in whatever the finished UCL games say — weight grows with
            # the sample so by ~MD6 the live data dominates.
            observed = team_strength.ratings_from_fixtures(fixtures, teams.keys())
            played: dict[int, int] = {}
            for f in fixtures:
                if f.status == "finished":
                    played[f.home_team_id] = played.get(f.home_team_id, 0) + 1
                    played[f.away_team_id] = played.get(f.away_team_id, 0) + 1
            ratings = {
                tid: club_strength.blend_prior_observed(tid, observed.get(tid), played.get(tid, 0))
                for tid in teams
            }
            team_strength.apply_ratings(teams, ratings)
            if not args.dry_run:
                db.upsert_teams(list(teams.values()))

            # ---- 5. projections — every remaining league-phase matchday -----
            horizon = max(1, int(params.horizon))
            last_league_md = 8  # UCL league phase; knockouts (9+) projected once seeded
            if getattr(args, "live", False):
                plan_mds = [matchday]  # matchday refresh: current MD only
            else:
                plan_mds = [
                    md for md in sorted({f.matchday for f in fixtures if f.matchday >= matchday})
                    if md <= max(last_league_md, matchday + horizon - 1)
                ] or [matchday]
            # Freeze the current matchday's projections once its first game is
            # live — so start/sit xPts don't drift mid-match and the calibration
            # harness has the genuine pre-match numbers to grade.
            md_live_now = any(
                f.status in ("live", "finished") for f in fixtures if f.matchday == matchday
            )
            proj_by_md: dict[int, list] = {}
            for md in plan_mds:
                pr = _build_projections(
                    players, teams, fixtures, stats, md, params, form_by_id,
                    confirmed_xi if md == matchday else None,
                )
                proj_by_md[md] = pr
                if args.dry_run:
                    continue
                if md == matchday and md_live_now and db.has_projections(md):
                    proj_by_md[md] = db.load_projections(md)
                    _log(f"projections MD{md} frozen (matchday underway) — kept pre-match values")
                else:
                    db.replace_projections(md, pr, MODEL_VERSION)
            projections = proj_by_md[matchday]
            _log(f"built projections for MD {plan_mds} ({len(projections)} players each)")
            if args.dry_run:
                _print_top(projections, players)

            # ---- 6. optimizer + chips ------------------------
            opt = _optimizer(db, players, teams, proj_by_md, matchday, params, picks, form_by_id)
            if opt:
                if opt.get("preSeason"):
                    _log(f"optimizer: pre-season squad {opt['formation']} "
                         f"€{opt.get('totalCost')}m, {opt.get('changesFromCurrent', '?')} changes")
                else:
                    _log(f"optimizer: {opt['formation']}, {len(opt.get('transfers', []))} transfer idea(s)")
                    cap = (opt.get("captains") or {}).get("safePick")
                    if cap:
                        _log(f"  captain: {cap['name']} (EV {cap['ev']}, ceil {cap['ceiling']})")
                    rec = (opt.get("chips") or {}).get("recommend") or {}
                    for chip, info in rec.items():
                        if info:
                            _log(f"  chip {chip}: MD{info['matchday']} (+{info['gain']})")
                if not args.dry_run:
                    db.set_setting(Keys.OPTIMIZER_OUTPUT, json.dumps(opt))

            # ---- 7. live matchday state (CL overview) -------------------
            # Once a matchday game is live/finished: archive per-player actuals,
            # turn the submitted squad into secured + projected-finish points
            # after auto-subs, score every mini-league rival the same way, snap
            # a history row, and (opt-in) push an alert when something's
            # actionable.
            try:
                _live_stage(
                    db, args, client, players, teams, fixtures,
                    proj_by_md.get(matchday, []), picks, matchday,
                    cfg.get(Keys.LEAGUE_ID), cfg.get(Keys.ENTRY_ID), notes,
                )
            except Exception as e:  # noqa: BLE001
                notes.append(f"live stage skipped: {e}")
                _log(notes[-1])

            # ---- 8. grade the model against finished matchdays ---------
            if not args.dry_run:
                try:
                    from .calibrate import compute_and_store

                    cal = compute_and_store(db)
                    if cal:
                        o = cal["overall"]
                        _log(f"calibration: MAE {o['mae']:.2f} bias {o['me']:+.2f} "
                             f"band {o['band'] * 100:.0f}% over MD {cal['matchdays']}")
                except Exception as e:  # noqa: BLE001
                    notes.append(f"calibration skipped: {e}")

    except Exception as e:  # noqa: BLE001
        ok = False
        notes.append(f"FATAL: {e}")
        traceback.print_exc()
    finally:
        if not args.dry_run and run_id >= 0:
            db.finish_run(run_id, ok, "done" if ok else "error", " | ".join(notes))
    return 0 if ok else 1


# --------------------------------------------------------------------------


def _league_codes(conf: dict) -> list[str]:
    try:
        v = conf["data"]["value"].get("leagueCode") or []
        return [str(x).upper() for x in v if x]
    except (KeyError, TypeError, AttributeError):
        return []


def _int_setting(db, key: str, default: int) -> int:
    try:
        v = db.get_settings([key]).get(key)
        return int(v) if v not in (None, "") else default
    except (ValueError, TypeError):
        return default


def _apply_live_scoring(client, players, fixtures, matchday: int) -> None:
    """Overlay UEFA's live scoring feeds onto the already-parsed players +
    fixtures for `matchday`: real per-player fantasy points + minutes, and the
    true live/FT status + score (the static feeds lag by many minutes)."""
    import time as _t

    feed = None
    for attempt in range(3):
        try:
            feed = client.get_live_player_points()
            break
        except Exception as e:
            if attempt == 2:
                raise
            _log(f"live-players-points retry {attempt + 1} ({type(e).__name__})")
            _t.sleep(2 + attempt * 3)
    val = feed.get("data", feed) if isinstance(feed, dict) else feed
    val = val.get("value", val) if isinstance(val, dict) else val
    if not isinstance(val, dict):
        return
    pts = {int(k): int(v) for k, v in (val.get("totalPoints") or {}).items()}
    scores = val.get("scores") or {}

    md_fx = [f for f in fixtures if f.matchday == matchday]
    fx_by_id = {f.uefa_match_id: f for f in md_fx}
    _DONE = {"FT", "AET", "PEN", "AP", "FT_PEN"}
    touched: list[int] = []
    for mid_s, sc in scores.items():
        try:
            f = fx_by_id.get(int(mid_s))
        except (TypeError, ValueError):
            f = None
        if not f:
            continue
        phase = str(sc.get("phase") or "").upper()
        f.status = "finished" if phase in _DONE else "live"
        if f.status == "finished":
            f.live_minute = 90
        else:
            try:
                f.live_minute = int(str(sc.get("minuteString") or "0").split("+")[0]) or (
                    45 if phase in ("HT", "HALFTIME") else 0
                )
            except (TypeError, ValueError):
                f.live_minute = 0
        goals = {int(s["tId"]): s.get("gS") for s in sc.get("scoreLine") or [] if s.get("tId") is not None}
        if f.home_team_id in goals:
            f.home_goals = goals[f.home_team_id]
        if f.away_team_id in goals:
            f.away_goals = goals[f.away_team_id]
        touched.append(f.uefa_match_id)

    # per-match detail for minutes played (drives the "did not feature" flag)
    minutes: dict[int, int] = {}
    for mid in touched:
        try:
            mv = client.get_live_match(mid)
            mv = mv.get("data", mv) if isinstance(mv, dict) else mv
            mv = mv.get("value", mv) if isinstance(mv, dict) else mv
            for ps in (mv or {}).get("pStats") or []:
                pid = ps.get("pId")
                if pid is not None:
                    minutes[int(pid)] = int(ps.get("oF") or 0)
        except Exception:  # noqa: BLE001,S112
            continue

    started_clubs: set[int] = set()
    for f in md_fx:
        if f.status in ("live", "finished"):
            started_clubs |= {f.home_team_id, f.away_team_id}

    scored = 0
    for p in players:
        if p.team_id not in started_clubs:
            continue
        pid = p.uefa_player_id
        if pid in pts:
            p.live_points = pts[pid]
            scored += 1
        mins = minutes.get(pid)
        if mins is not None:
            p.live_played = mins > 0
        elif pid in pts and pts[pid] != 0:
            p.live_played = True
    n_ft = sum(1 for f in md_fx if f.status == "finished")
    _log(f"live scoring: {scored} players scored across {len(touched)} matches "
         f"({n_ft}/{len(md_fx)} MD{matchday} fixtures FT, {len(minutes)} minute records)")


def _recent_played_md(fixtures, current_md: int, grace_hours: float = 54.0) -> int | None:
    """The most recent matchday that has kicked off, if the current one hasn't —
    so a just-finished matchday's result stays on the overview until the next
    starts (then it clears). Bounded by a grace window off the last kickoff."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    cands = sorted(
        {f.matchday for f in fixtures
         if f.matchday < current_md and f.status in ("live", "finished")},
        reverse=True,
    )
    for md in cands:
        kos = [f.kickoff for f in fixtures if f.matchday == md and f.kickoff]
        if not kos:
            return md
        last = max(kos)
        last = last if last.tzinfo else last.replace(tzinfo=UTC)
        if now - last <= timedelta(hours=grace_hours):
            return md
    return None


def _live_stage(db, args, client, players, teams, fixtures, projections, picks, matchday,
                league_id, my_entry_id, notes) -> None:
    """Section 7: archive per-player actuals, build the live-state + live-rival
    blobs, snapshot history, and (opt-in) push an alert. No-op until a matchday
    game is live/finished; clears the blobs once the matchday is upcoming again."""
    from .model.live import build_live_rivals, build_live_state

    dry = args.dry_run
    md_fx = [f for f in fixtures if f.matchday == matchday]
    started = any(f.status in ("live", "finished") for f in md_fx)
    if not started:
        # Current matchday hasn't kicked off — keep the last played matchday's
        # result up until this one starts.
        prev = _recent_played_md(fixtures, matchday)
        if prev is None:
            if not dry:
                db.set_setting(Keys.LIVE_STATE, "")
                db.set_setting(Keys.LIVE_RIVALS, "")
            return
        _log(f"live: MD{matchday} not started — keeping MD{prev} result")
        matchday = prev
        md_fx = [f for f in fixtures if f.matchday == matchday]
        if not dry:
            try:
                _apply_live_scoring(client, players, fixtures, matchday)
                db.upsert_fixtures(md_fx)
            except Exception as e:  # noqa: BLE001
                notes.append(f"live scoring (fallback MD) skipped: {e}")
            projections = db.load_projections(matchday)

    # Fall back to the last archived actuals if this run's live-scoring overlay
    # didn't land (UEFA rate-limits the scoring feeds harder than the static
    # ones) — better slightly-stale points than a wall of zeros.
    if not dry:
        stored = db.load_player_scores(matchday)
        if stored:
            filled = 0
            for p in players:
                sc = stored.get(p.uefa_player_id)
                if sc and not p.live_points:
                    p.live_points, filled = sc[0], filled + 1
                    p.live_played = p.live_played or sc[1]
            if filled:
                _log(f"live: filled {filled} player points from the last archived run")

    # 7a. archive per-player actuals for every club that has kicked off
    live_clubs, final_clubs = set(), set()
    for f in md_fx:
        if f.status in ("live", "finished"):
            live_clubs |= {f.home_team_id, f.away_team_id}
        if f.status == "finished":
            final_clubs |= {f.home_team_id, f.away_team_id}
    score_rows = [
        (p.uefa_player_id, matchday, int(p.live_points or 0),
         bool(p.live_played), p.team_id in final_clubs)
        for p in players if p.team_id in live_clubs
    ]
    if score_rows and not dry:
        db.upsert_player_scores(score_rows)
    _log(f"live: archived {len(score_rows)} player scores for MD{matchday}")

    # 7b. my squad — secured / projected-finish after UEFA auto-subs
    live_picks = picks or (db.load_my_squad(matchday) if not dry else [])
    live = build_live_state(players, teams, fixtures, projections, live_picks, matchday)
    if live:
        _log(
            f"live: MD{matchday} {live['state']} — {live['securedPoints']} secured, "
            f"{live['projectedFinish']} projected ({live['played']}/{live['starters']} "
            f"played, {len(live['autoSubs'])} auto-sub, "
            f"{len(live['manualSubs'])} manual-sub idea)"
        )
    if not dry:
        db.set_setting(Keys.LIVE_STATE, json.dumps(live) if live else "")

    # 7c. score every mini-league rival the same way
    rivals = None
    if league_id and not dry:
        try:
            standings = db.load_league_standings(league_id, matchday)
            rivals = build_live_rivals(
                standings, my_entry_id, players, teams, projections,
                db.load_player_scores(matchday), matchday, my_live=live,
            )
        except Exception as e:  # noqa: BLE001
            notes.append(f"live rivals skipped: {e}")
        db.set_setting(Keys.LIVE_RIVALS, json.dumps(rivals) if rivals else "")
        if rivals:
            me = next((r for r in rivals["rows"] if r["mine"]), None)
            if me:
                ahead = sum(
                    1 for r in rivals["rows"]
                    if not r["mine"] and r["projected"] > me["projected"]
                )
                _log(f"live rivals: you project {me['projected']} — {ahead} ahead live")

    # 7d. snapshot the history row
    if live and not dry:
        try:
            db.insert_live_snapshot(
                matchday, live["securedPoints"], live["projectedFinish"],
                live["preMatchProjection"], live["state"], live,
            )
        except Exception as e:  # noqa: BLE001
            notes.append(f"live snapshot skipped: {e}")

    # 7e. opt-in push alert on still-actionable items
    if live and not dry:
        _maybe_alert(db, live)


def _maybe_alert(db, live: dict) -> None:
    import hashlib

    from .notify import notify

    bits = [
        f"SUB {s['outName']}→{s['inName']} (+{s['gain']})"
        for s in live.get("manualSubs", [])
    ]
    cap = live.get("captain") or {}
    if cap.get("recommendation") == "switch" and cap.get("switch"):
        sw = cap["switch"]
        bits.append(f"MOVE (C) {sw['fromName']}→{sw['toName']} (+{sw['gain']})")
    if not bits:
        return
    body = " · ".join(bits)
    digest = hashlib.sha1(body.encode()).hexdigest()[:16]
    if db.get_settings([Keys.LAST_ALERT_HASH]).get(Keys.LAST_ALERT_HASH) == digest:
        return
    if notify(f"CL MD{live['matchday']} — action needed", body):
        db.set_setting(Keys.LAST_ALERT_HASH, digest)
        _log(f"live: pushed alert — {body}")


def _resolve_md(cfg: dict, md_info, cli_md: int | None) -> int:
    if cli_md:
        return cli_md
    s = cfg.get(Keys.CURRENT_MATCHDAY, "")
    if s.isdigit():
        return int(s)
    return fetch.current_matchday(md_info)


def _write_matchday_meta(db, md_info, matchday: int) -> None:
    db.set_setting(Keys.CURRENT_MATCHDAY, str(matchday))
    for m in md_info:
        if m.matchday == matchday:
            if m.deadline:
                db.set_setting(Keys.DEADLINE, m.deadline.isoformat())
            db.set_setting(Keys.SUBS_ALLOWED, str(m.subs_allowed))
            db.set_setting(Keys.SUBS_CARRY, str(m.subs_carry))


def _private_from_samples(db, samples, matchday, dry):
    picks: list = []
    if samples.get("my_team"):
        picks, bank = fetch.parse_my_team(samples["my_team"], matchday)
        _log(f"sample squad: {len(picks)} picks, bank {bank}")
        if not dry and picks:
            db.replace_my_squad(matchday, picks)
            db.set_setting("ucl.bank", str(bank))
    if samples.get("league"):
        entries = fetch.parse_league_standings(samples["league"], matchday)
        _log(f"sample league: {len(entries)} entries")
        if not dry and entries:
            lid = db.get_settings([Keys.LEAGUE_ID]).get(Keys.LEAGUE_ID) or "sample"
            db.upsert_league_standings(lid, entries)
    return picks


def _private_live(db, client: UefaClient, guid, matchday, league_id, league_code, notes):
    picks: list = []
    state = client.check_auth(guid)
    _log(f"UEFA auth: {state}")
    if state != "authed":
        notes.append("UEFA session not valid — squad/league skipped (paste a fresh cookie)")
        return picks
    try:
        picks, bank = fetch.parse_my_team(client.get_my_team(guid, matchday), matchday)
        _log(f"my squad: {len(picks)} picks, bank {bank}")
        if picks:
            db.replace_my_squad(matchday, picks)
            db.set_setting("ucl.bank", str(bank))
    except (UefaAuthError, KeyError, ValueError) as e:
        notes.append(f"my_team failed: {e}")
        _log(notes[-1])

    if not league_id and league_code:
        try:
            leagues = fetch.parse_private_leagues(client.get_private_leagues(guid))
            match = next((L for L in leagues if L["code"] == league_code.upper()), None)
            if match:
                league_id = match["id"]
                db.set_setting(Keys.LEAGUE_ID, league_id)
                _log(f"resolved league {league_code} -> id {league_id}")
            else:
                notes.append(f"league code {league_code} not found among {[L['code'] for L in leagues]}")
        except (UefaAuthError, KeyError, ValueError) as e:
            notes.append(f"private leagues lookup failed: {e}")

    if league_id:
        try:
            entries = fetch.parse_league_standings(
                client.get_league_standings(league_id, matchday=matchday), matchday
            )
            _log(f"league {league_id}: {len(entries)} entries")
            if entries:
                _enrich_rival_squads(client, entries, matchday, my_guid=guid, notes=notes)
                db.upsert_league_standings(league_id, entries)
        except UefaAuthError as e:
            # -70/-40 here means the league has no completed matchday yet, not
            # that our session is bad (squad above already proved auth works).
            _log(f"league standings not available yet ({e}) — populates after MD1")
        except (KeyError, ValueError) as e:
            notes.append(f"league standings parse failed: {e}")
            _log(notes[-1])
    return picks


def _enrich_rival_squads(client: UefaClient, entries, matchday, *, my_guid, notes) -> None:
    """Pull each mini-league rival's saved squad (list of player ids) so the
    rival-tracking page can project their score. Best-effort per entry."""
    ok = 0
    for e in entries:
        if not e.entry_id or e.entry_id == my_guid:
            continue
        try:
            picks, _bank = fetch.parse_my_team(client.get_my_team(e.entry_id, matchday), matchday)
            # keep starter / captain / bench-order so the rival projection uses
            # their ACTUAL XI + captain, not our guess at their best 11.
            e.squad = [
                {"id": pk.player_id, "c": bool(pk.is_captain), "s": bool(pk.is_starter),
                 "b": int(pk.bench_order or 0)}
                for pk in picks
            ]
            if e.squad:
                ok += 1
        except (UefaAuthError, KeyError, ValueError) as ex:
            _log(f"  rival squad {e.manager_name or e.entry_id!r} failed: {ex}")
    _log(f"  rival squads: {ok}/{max(0, len(entries) - 1)} fetched")
    if ok == 0 and len(entries) > 1:
        notes.append("rival squads unavailable (pre-MD1 or endpoint blocked)")


def _sources(db, env: Env, players, teams, dry):
    """Legacy xG layer. FBref now blocks scrapers, so this is Understat season
    stats only, and best-effort — the real signal comes from _form_source."""
    from .mapping.player_match import build_stats
    from .sources.domestic_xg import fetch_understat_rows

    leagues = [x.strip() for x in env.source_leagues.split(",") if x.strip()]
    understat_leagues = [lg for lg in leagues if lg.split("-")[0] in ("ENG", "ESP", "GER", "ITA", "FRA")]
    understat_rows = fetch_understat_rows(understat_leagues, env.fbref_season)
    team_names = {tid: t.name for tid, t in teams.items()}
    report = build_stats(players, team_names, [], understat_rows, _overrides(db))
    _log(f"xG (Understat season): matched {len(report.matched)}/{len(players)}")
    if not dry and report.matched:
        db.upsert_player_stats(list(report.matched.values()))
    return report.matched


def _season_xg_source(db, env: Env, players, teams, dry):
    """Sofascore per-league season xG/xA — every CL player, all leagues (not
    just big-5). Writes `player_stats` scope='combined', overwriting Understat
    rows where both have a player. Best-effort. Also records name-match coverage
    (`ingest.xg_coverage`) so a missed star is visible on the Settings page."""
    import json

    from .sources.season_xg import fetch_season_xg

    team_names = {tid: t.name for tid, t in teams.items()}
    stats, cov = fetch_season_xg(
        players, team_names, min_price=env.recent_form_min_price,
        overrides=_overrides(db), log=_log,
    )
    if not dry:
        if stats:
            db.upsert_player_stats(list(stats.values()))
        if cov.total:
            db.set_setting(Keys.XG_COVERAGE, json.dumps(cov.as_dict()))
    return stats


def _overrides(db) -> dict[int, tuple[str, str]]:
    out: dict[int, tuple[str, str]] = {}
    try:
        with db.conn() as c:
            rows = c.execute(
                "select uefa_player_id, note from player_id_overrides where note like '%|%'"
            ).fetchall()
    except Exception:  # noqa: BLE001
        return out
    for pid, note in rows:
        name, _, tm = str(note).partition("|")
        out[int(pid)] = (name.strip(), tm.strip())
    return out


def _fdr(opp, is_home: bool) -> int:
    """1 (easiest) .. 5 (hardest) from opponent strength + home/away. Venue is a
    ~1/3-FDR-point nudge, not the ±0.77 the old ±0.35 gave it."""
    raw = 0.55 * (opp.attack_rating - 1) + 0.55 * (1 - opp.defence_rating) + (-0.15 if is_home else 0.15)
    return max(1, min(5, round(3 + 2.2 * raw)))


def _fixture_context(db, teams, matchday: int) -> dict[int, tuple[str, bool, int, int]]:
    """club_id -> (opponent name, is_home, fdr 1-5, day-of-matchday 1..N).

    UCL matchdays run over ~3 calendar days; the day index matters because you
    can still make bench changes after the early games kick off."""
    out: dict[int, tuple[str, bool, int, int]] = {}
    try:
        fixtures = [f for f in db.load_fixtures(matchday) if f.matchday == matchday]
    except Exception:  # noqa: BLE001
        return out
    days = sorted({f.kickoff.date() for f in fixtures if f.kickoff})
    day_of = {d: i + 1 for i, d in enumerate(days)}
    for f in fixtures:
        h, a = teams.get(f.home_team_id), teams.get(f.away_team_id)
        d = day_of.get(f.kickoff.date(), 1) if f.kickoff else 1
        if h and a:
            out[f.home_team_id] = (a.name, True, _fdr(a, True), d)
            out[f.away_team_id] = (h.name, False, _fdr(h, False), d)
    return out


def _confirmed_xi(players, teams, fixtures, matchday: int) -> dict[int, str]:
    """{uefa_player_id: "start"|"bench"} from Sofascore's confirmed lineups for
    the upcoming matchday. Empty outside the matchday window or if nothing is
    confirmed yet."""
    from .sources.confirmed_xi import fetch_confirmed_xi, within_matchday_window

    md_fx = [f for f in fixtures if f.matchday == matchday and f.status != "finished"]
    if not md_fx or not within_matchday_window(md_fx):
        return {}
    team_names = {tid: t.name for tid, t in teams.items()}
    got = fetch_confirmed_xi(md_fx, players, team_names, log=_log)
    if got:
        _log(f"confirmed XI: applied to {len(got)} players for MD{matchday}")
    return got


def _build_projections(players, teams, fixtures, stats, matchday, params, form_by_id=None,
                       confirmed_by_id=None):
    form_by_id = form_by_id or {}
    confirmed_by_id = confirmed_by_id or {}
    fx: dict[int, tuple[Fixture, bool]] = {}
    for f in fixtures:
        if f.matchday != matchday:
            continue
        fx[f.home_team_id] = (f, True)
        fx[f.away_team_id] = (f, False)

    out = []
    for p in players:
        slot = fx.get(p.team_id)
        team = teams.get(p.team_id)
        if not slot or not team:
            out.append(blank_projection(p, matchday))
            continue
        f, is_home = slot
        opp_id = f.away_team_id if is_home else f.home_team_id
        opp = teams.get(opp_id) or Team(uefa_team_id=opp_id, name=f"Team {opp_id}")
        out.append(project_player(
            p, stats.get(p.uefa_player_id), team, opp, is_home, matchday, params,
            form=form_by_id.get(p.uefa_player_id),
            confirmed=confirmed_by_id.get(p.uefa_player_id),
        ))
    return out


def _form_source(db, env: Env, players, teams, dry):
    """Recent-form for every CL player. The *recent window* is the player's last
    N matches **across all competitions** (Champions League + domestic league +
    domestic cups + super cups) — so it always reflects what a manager just saw,
    not a stale domestic-only slice.

      1. Sofascore — last-N-overall match logs (minutes / xG / xA / goals /
         rating / role), for *every* CL club, slow-paced with a circuit breaker.
         This is the authoritative recent-window source.
      2. Understat — domestic match logs, big-5 only. Optional depth layer
         (RECENT_FORM_SOURCE=both); Sofascore rows win per player because they
         carry the cup + CL games Understat can't see.
      3. Whatever is already stored in `player_form` (merged downstream) so a
         time-boxed run only ever *adds* coverage.

    Any source failing just means less fresh data, never a failed run.
    """
    from .mapping.form_match import build_player_form

    team_names = {tid: t.name for tid, t in teams.items()}
    n = env.recent_form_lookback
    leagues = [x.strip() for x in env.source_leagues.split(",") if x.strip()]
    src = (env.recent_form_source or "sofascore").lower()
    try:
        overrides = json.loads(db.get_settings(["ucl.role_overrides"]).get("ucl.role_overrides") or "{}")
    except (ValueError, TypeError):
        overrides = {}

    us_rows: list = []
    ss_rows: list = []

    # ---- 1. Understat (big-5 domestic) — optional depth layer -------------
    if src in ("both", "understat", "understat_only"):
        try:
            from .sources.understat_form import fetch_form_rows as fetch_us

            _log(f"form: Understat (domestic depth), last {n}, season {env.fbref_season}")
            us_rows = fetch_us(leagues, env.fbref_season, last_n=n)
            _log(f"  Understat: {len(us_rows)} player logs")
        except Exception as e:  # noqa: BLE001
            _log(f"  Understat unavailable ({type(e).__name__}: {e})")

    # ---- 2. Sofascore — last-N-overall, EVERY CL club --------------------
    if src != "understat_only":
        try:
            from .sources.recent_form import fetch_form_rows as fetch_ss

            budget = float(os.environ.get("SOFA_FORM_BUDGET_S", "2200") or 2200)
            dly = float(os.environ.get("SOFA_FORM_DELAY_S", "1.2") or 1.2)
            n_clubs = len({p.team_id for p in players if p.price >= env.recent_form_min_price})
            _log(f"form: Sofascore last-{n}-overall — all {n_clubs} CL clubs, "
                 f"{budget:.0f}s budget, {dly:.1f}s pacing (incremental: cached "
                 f"fixtures are free, so coverage builds run-over-run)")
            ss_rows = fetch_ss(
                players, team_names, last_n=n, min_price=env.recent_form_min_price,
                time_budget_s=budget, only_uids=None, delay=dly,
                log=lambda m: _log(m),
            )
            _log(f"  Sofascore: {len(ss_rows)} player logs")
        except Exception as e:  # noqa: BLE001
            _log(f"  Sofascore unavailable ({type(e).__name__}) — falling back to "
                 f"Understat + stored form")

    # Sofascore's all-comps window supersedes Understat's domestic-only one:
    # both feeds are passed to the matcher, which prefers the Sofascore row per
    # player (it carries the cup + CL games Understat can't see).
    all_rows = ss_rows + us_rows

    if not all_rows:
        _log("  no fresh form rows; projections use stored form + UEFA-minutes prior")
        return db.load_player_form() if not dry else {}

    form, unmatched = build_player_form(players, team_names, all_rows, overrides)
    form_by_pid = {f.player_id: f for f in form}
    xfer = [f for f in form if not f.team_ok]
    _log(f"  fresh form: matched {len(form)}/{len(players)} this run "
         f"({len(unmatched)} unmatched); {len(xfer)} transferred/role-mismatch")
    for f in xfer[:25]:
        p = next((x for x in players if x.uefa_player_id == f.player_id), None)
        _log(f"  MISMATCH  {p.name if p else f.player_id}: {f.role_note}")
    if not dry and form:
        db.replace_player_form(form)

    # `player_form` is an upsert store, so a time-boxed run only refreshes a
    # slice — merge this run's rows over everything accumulated so projections
    # see full history. BUT: for a club we genuinely just re-scraped from
    # Sofascore (senior, all-comps), a *stored* row for a player who did NOT
    # match a fresh senior sample is almost always a stale academy/reserve
    # artifact from an older Understat pull (Rivas, Gerard Martín, N. Brown…).
    # Evict those so they can't outrank real first-teamers in the predicted XI.
    pmap = {p.uefa_player_id: p for p in players}
    scraped_teams = {
        pmap[pid].team_id for pid, f in form_by_pid.items()
        if pid in pmap and f.source == "sofascore" and f.recent_matches > 0
    }
    merged = db.load_player_form() if not dry else {}
    stale = [
        pid for pid, f in merged.items()
        if pid not in form_by_pid
        and pid in pmap and pmap[pid].team_id in scraped_teams
        and (f.source != "sofascore" or f.recent_matches <= 2)
    ]
    for pid in stale:
        merged.pop(pid, None)
    if stale and not dry:
        db.delete_player_form(stale)
    merged.update(form_by_pid)
    _log(f"  form coverage after merge with stored: {len(merged)}/{len(players)} "
         f"({len(scraped_teams)} clubs re-scraped, {len(stale)} stale rows evicted)")
    return merged


def _form_from_sample(db, samples, players, teams, dry):
    from .mapping.form_match import build_player_form
    from .sources.understat_form import aggregate_match_rows

    rows = aggregate_match_rows(samples["form"])
    team_names = {tid: t.name for tid, t in teams.items()}
    form, _ = build_player_form(players, team_names, rows)
    if not dry and form:
        db.replace_player_form(form)
    return {f.player_id: f for f in form}


def _optimizer(db, players, teams, proj_by_md, matchday, params, picks_override, form_by_id=None):
    from .model.captains import analyse_captains
    from .model.chips import evaluate_chips
    from .model.optimizer import suggest_initial_squad

    picks = picks_override or db.load_my_squad(matchday)
    proj = {pr.player_id: pr for pr in proj_by_md.get(matchday, [])}
    pmap = {p.uefa_player_id: p for p in players}
    form_by_id = form_by_id or {}

    # Planning horizon: the next `params.horizon` matchdays we actually have
    # projections for — NOT every league-phase MD (proj_by_md now spans all 8).
    plan_mds = sorted(md for md in proj_by_md if md >= matchday) or sorted(proj_by_md)
    horizon = max(1, min(int(params.horizon), len(plan_mds)))
    horizon_mds = plan_mds[:horizon]
    # Weight nearer matchdays more heavily — the squad should be built to win the
    # *upcoming* fixture first, not an equal-weighted average of the next 8.
    decay = 0.65
    horizon_xpts: dict[int, float] = {}
    for i, md in enumerate(horizon_mds):
        w = decay ** i
        for pr in proj_by_md.get(md, []):
            horizon_xpts[pr.player_id] = horizon_xpts.get(pr.player_id, 0.0) + w * pr.xpts

    try:
        min_start = float(db.get_settings(["ucl.min_start_prob"]).get("ucl.min_start_prob") or 0.45)
    except ValueError:
        min_start = 0.45

    def mk(pid, owned, md=None):
        p = pmap.get(pid)
        pr = proj.get(pid) if md is None else _by_md.get(md, {}).get(pid)
        if not p or not pr:
            return None
        return OptPlayer(
            player_id=pid, name=p.name,
            team=teams.get(p.team_id).name if teams.get(p.team_id) else "",
            club_id=p.team_id, position=p.position, price=p.price, xpts=pr.xpts,
            owned=owned, horizon_xpts=horizon_xpts.get(pid, pr.xpts),
        )

    _by_md = {md: {pr.player_id: pr for pr in prs} for md, prs in proj_by_md.items()}

    # opponent + fixture-difficulty for this matchday, so every squad row the UI
    # renders can be sanity-checked ("why this defender, who do they play?").
    fx_by_club = _fixture_context(db, teams, matchday)

    def decorate(rows):
        for row in rows or []:
            p = pmap.get(row.get("playerId"))
            ctx = fx_by_club.get(p.team_id) if p else None
            if ctx:
                row["opp"], row["home"], row["fdr"], row["mdDay"] = ctx
            else:
                row["opp"], row["home"], row["fdr"], row["mdDay"] = None, None, None, None
        return rows

    def eligible(pid: int) -> bool:
        fm = form_by_id.get(pid)
        if fm is not None and not fm.team_ok:
            return False  # genuinely at another club now
        # Prefer the COMPOSED start prob (blends form + minutes + price + an
        # official lineup when one is out) over the raw recent-form rate — a
        # nailed or confirmed starter with a thin form sample must not be
        # filtered out of the transfer pool, and a confirmed-benched star must.
        pr = proj.get(pid)
        if pr is not None and pr.p_start is not None:
            return pr.p_start >= min_start
        if fm is None:
            return True  # no signal at all -> let the projection prior decide
        return fm.start_prob >= min_start or fm.recent_matches == 0

    pool = [
        op for p in players
        if eligible(p.uefa_player_id) and (op := mk(p.uefa_player_id, False)) and op.hx > 0
    ]
    squad = [op for pk in picks if (op := mk(pk.player_id, True))]

    # "Ideal" from-scratch squad — the target for a wildcard or the season start.
    ideal = suggest_initial_squad(pool, matchday=matchday, horizon=horizon)

    # Pre-season (team not yet locked) or no squad -> the ideal squad IS the advice.
    deadline = db.get_settings([Keys.DEADLINE]).get(Keys.DEADLINE)
    pre_season = False
    if deadline:
        try:
            pre_season = datetime.fromisoformat(deadline) > datetime.now(UTC)
        except ValueError:
            pre_season = False

    club_of = {pid: p.team_id for pid, p in pmap.items()}

    def attach_analyses(target: dict, sq_ids: list[int], free_transfers: int = 2) -> None:
        # captaincy for this matchday
        cap_rows = []
        for pid in sq_ids:
            p, pr = pmap.get(pid), proj.get(pid)
            if not p or not pr:
                continue
            cap_rows.append({
                "playerId": pid, "name": p.name,
                "team": teams.get(p.team_id).name if teams.get(p.team_id) else "",
                "position": p.position, "xpts": pr.xpts,
                "xptsHigh": pr.xpts_high, "xptsLow": pr.xpts_low,
                "selectedPct": p.selected_pct,
            })
        target["captains"] = analyse_captains(cap_rows)

        # chip strategy across all remaining matchdays
        try:
            sbm, pbm = {}, {}
            for md in sorted(proj_by_md):
                s_md = [op for pid in sq_ids if (op := mk(pid, True, md))]
                if len(s_md) < 15:
                    continue
                sbm[md] = s_md
                pbm[md] = [
                    op for p in players
                    if p.uefa_player_id not in sq_ids and eligible(p.uefa_player_id)
                    and (op := mk(p.uefa_player_id, False, md)) and op.xpts > 0
                ]
            if sbm:
                # CL league phase = 8 matchdays (evaluate_chips default)
                target["chips"] = evaluate_chips(
                    sbm, pbm, start_md=matchday, free_transfers=free_transfers
                )
        except Exception as e:  # noqa: BLE001
            _log(f"chip eval skipped: {e}")

        # per-matchday rotation + fixture-targeted buys
        plan = []
        owned = set(sq_ids)
        for md in plan_mds[: min(5, len(plan_mds))]:
            fx_md = _fixture_context(db, teams, md)
            s_md = sorted((op for pid in owned if (op := mk(pid, True, md))), key=lambda o: -o.xpts)
            xi = s_md[:11]
            targets = sorted(
                (op for p in players
                 if p.uefa_player_id not in owned and eligible(p.uefa_player_id)
                 and (op := mk(p.uefa_player_id, False, md)) and op.xpts > 0),
                key=lambda o: -o.xpts,
            )[:6]
            plan.append({
                "matchday": md,
                "xiXpts": round(sum(o.xpts for o in xi) + (xi[0].xpts if xi else 0.0), 1),
                "startForMd": [_plan_row(o, True, fx_md, club_of) for o in xi],
                "benchForMd": [_plan_row(o, True, fx_md, club_of) for o in s_md[11:15]],
                "targets": [_plan_row(o, False, fx_md, club_of) for o in targets],
            })
        if plan:
            target["matchdayPlan"] = plan

        # ---- matchday timing: CL lets you sub after the early games ----
        fx0 = _fixture_context(db, teams, matchday)
        timing = []
        for pid in sq_ids:
            op = mk(pid, True)
            ctx = fx0.get(pmap[pid].team_id) if pid in pmap else None
            if not op or not ctx:
                continue
            fm = form_by_id.get(pid)
            timing.append({
                "playerId": pid, "name": op.name, "position": op.position,
                "opp": ctx[0], "home": ctx[1], "fdr": ctx[2], "mdDay": ctx[3],
                "xpts": round(op.xpts, 2),
                "pStart": round(fm.start_prob, 2) if fm else None,
            })
        if timing:
            n_days = max((t["mdDay"] or 1) for t in timing)
            late = sorted(
                (t for t in timing if (t["mdDay"] or 1) >= n_days and t["xpts"] > 0),
                key=lambda t: -t["xpts"],
            )
            target["matchdayTiming"] = {
                "days": n_days,
                "players": sorted(timing, key=lambda t: (t["mdDay"] or 9, -t["xpts"])),
                "liveOptions": [t["name"] for t in late[:4]],
            }

    # Only surface the from-scratch ideal squad AS the whole recommendation when
    # there's no real 15 to analyse. If the user has picked a squad — even
    # before the MD1 deadline — the captain / best XI / live-option advice must
    # be about THEIR players, not a theoretical dream team. The ideal squad is
    # still attached below (as `idealSquad`) for "if you rebuilt from scratch".
    if len(squad) < 15:
        if not ideal:
            return None
        ideal["preSeason"] = True
        if squad:
            owned = {p.player_id for p in squad}
            keep = [p for p in ideal["squad"] if p["playerId"] in owned]
            ideal["changesFromCurrent"] = 15 - len(keep)
            ideal["keepFromCurrent"] = len(keep)
        decorate(ideal.get("squad"))
        attach_analyses(ideal, [p["playerId"] for p in ideal.get("squad", [])])
        return ideal

    bank = 0.0
    b = db.get_settings(["ucl.bank"]).get("ucl.bank")
    if b:
        try:
            bank = float(b)
        except ValueError:
            pass
    try:
        free_transfers = int(db.get_settings(["ucl.free_transfers"]).get("ucl.free_transfers") or 2)
    except ValueError:
        free_transfers = 2
    # Before the MD1 deadline the squad isn't locked — every change is free, so
    # the planner shouldn't be pricing in −4 hits for the 3rd+ move.
    ft_effective = 15 if pre_season else free_transfers
    starters = {pk.player_id for pk in picks if pk.is_starter}
    captain = next((pk.player_id for pk in picks if pk.is_captain), None)
    out = optimise(
        squad, pool, matchday=matchday, bank=bank, free_transfers=ft_effective,
        horizon=horizon, current_starter_ids=starters or None, current_captain_id=captain,
    )
    out["preSeason"] = False
    out["deadlineOpen"] = pre_season  # squad not locked yet — free to change
    out["freeTransfers"] = free_transfers
    if ideal:
        owned = {p.player_id for p in squad}
        ideal["changesFromCurrent"] = 15 - sum(1 for p in ideal["squad"] if p["playerId"] in owned)
        out["idealSquad"] = ideal

    decorate(out.get("bestXI"))
    decorate(out.get("bench"))
    if out.get("idealSquad"):
        decorate(out["idealSquad"].get("squad"))
    for t in out.get("transfers") or []:
        for side in ("in", "out"):
            if isinstance(t.get(side), dict):
                decorate([t[side]])

    attach_analyses(out, [pk.player_id for pk in picks], free_transfers)
    return out


def _plan_row(o, owned: bool, fx_md: dict, club_of: dict) -> dict:
    ctx = fx_md.get(club_of.get(o.player_id))
    return {
        "playerId": o.player_id, "name": o.name, "team": o.team,
        "position": o.position, "price": o.price, "xpts": round(o.xpts, 2),
        "owned": owned,
        "opp": ctx[0] if ctx else None,
        "home": ctx[1] if ctx else None,
        "fdr": ctx[2] if ctx else None,
        "mdDay": ctx[3] if ctx else None,
    }


def _print_top(projections, players, n=20):
    name = {p.uefa_player_id: p.name for p in players}
    _log(f"top {n} projected:")
    for pr in sorted(projections, key=lambda x: -x.xpts)[:n]:
        _log(f"  {pr.xpts:5.2f}  {name.get(pr.player_id, pr.player_id)}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="fantasy_ingest.run")
    ap.add_argument("--matchday", type=int, default=None)
    ap.add_argument("--skip-sources", action="store_true")
    ap.add_argument(
        "--live",
        action="store_true",
        help="matchday refresh: re-pull UEFA data + squad + rivals, rebuild the "
        "current matchday's projections and the live-state blob, skip the form "
        "scrape and future-matchday planning. Fast — safe to run every few "
        "minutes while games are on.",
    )
    ap.add_argument("--samples", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
