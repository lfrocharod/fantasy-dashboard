"""Thin Postgres layer over psycopg3. Upserts keyed on UEFA ids so every run is
idempotent."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg

from .types import (
    Fixture,
    LeagueEntry,
    Player,
    PlayerStat,
    Projection,
    SquadPick,
    Team,
)


class DB:
    def __init__(self, url: str):
        # psycopg wants "postgresql://"; accept the "postgres://" many tools emit.
        self.url = url.replace("postgres://", "postgresql://", 1)
        self._conn: psycopg.Connection | None = None

    def _connect(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            # connect_timeout stops a hang when Neon is resuming from idle;
            # autocommit keeps the ~2k per-run upserts simple and cheap.
            self._conn = psycopg.connect(
                self.url,
                autocommit=True,
                connect_timeout=15,
                keepalives=1,
                keepalives_idle=30,
            )
        return self._conn

    @contextmanager
    def conn(self):
        yield self._connect()

    def _many(self, sql: str, rows: list[tuple], *, atomic_delete: str | None = None,
              delete_args: tuple = ()) -> None:
        """Batched write. psycopg3 pipelines executemany, so this is ~1 round-trip
        instead of N. `atomic_delete` runs a DELETE + the inserts in one txn."""
        if not rows and atomic_delete is None:
            return
        conn = self._connect()
        if atomic_delete is not None:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(atomic_delete, delete_args)
                if rows:
                    cur.executemany(sql, rows)
        else:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()

    # ---- settings ----------------------------------------------------------

    def get_settings(self, keys: list[str]) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute(
                "select key, value from settings where key = any(%s)", (keys,)
            ).fetchall()
        return {k: v for k, v in rows}

    def set_setting(self, key: str, value: str) -> None:
        with self.conn() as c:
            c.execute(
                """insert into settings (key, value, updated_at)
                   values (%s, %s, now())
                   on conflict (key) do update set value = excluded.value, updated_at = now()""",
                (key, value),
            )
            c.commit()

    # ---- reference data --------------------------------------------------

    def upsert_teams(self, teams: list[Team]) -> None:
        self._many(
            """insert into teams (uefa_team_id, name, code, attack_rating, defence_rating, updated_at)
               values (%s,%s,%s,%s,%s, now())
               on conflict (uefa_team_id) do update set
                 name=excluded.name, code=excluded.code,
                 attack_rating=excluded.attack_rating,
                 defence_rating=excluded.defence_rating, updated_at=now()""",
            [(t.uefa_team_id, t.name, t.code, t.attack_rating, t.defence_rating) for t in teams],
        )

    def upsert_players(self, players: list[Player]) -> None:
        self._many(
            """insert into players
               (uefa_player_id, name, display_name, team_id, position, price,
                uefa_total_points, uefa_form, selected_pct, status_code, status_detail,
                fbref_id, understat_id, updated_at)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               on conflict (uefa_player_id) do update set
                 name=excluded.name, display_name=excluded.display_name,
                 team_id=excluded.team_id, position=excluded.position,
                 price=excluded.price, uefa_total_points=excluded.uefa_total_points,
                 uefa_form=excluded.uefa_form, selected_pct=excluded.selected_pct,
                 status_code=excluded.status_code, status_detail=excluded.status_detail,
                 fbref_id=coalesce(excluded.fbref_id, players.fbref_id),
                 understat_id=coalesce(excluded.understat_id, players.understat_id),
                 updated_at=now()""",
            [
                (p.uefa_player_id, p.name, p.name, p.team_id, p.position, p.price,
                 p.uefa_total_points, p.uefa_form, p.selected_pct, p.status_code,
                 p.status_detail, p.fbref_id, p.understat_id)
                for p in players
            ],
        )

    def set_player_external_ids(self, mapping: dict[int, tuple[str | None, str | None]]) -> None:
        self._many(
            "update players set fbref_id=%s, understat_id=%s, updated_at=now() where uefa_player_id=%s",
            [(fb, us, pid) for pid, (fb, us) in mapping.items()],
        )

    def upsert_player_stats(self, stats: list[PlayerStat]) -> None:
        self._many(
            """insert into player_stats
               (player_id, scope, minutes, matches, npxg90, xag90, shots90, sca90, save_pct, source, updated_at)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               on conflict (player_id, scope) do update set
                 minutes=excluded.minutes, matches=excluded.matches,
                 npxg90=excluded.npxg90, xag90=excluded.xag90,
                 shots90=excluded.shots90, sca90=excluded.sca90,
                 save_pct=excluded.save_pct, source=excluded.source, updated_at=now()""",
            [
                (s.player_id, s.scope, s.minutes, s.matches, s.npxg90, s.xag90,
                 s.shots90, s.sca90, s.save_pct, s.source)
                for s in stats
            ],
        )

    def upsert_fixtures(self, fixtures: list[Fixture]) -> None:
        self._many(
            """insert into fixtures
               (uefa_match_id, matchday, home_team_id, away_team_id, kickoff, status,
                home_goals, away_goals, home_xg_est, away_xg_est, updated_at)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               on conflict (uefa_match_id) do update set
                 matchday=excluded.matchday, home_team_id=excluded.home_team_id,
                 away_team_id=excluded.away_team_id, kickoff=excluded.kickoff,
                 status=excluded.status, home_goals=excluded.home_goals,
                 away_goals=excluded.away_goals, home_xg_est=excluded.home_xg_est,
                 away_xg_est=excluded.away_xg_est, updated_at=now()""",
            [
                (f.uefa_match_id, f.matchday, f.home_team_id, f.away_team_id, f.kickoff,
                 f.status, f.home_goals, f.away_goals, f.home_xg_est, f.away_xg_est)
                for f in fixtures
            ],
        )

    def replace_projections(self, matchday: int, projections: list[Projection], model_version: str) -> None:
        self._many(
            """insert into projections
               (player_id, matchday, p_start, exp_minutes, xpts, xpts_captain, value,
                xpts_high, xpts_low, components, model_version, generated_at)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())""",
            [
                (p.player_id, p.matchday, p.p_start, p.exp_minutes, p.xpts,
                 p.xpts_captain, p.value, p.xpts_high, p.xpts_low,
                 json.dumps(p.components), model_version)
                for p in projections
            ],
            atomic_delete="delete from projections where matchday=%s",
            delete_args=(matchday,),
        )

    def replace_my_squad(self, matchday: int, picks: list[SquadPick]) -> None:
        self._many(
            """insert into my_squad
               (matchday, player_id, is_starter, is_captain, is_vice, bench_order, purchase_price, updated_at)
               values (%s,%s,%s,%s,%s,%s,%s, now())""",
            [
                (matchday, s.player_id, s.is_starter, s.is_captain, s.is_vice,
                 s.bench_order, s.purchase_price)
                for s in picks
            ],
            atomic_delete="delete from my_squad where matchday=%s",
            delete_args=(matchday,),
        )

    def upsert_league_standings(self, league_id: str, entries: list[LeagueEntry]) -> None:
        self._many(
            """insert into league_standings
               (league_id, entry_id, manager_name, team_name, matchday, points,
                total_points, rank, prev_rank, squad, updated_at)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               on conflict (league_id, entry_id, matchday) do update set
                 manager_name=excluded.manager_name, team_name=excluded.team_name,
                 points=excluded.points, total_points=excluded.total_points,
                 rank=excluded.rank, prev_rank=excluded.prev_rank,
                 squad=excluded.squad, updated_at=now()""",
            [
                (league_id, e.entry_id, e.manager_name, e.team_name, e.matchday,
                 e.points, e.total_points, e.rank, e.prev_rank, json.dumps(e.squad))
                for e in entries
            ],
        )

    def load_players(self) -> list[Player]:
        with self.conn() as c:
            rows = c.execute(
                """select uefa_player_id, name, team_id, position, price, uefa_total_points,
                          uefa_form, selected_pct, status_code, status_detail, fbref_id, understat_id
                   from players"""
            ).fetchall()
        return [
            Player(
                uefa_player_id=r[0], name=r[1], team_id=r[2], position=r[3], price=r[4],
                uefa_total_points=r[5], uefa_form=r[6], selected_pct=r[7], status_code=r[8],
                status_detail=r[9], fbref_id=r[10], understat_id=r[11],
            )
            for r in rows
        ]

    def load_teams(self) -> dict[int, Team]:
        with self.conn() as c:
            rows = c.execute(
                "select uefa_team_id, name, code, attack_rating, defence_rating from teams"
            ).fetchall()
        return {
            r[0]: Team(uefa_team_id=r[0], name=r[1], code=r[2], attack_rating=r[3], defence_rating=r[4])
            for r in rows
        }

    def load_fixtures(self, matchday: int | None = None) -> list[Fixture]:
        q = """select uefa_match_id, matchday, home_team_id, away_team_id, kickoff, status,
                      home_goals, away_goals, home_xg_est, away_xg_est from fixtures"""
        params: tuple = ()
        if matchday is not None:
            q += " where matchday=%s"
            params = (matchday,)
        with self.conn() as c:
            rows = c.execute(q, params).fetchall()
        return [
            Fixture(
                uefa_match_id=r[0], matchday=r[1], home_team_id=r[2], away_team_id=r[3],
                kickoff=r[4], status=r[5], home_goals=r[6], away_goals=r[7],
                home_xg_est=r[8], away_xg_est=r[9],
            )
            for r in rows
        ]

    def load_player_stats(self) -> dict[int, PlayerStat]:
        with self.conn() as c:
            rows = c.execute(
                """select player_id, scope, minutes, matches, npxg90, xag90, shots90, sca90, save_pct, source
                   from player_stats where scope in ('combined','domestic')"""
            ).fetchall()
        # prefer 'combined', fall back to 'domestic'
        out: dict[int, PlayerStat] = {}
        for r in rows:
            st = PlayerStat(
                player_id=r[0], scope=r[1], minutes=r[2], matches=r[3], npxg90=r[4],
                xag90=r[5], shots90=r[6], sca90=r[7], save_pct=r[8], source=r[9],
            )
            if r[0] not in out or st.scope == "combined":
                out[r[0]] = st
        return out

    def load_my_squad(self, matchday: int) -> list[SquadPick]:
        with self.conn() as c:
            rows = c.execute(
                """select player_id, is_starter, is_captain, is_vice, bench_order, purchase_price
                   from my_squad where matchday=%s""",
                (matchday,),
            ).fetchall()
        return [
            SquadPick(player_id=r[0], is_starter=r[1], is_captain=r[2], is_vice=r[3],
                      bench_order=r[4], purchase_price=r[5])
            for r in rows
        ]

    # ---- run bookkeeping ----------------------------------------------------

    def start_run(self, stage: str = "start") -> int:
        with self.conn() as c:
            rid = c.execute(
                "insert into ingest_runs (started_at, stage) values (now(), %s) returning id",
                (stage,),
            ).fetchone()[0]
            c.commit()
        return rid

    def finish_run(self, run_id: int, ok: bool, stage: str, notes: str = "") -> None:
        with self.conn() as c:
            c.execute(
                "update ingest_runs set finished_at=now(), ok=%s, stage=%s, notes=%s where id=%s",
                (ok, stage, notes[:2000], run_id),
            )
            c.commit()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
