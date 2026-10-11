"""baseline: the schema production already has (created by drizzle-kit before
Alembic). `fantasy db upgrade` stamps this revision on such a database instead
of running it.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-10 21:00:29.704322
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "draft_picks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pick_in_round", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("team_id", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("team_name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("player_ext_id", sa.Text(), nullable=False),
        sa.Column("is_mine", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("'manual'::text"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("draft_picks_pkey")),
    )
    op.create_index(
        "draft_picks_player_idx", "draft_picks", ["sport", "player_ext_id"], unique=False
    )
    op.create_index(
        "draft_picks_sport_overall_idx", "draft_picks", ["sport", "overall"], unique=True
    )
    op.create_table(
        "draft_players",
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("ext_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("team", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("positions", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("primary_pos", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("proj_points", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("adp", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("provider_rank", sa.Integer(), nullable=True),
        sa.Column("ecr_rank", sa.Integer(), nullable=True),
        sa.Column("ecr_tier", sa.Integer(), nullable=True),
        sa.Column("ecr_pos_rank", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("ecr_std", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("vbd", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("bye_week", sa.Integer(), nullable=True),
        sa.Column("injury_status", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("outlook", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("draft_players_pk", "draft_players", ["sport", "ext_id"], unique=True)
    op.create_index("draft_players_sport_idx", "draft_players", ["sport"], unique=False)
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ok", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("stage", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("notes", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("ingest_runs_pkey")),
    )
    op.create_table(
        "league_standings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Text(), nullable=False),
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("manager_name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("team_name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("matchday", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("prev_rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("squad", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("league_standings_pkey")),
    )
    op.create_index(
        "league_standings_key_idx",
        "league_standings",
        ["league_id", "entry_id", "matchday"],
        unique=True,
    )
    op.create_index("league_standings_league_idx", "league_standings", ["league_id"], unique=False)
    op.create_table(
        "live_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("matchday", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("secured", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("projected", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("pre_match", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'live'::text"), nullable=False),
        sa.Column("blob", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("live_snapshots_pkey")),
    )
    op.create_index(
        "live_snapshots_md_idx", "live_snapshots", ["matchday", "captured_at"], unique=False
    )
    op.create_table(
        "player_id_overrides",
        sa.Column("uefa_player_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("fbref_id", sa.Text(), nullable=True),
        sa.Column("understat_id", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.PrimaryKeyConstraint("uefa_player_id", name=op.f("player_id_overrides_pkey")),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("settings_pkey")),
    )
    op.create_table(
        "teams",
        sa.Column("uefa_team_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("attack_rating", sa.REAL(), server_default=sa.text("1"), nullable=False),
        sa.Column("defence_rating", sa.REAL(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("uefa_team_id", name=op.f("teams_pkey")),
    )
    op.create_table(
        "fixtures",
        sa.Column("uefa_match_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("matchday", sa.Integer(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'upcoming'::text"), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=True),
        sa.Column("away_goals", sa.Integer(), nullable=True),
        sa.Column("home_xg_est", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("away_xg_est", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["away_team_id"],
            ["teams.uefa_team_id"],
            name="fixtures_away_team_id_teams_uefa_team_id_fk",
        ),
        sa.ForeignKeyConstraint(
            ["home_team_id"],
            ["teams.uefa_team_id"],
            name="fixtures_home_team_id_teams_uefa_team_id_fk",
        ),
        sa.PrimaryKeyConstraint("uefa_match_id", name=op.f("fixtures_pkey")),
    )
    op.create_index("fixtures_md_idx", "fixtures", ["matchday"], unique=False)
    op.create_table(
        "players",
        sa.Column("uefa_player_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("price", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("uefa_total_points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("uefa_form", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("selected_pct", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("status_code", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status_detail", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("fbref_id", sa.Text(), nullable=True),
        sa.Column("understat_id", sa.Text(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("price_momentum", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("set_piece", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.uefa_team_id"], name="players_team_id_teams_uefa_team_id_fk"
        ),
        sa.PrimaryKeyConstraint("uefa_player_id", name=op.f("players_pkey")),
    )
    op.create_index("players_pos_idx", "players", ["position"], unique=False)
    op.create_index("players_team_idx", "players", ["team_id"], unique=False)
    op.create_table(
        "my_squad",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("matchday", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("is_starter", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_captain", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_vice", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("bench_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("purchase_price", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.uefa_player_id"],
            name="my_squad_player_id_players_uefa_player_id_fk",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("my_squad_pkey")),
    )
    op.create_index("my_squad_md_player_idx", "my_squad", ["matchday", "player_id"], unique=True)
    op.create_table(
        "player_form",
        sa.Column("player_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("'understat'::text"), nullable=False),
        sa.Column("source_team", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("team_ok", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("role", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("role_note", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("recent_matches", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_starts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_minutes", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_goals", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_assists", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_npxg", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_xa", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("recent_shots", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("season_minutes", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("season_npxg90", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("season_xa90", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("start_prob", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("hot_score", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("avg_rating", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("matches_14d", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("comps", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.uefa_player_id"],
            name="player_form_player_id_players_uefa_player_id_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_id", name=op.f("player_form_pkey")),
    )
    op.create_table(
        "player_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("matchday", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("played", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("final", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.uefa_player_id"],
            name="player_scores_player_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("player_scores_pkey")),
    )
    op.create_index("player_scores_md_idx", "player_scores", ["matchday"], unique=False)
    op.create_index(
        "player_scores_player_md_idx", "player_scores", ["player_id", "matchday"], unique=True
    )
    op.create_table(
        "player_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.Text(), server_default=sa.text("'combined'::text"), nullable=False),
        sa.Column("minutes", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("matches", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("npxg90", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("xag90", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("shots90", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("sca90", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("save_pct", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.uefa_player_id"],
            name="player_stats_player_id_players_uefa_player_id_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("player_stats_pkey")),
    )
    op.create_index(
        "player_stats_player_scope_idx", "player_stats", ["player_id", "scope"], unique=True
    )
    op.create_table(
        "projections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("matchday", sa.Integer(), nullable=False),
        sa.Column("p_start", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("exp_minutes", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("xpts", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("xpts_captain", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("value", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("xpts_high", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("xpts_low", sa.REAL(), server_default=sa.text("0"), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_version", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.uefa_player_id"],
            name="projections_player_id_players_uefa_player_id_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("projections_pkey")),
    )
    op.create_index(
        "projections_player_md_idx", "projections", ["player_id", "matchday"], unique=True
    )
    op.create_table(
        "set_piece_roles",
        sa.Column("player_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("pen_rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("fk_rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ck_rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("'manual'::text"), nullable=False),
        sa.Column("note", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.uefa_player_id"], name="set_piece_roles_player_id_fkey"
        ),
        sa.PrimaryKeyConstraint("player_id", name=op.f("set_piece_roles_pkey")),
    )


def downgrade() -> None:
    op.drop_table("set_piece_roles")
    op.drop_index("projections_player_md_idx", table_name="projections")
    op.drop_table("projections")
    op.drop_index("player_stats_player_scope_idx", table_name="player_stats")
    op.drop_table("player_stats")
    op.drop_index("player_scores_player_md_idx", table_name="player_scores")
    op.drop_index("player_scores_md_idx", table_name="player_scores")
    op.drop_table("player_scores")
    op.drop_table("player_form")
    op.drop_index("my_squad_md_player_idx", table_name="my_squad")
    op.drop_table("my_squad")
    op.drop_index("players_team_idx", table_name="players")
    op.drop_index("players_pos_idx", table_name="players")
    op.drop_table("players")
    op.drop_index("fixtures_md_idx", table_name="fixtures")
    op.drop_table("fixtures")
    op.drop_table("teams")
    op.drop_table("settings")
    op.drop_table("player_id_overrides")
    op.drop_index("live_snapshots_md_idx", table_name="live_snapshots")
    op.drop_table("live_snapshots")
    op.drop_index("league_standings_league_idx", table_name="league_standings")
    op.drop_index("league_standings_key_idx", table_name="league_standings")
    op.drop_table("league_standings")
    op.drop_table("ingest_runs")
    op.drop_index("draft_players_sport_idx", table_name="draft_players")
    op.drop_index("draft_players_pk", table_name="draft_players")
    op.drop_table("draft_players")
    op.drop_index("draft_picks_sport_overall_idx", table_name="draft_picks")
    op.drop_index("draft_picks_player_idx", table_name="draft_picks")
    op.drop_table("draft_picks")
