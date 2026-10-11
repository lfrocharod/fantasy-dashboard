"""Schema migrations: the chain applies cleanly, matches the models, the 0002
data copy moves the settings blobs into the new tables, and 0004 drops them."""

from __future__ import annotations

import json

import psycopg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from fantasy.core import migrations
from fantasy.core.database import database_url
from fantasy.core.models import Base

pytestmark = pytest.mark.db


def test_upgrade_head_matches_models(migrated_db: str) -> None:
    engine = create_engine(database_url(migrated_db))
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "compare_server_default": True}
        )
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diff == [], f"models and migrations have drifted: {diff}"


def test_legacy_database_is_stamped_not_recreated(empty_db: str) -> None:
    # A database created before Alembic (drizzle-kit) has the tables but no
    # alembic_version: upgrade() must stamp the baseline instead of failing.
    command.upgrade(migrations.config(), "0001_baseline")
    with psycopg.connect(empty_db, autocommit=True) as c:
        c.execute("DROP TABLE alembic_version")
        c.execute("INSERT INTO settings (key, value) VALUES ('ucl.current_matchday', '3')")
    migrations.upgrade("head")
    with psycopg.connect(empty_db) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone()[0].startswith("000")
        assert c.execute("SELECT current_round FROM leagues WHERE sport='ucl'").fetchone() == (3,)


def test_0002_copies_settings_blobs(empty_db: str) -> None:
    command.upgrade(migrations.config(), "0001_baseline")
    rows = {
        "ucl.current_matchday": "2",
        "ucl.deadline_iso": "2026-10-13T16:45:00+00:00",
        "draft.fpl.entry_id": "111",
        "draft.fpl.mode": "c",
        "draft.fpl.teams": "5",
        "draft.fpl.standings": json.dumps([
            {"league_entry": 1, "entry_id": 111, "name": "Mine", "rank": 1, "total": 410,
             "points_for": 410, "w": None, "d": None, "l": None},
            {"league_entry": 2, "entry_id": 222, "name": "Rival", "rank": 2, "total": 400},
            {"league_entry": 3, "entry_id": None, "name": "ghost"},
        ]),
        "draft.fpl.schedule": json.dumps([
            {"event": 7, "home": "Mine", "away": "Rival", "home_entry": 111, "away_entry": 222,
             "home_pts": 51, "away_pts": 44, "finished": True},
        ]),
        "draft.fpl.my_lineup": json.dumps({"source": "my-team", "picks": [
            {"extId": "10", "slot": 1, "starter": True, "captain": False, "vice": False},
            {"extId": "11", "slot": 12, "starter": False, "captain": False, "vice": False},
        ]}),
        "draft.fpl.my_squad": json.dumps(["10", "11", "12"]),
        "draft.nfl.my_team_id": "4",
        "draft.nfl.week": "6",
        "draft.nfl.reg_weeks": "14",
        "draft.nfl.playoff_weeks": json.dumps([15, 16]),
        "draft.nfl.playoff_teams": "4",
        "draft.nfl.seeding_rule": "H2H_RECORD",
        "draft.nfl.slots": json.dumps({"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}),
        "draft.nfl.teams": json.dumps({"4": "Mine", "5": "Them"}),
        "draft.nfl.standings": json.dumps([
            {"team_id": 4, "name": "Mine", "wins": 3, "losses": 2, "ties": 0, "pf": 620.5,
             "pa": 600.1},
        ]),
        "draft.nfl.schedule": json.dumps([
            {"week": 6, "home": 4, "away": 5, "home_name": "Mine", "away_name": "Them",
             "home_pts": 0, "away_pts": 0, "winner": "UNDECIDED"},
        ]),
        "draft.nfl.my_roster": json.dumps(["9001", "9002"]),
        "model.optimizer_output": json.dumps({"matchday": 2, "formation": "4-4-2"}),
        "model.live_state": "",  # empty: skipped
        "ingest.calibration": "{not json",  # malformed: skipped, never fatal
    }
    with psycopg.connect(empty_db, autocommit=True) as c:
        for k, v in rows.items():
            c.execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (k, v))

    migrations.upgrade("head")

    with psycopg.connect(empty_db) as c:
        leagues = {
            r[0]: r[1:]
            for r in c.execute(
                "SELECT sport, current_round, n_teams, scoring, regular_rounds, playoff_rounds, "
                "playoff_teams, seeding_rule, lineup_slots, deadline IS NOT NULL FROM leagues"
            )
        }
        assert leagues["ucl"][0] == 2 and leagues["ucl"][-1] is True
        assert leagues["fpl"][1:3] == (5, "c")
        nfl = leagues["nfl"]
        assert nfl[0] == 6 and nfl[1] == 2 and nfl[3] == 14 and nfl[4] == [15, 16]
        assert nfl[6] == "H2H_RECORD" and nfl[7]["FLEX"] == 1

        entries = c.execute(
            "SELECT sport, entry_id, name, is_mine, rank, total, wins, points_for "
            "FROM league_entries ORDER BY sport, entry_id"
        ).fetchall()
        assert entries == [
            ("fpl", "111", "Mine", True, 1, 410.0, None, 410.0),
            ("fpl", "222", "Rival", False, 2, 400.0, None, None),
            ("nfl", "4", "Mine", True, None, None, 3, 620.5),
        ]
        matchups = c.execute(
            "SELECT sport, round, home_entry, away_entry, home_points, winner, finished "
            "FROM matchups ORDER BY sport"
        ).fetchall()
        assert matchups == [
            ("fpl", 7, "111", "222", 51.0, None, True),
            ("nfl", 6, "4", "5", 0.0, "UNDECIDED", False),
        ]
        lineup = c.execute(
            "SELECT sport, ext_id, position, starter, source FROM my_lineup ORDER BY sport, ext_id"
        ).fetchall()
        assert lineup == [
            ("fpl", "10", 1, True, "my-team"),
            ("fpl", "11", 12, False, "my-team"),
            ("fpl", "12", None, False, ""),
            ("nfl", "9001", None, False, "espn"),
            ("nfl", "9002", None, False, "espn"),
        ]
        docs = dict(c.execute("SELECT key, payload FROM documents"))
        assert docs == {"ucl.optimizer": {"matchday": 2, "formation": "4-4-2"}}
        # draft_players now has a real primary key
        assert c.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'draft_players_pkey' AND contype = 'p'"
        ).fetchone()


def test_0004_drops_the_copied_keys_and_keeps_config(empty_db: str) -> None:
    command.upgrade(migrations.config(), "0003_model_predictions")
    kept = {"ucl.league_id": "25", "draft.nfl.my_team_id": "4", "draft.nfl.teams": "10",
            "draft.fpl.entry_id": "111", "draft.nba.league_id": "7"}
    dropped = {"model.optimizer_output": "{}", "draft.nfl.standings": "[]",
               "ucl.current_matchday": "2", "draft.fpl.my_squad": "[]"}
    with psycopg.connect(empty_db, autocommit=True) as c:
        for k, v in {**kept, **dropped}.items():
            c.execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (k, v))
    migrations.upgrade("head")
    with psycopg.connect(empty_db) as c:
        left = dict(c.execute("SELECT key, value FROM settings").fetchall())
    assert left == kept

