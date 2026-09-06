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
import sys
import traceback
from pathlib import Path

from . import MODEL_VERSION
from .config import Env, Keys
from .db import DB
from .model import team_strength
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
    for name in ("players", "fixtures", "teams", "my_team", "league", "private_leagues"):
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

        with UefaClient(token=token) as client:
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

            # ---- 3. external xG/xA ------------------------------
            stats = {}
            if not args.skip_sources and not env.skip_sources:
                try:
                    stats = _sources(db, env, players, teams, args.dry_run)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"sources step failed, UEFA form only: {e}")
                    _log(notes[-1])
            if not stats:
                stats = db.load_player_stats() if not args.dry_run else {}

            # ---- 4. team strength ------------------------------
            ratings = team_strength.ratings_from_fixtures(fixtures, teams.keys())
            team_strength.apply_ratings(teams, ratings)
            if not args.dry_run:
                db.upsert_teams(list(teams.values()))

            # ---- 5. projections -------------------------------
            projections = _build_projections(players, teams, fixtures, stats, matchday, params)
            _log(f"built {len(projections)} projections")
            if not args.dry_run:
                db.replace_projections(matchday, projections, MODEL_VERSION)
            else:
                _print_top(projections, players)

            # ---- 6. optimizer --------------------------------
            opt = _optimizer(db, players, teams, projections, matchday, params, picks)
            if opt:
                _log(f"optimizer: {opt['formation']}, {len(opt['transfers'])} transfer idea(s)")
                if not args.dry_run:
                    db.set_setting(Keys.OPTIMIZER_OUTPUT, json.dumps(opt))

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
        if m.matchday == matchday and m.deadline:
            db.set_setting(Keys.DEADLINE, m.deadline.isoformat())


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
                client.get_league_standings(league_id), matchday
            )
            _log(f"league {league_id}: {len(entries)} entries")
            if entries:
                db.upsert_league_standings(league_id, entries)
        except (UefaAuthError, KeyError, ValueError) as e:
            notes.append(f"league standings failed: {e}")
            _log(notes[-1])
    return picks


def _sources(db, env: Env, players, teams, dry):
    from .mapping.player_match import build_stats
    from .sources.domestic_xg import fetch_fbref_rows, fetch_understat_rows

    leagues = [x.strip() for x in env.source_leagues.split(",") if x.strip()]
    _log(f"scraping FBref for {leagues} ...")
    fbref_rows = fetch_fbref_rows(leagues, env.fbref_season)
    _log(f"  {len(fbref_rows)} FBref rows")
    try:
        understat_rows = fetch_understat_rows(
            [lg for lg in leagues if lg.split("-")[0] in ("ENG", "ESP", "GER", "ITA", "FRA")],
            env.fbref_season,
        )
    except Exception as e:  # noqa: BLE001
        _log(f"  understat skipped: {e}")
        understat_rows = []

    team_names = {tid: t.name for tid, t in teams.items()}
    overrides = _overrides(db)
    report = build_stats(players, team_names, fbref_rows, understat_rows, overrides)
    _log(
        f"matched {len(report.matched)}/{len(players)} "
        f"({len(report.unmatched)} unmatched, {len(report.low_confidence)} low-confidence)"
    )
    for pid, name, tm in report.unmatched[:40]:
        _log(f"  UNMATCHED {pid:>10}  {name} ({tm})")
    if not dry and report.matched:
        db.upsert_player_stats(list(report.matched.values()))
    return report.matched


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


def _build_projections(players, teams, fixtures, stats, matchday, params):
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
        out.append(project_player(p, stats.get(p.uefa_player_id), team, opp, is_home, matchday, params))
    return out


def _optimizer(db, players, teams, projections, matchday, params, picks_override):
    picks = picks_override or db.load_my_squad(matchday)
    proj = {pr.player_id: pr for pr in projections}
    pmap = {p.uefa_player_id: p for p in players}

    def mk(pid, owned):
        p, pr = pmap.get(pid), proj.get(pid)
        if not p or not pr:
            return None
        return OptPlayer(
            player_id=pid, name=p.name,
            team=teams.get(p.team_id).name if teams.get(p.team_id) else "",
            club_id=p.team_id, position=p.position, price=p.price, xpts=pr.xpts, owned=owned,
        )

    squad = [op for pk in picks if (op := mk(pk.player_id, True))]
    if len(squad) < 11:
        return None
    pool = [op for p in players if (op := mk(p.uefa_player_id, False)) and op.xpts > 0]

    bank = 0.0
    b = db.get_settings(["ucl.bank"]).get("ucl.bank")
    if b:
        try:
            bank = float(b)
        except ValueError:
            pass
    starters = {pk.player_id for pk in picks if pk.is_starter}
    captain = next((pk.player_id for pk in picks if pk.is_captain), None)
    return optimise(
        squad, pool, matchday=matchday, bank=bank, horizon=int(params.horizon),
        current_starter_ids=starters or None, current_captain_id=captain,
    )


def _print_top(projections, players, n=20):
    name = {p.uefa_player_id: p.name for p in players}
    _log(f"top {n} projected:")
    for pr in sorted(projections, key=lambda x: -x.xpts)[:n]:
        _log(f"  {pr.xpts:5.2f}  {name.get(pr.player_id, pr.player_id)}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="fantasy_ingest.run")
    ap.add_argument("--matchday", type=int, default=None)
    ap.add_argument("--skip-sources", action="store_true")
    ap.add_argument("--samples", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
