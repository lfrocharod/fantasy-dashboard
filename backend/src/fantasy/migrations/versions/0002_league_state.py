"""league state: move JSON blobs out of `settings` into real tables

Revision ID: 0002_league_state
Revises: 0001_baseline
Create Date: 2026-10-10

`settings` had become the store for everything: user config, encrypted
cookies, and whole league state as JSON strings (FPL/NFL standings, schedules,
lineups, the UCL optimizer output, live-matchday state). This revision:

* adds `leagues`, `league_entries`, `matchups`, `my_lineup` for league state
  the API queries and joins, and `documents` (JSONB) for computed outputs the
  UI always reads whole;
* copies what is in `settings` today into them (best-effort — a malformed or
  empty value is skipped, never fatal), so nothing waits for the next sync;
* turns the unique index on draft_players into its primary key.

The old settings keys are left in place (expand/contract): the previous app
version keeps working until cutover, and a later revision drops them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_league_state"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_KEYS = {
    "model.optimizer_output": "ucl.optimizer",
    "model.live_state": "ucl.live_state",
    "model.live_rivals": "ucl.live_rivals",
    "ingest.calibration": "ucl.calibration",
    "ingest.xg_coverage": "ucl.xg_coverage",
    "draft.fpl.live": "fpl.live",
}


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("n_teams", sa.Integer(), nullable=True),
        sa.Column("scoring", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("regular_rounds", sa.Integer(), nullable=True),
        sa.Column(
            "playoff_rounds",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column("playoff_teams", sa.Integer(), nullable=True),
        sa.Column("seeding_rule", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("roster", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("lineup_slots", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("sport", name=op.f("leagues_pkey")),
    )
    op.create_table(
        "league_entries",
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("is_mine", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("total", sa.REAL(), nullable=True),
        sa.Column("points_for", sa.REAL(), nullable=True),
        sa.Column("points_against", sa.REAL(), nullable=True),
        sa.Column("wins", sa.Integer(), nullable=True),
        sa.Column("draws", sa.Integer(), nullable=True),
        sa.Column("losses", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["sport"], ["leagues.sport"], name=op.f("league_entries_sport_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("sport", "entry_id", name=op.f("league_entries_pkey")),
    )
    op.create_table(
        "matchups",
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("round", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("home_entry", sa.Text(), nullable=False),
        sa.Column("away_entry", sa.Text(), nullable=False),
        sa.Column("home_name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("away_name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("home_points", sa.REAL(), nullable=True),
        sa.Column("away_points", sa.REAL(), nullable=True),
        sa.Column("winner", sa.Text(), nullable=True),
        sa.Column("finished", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["sport"], ["leagues.sport"], name=op.f("matchups_sport_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "sport", "round", "home_entry", "away_entry", name=op.f("matchups_pkey")
        ),
    )
    op.create_table(
        "my_lineup",
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("ext_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("starter", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("captain", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("vice", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.PrimaryKeyConstraint("sport", "ext_id", name=op.f("my_lineup_pkey")),
    )
    op.create_table(
        "documents",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("documents_pkey")),
    )
    # The unique index becomes the primary key (Postgres renames it).
    op.execute(
        "ALTER TABLE draft_players ADD CONSTRAINT draft_players_pkey "
        "PRIMARY KEY USING INDEX draft_players_pk"
    )

    _copy_settings_into_tables(op.get_bind())


def downgrade() -> None:
    op.execute("ALTER TABLE draft_players DROP CONSTRAINT draft_players_pkey")
    op.create_index("draft_players_pk", "draft_players", ["sport", "ext_id"], unique=True)
    op.drop_table("documents")
    op.drop_table("my_lineup")
    op.drop_table("matchups")
    op.drop_table("league_entries")
    op.drop_table("leagues")


# ---- data copy ------------------------------------------------------------------


def _json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _exec(conn: sa.Connection, sql: str, params: dict[str, Any]) -> None:
    conn.execute(sa.text(sql), params)


def _copy_settings_into_tables(conn: sa.Connection) -> None:
    s: dict[str, str] = {k: v for k, v in conn.execute(sa.text("SELECT key, value FROM settings"))}

    def put_league(sport: str, **cols: Any) -> None:
        cols = {k: v for k, v in cols.items() if v is not None}
        names = ", ".join(["sport", *cols])
        values = []
        for k in cols:
            values.append(f"CAST(:{k} AS jsonb)" if k in ("roster", "lineup_slots") else f":{k}")
        params = {k: json.dumps(v) if k in ("roster", "lineup_slots") else v for k, v in cols.items()}
        _exec(
            conn,
            f"INSERT INTO leagues ({names}) VALUES (:sport, {', '.join(values)}) "
            "ON CONFLICT DO NOTHING"
            if cols
            else "INSERT INTO leagues (sport) VALUES (:sport) ON CONFLICT DO NOTHING",
            {"sport": sport, **params},
        )

    # -- UCL --
    put_league(
        "ucl",
        current_round=_int(s.get("ucl.current_matchday")),
        deadline=s.get("ucl.deadline_iso") or None,
    )

    # -- FPL Draft --
    put_league(
        "fpl", n_teams=_int(s.get("draft.fpl.teams")), scoring=s.get("draft.fpl.mode") or None
    )
    my_fpl = str(s.get("draft.fpl.entry_id") or "")
    for row in _json(s.get("draft.fpl.standings")) or []:
        if not isinstance(row, dict) or row.get("entry_id") in (None, ""):
            continue
        eid = str(row["entry_id"])
        _exec(
            conn,
            "INSERT INTO league_entries (sport, entry_id, name, is_mine, rank, total, points_for, "
            "points_against, wins, draws, losses) VALUES ('fpl', :e, :n, :m, :r, :t, :pf, :pa, "
            ":w, :d, :l) ON CONFLICT DO NOTHING",
            {
                "e": eid, "n": str(row.get("name") or ""), "m": eid == my_fpl,
                "r": _int(row.get("rank")), "t": _num(row.get("total")),
                "pf": _num(row.get("points_for")), "pa": _num(row.get("points_against")),
                "w": _int(row.get("w")), "d": _int(row.get("d")), "l": _int(row.get("l")),
            },
        )
    for m in _json(s.get("draft.fpl.schedule")) or []:
        if not isinstance(m, dict) or _int(m.get("event")) is None:
            continue
        _exec(
            conn,
            "INSERT INTO matchups (sport, round, home_entry, away_entry, home_name, away_name, "
            "home_points, away_points, finished) VALUES ('fpl', :r, :he, :ae, :hn, :an, :hp, :ap, "
            ":f) ON CONFLICT DO NOTHING",
            {
                "r": _int(m.get("event")), "he": str(m.get("home_entry") or ""),
                "ae": str(m.get("away_entry") or ""), "hn": str(m.get("home") or ""),
                "an": str(m.get("away") or ""), "hp": _num(m.get("home_pts")),
                "ap": _num(m.get("away_pts")), "f": bool(m.get("finished")),
            },
        )
    lineup = _json(s.get("draft.fpl.my_lineup"))
    picks = lineup.get("picks") if isinstance(lineup, dict) else lineup
    source = str(lineup.get("source") or "") if isinstance(lineup, dict) else ""
    seen: set[str] = set()
    for p in picks or []:
        if not isinstance(p, dict) or not p.get("extId"):
            continue
        seen.add(str(p["extId"]))
        _exec(
            conn,
            "INSERT INTO my_lineup (sport, ext_id, position, starter, captain, vice, source) "
            "VALUES ('fpl', :x, :pos, :st, :c, :v, :src) ON CONFLICT DO NOTHING",
            {
                "x": str(p["extId"]), "pos": _int(p.get("slot")), "st": bool(p.get("starter")),
                "c": bool(p.get("captain")), "v": bool(p.get("vice")), "src": source,
            },
        )
    for ext in _json(s.get("draft.fpl.my_squad")) or []:
        if str(ext) not in seen:
            _exec(
                conn,
                "INSERT INTO my_lineup (sport, ext_id) VALUES ('fpl', :x) ON CONFLICT DO NOTHING",
                {"x": str(ext)},
            )

    # -- NFL --
    team_names = _json(s.get("draft.nfl.teams"))
    n_nfl = len(team_names) if isinstance(team_names, dict) else _int(s.get("draft.nfl.teams"))
    playoff = [w for w in (_int(x) for x in (_json(s.get("draft.nfl.playoff_weeks")) or [])) if w]
    put_league(
        "nfl",
        current_round=_int(s.get("draft.nfl.week")),
        n_teams=n_nfl,
        scoring=s.get("draft.nfl.scoring") or None,
        regular_rounds=_int(s.get("draft.nfl.reg_weeks")),
        playoff_rounds=playoff or None,
        playoff_teams=_int(s.get("draft.nfl.playoff_teams")),
        seeding_rule=s.get("draft.nfl.seeding_rule") or None,
        roster=_json(s.get("draft.nfl.roster")),
        lineup_slots=_json(s.get("draft.nfl.slots")),
    )
    my_nfl = str(s.get("draft.nfl.my_team_id") or "")
    for row in _json(s.get("draft.nfl.standings")) or []:
        if not isinstance(row, dict) or row.get("team_id") in (None, ""):
            continue
        eid = str(row["team_id"])
        _exec(
            conn,
            "INSERT INTO league_entries (sport, entry_id, name, is_mine, points_for, "
            "points_against, wins, draws, losses) VALUES ('nfl', :e, :n, :m, :pf, :pa, :w, :d, "
            ":l) ON CONFLICT DO NOTHING",
            {
                "e": eid, "n": str(row.get("name") or ""), "m": eid == my_nfl,
                "pf": _num(row.get("pf")), "pa": _num(row.get("pa")),
                "w": _int(row.get("wins")), "d": _int(row.get("ties")), "l": _int(row.get("losses")),
            },
        )
    for m in _json(s.get("draft.nfl.schedule")) or []:
        if not isinstance(m, dict) or _int(m.get("week")) is None:
            continue
        winner = m.get("winner")
        _exec(
            conn,
            "INSERT INTO matchups (sport, round, home_entry, away_entry, home_name, away_name, "
            "home_points, away_points, winner, finished) VALUES ('nfl', :r, :he, :ae, :hn, :an, "
            ":hp, :ap, :w, :f) ON CONFLICT DO NOTHING",
            {
                "r": _int(m.get("week")), "he": str(m.get("home") or ""),
                "ae": str(m.get("away") or ""), "hn": str(m.get("home_name") or ""),
                "an": str(m.get("away_name") or ""), "hp": _num(m.get("home_pts")),
                "ap": _num(m.get("away_pts")), "w": winner,
                "f": winner in ("HOME", "AWAY", "TIE"),
            },
        )
    for ext in _json(s.get("draft.nfl.my_roster")) or []:
        _exec(
            conn,
            "INSERT INTO my_lineup (sport, ext_id, source) VALUES ('nfl', :x, 'espn') "
            "ON CONFLICT DO NOTHING",
            {"x": str(ext)},
        )

    # -- computed documents --
    for old_key, doc_key in DOCUMENT_KEYS.items():
        payload = _json(s.get(old_key))
        if payload:
            _exec(
                conn,
                "INSERT INTO documents (key, payload) VALUES (:k, CAST(:p AS jsonb)) "
                "ON CONFLICT DO NOTHING",
                {"k": doc_key, "p": json.dumps(payload)},
            )
