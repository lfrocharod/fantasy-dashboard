"""The database schema, as SQLAlchemy 2.0 typed models.

This module is the single source of truth for the schema: Alembic migrations
(`fantasy/migrations`) are generated from it and CI fails if the two drift
(`alembic check`). The API reads through these models; the bulk writers in
`fantasy.core.db` issue hand-written upserts against the same tables.

Column types mirror what is in production exactly (REAL, not DOUBLE; drizzle's
foreign-key names) so the baseline migration is a no-op there.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NOW = text("now()")
EMPTY = text("''::text")
ZERO = text("0")
FALSE = text("false")
TRUE = text("true")


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "%(table_name)s_pkey",
            "ix": "%(table_name)s_%(column_0_name)s_idx",
            "uq": "%(table_name)s_%(column_0_name)s_key",
            "fk": "%(table_name)s_%(column_0_name)s_fkey",
        }
    )


def _real(default: str = "0") -> Mapped[float]:
    return mapped_column(REAL, nullable=False, server_default=text(default))


def _int0() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=ZERO)


def _text_empty() -> Mapped[str]:
    return mapped_column(Text, nullable=False, server_default=EMPTY)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)


# ---- Champions League -----------------------------------------------------------


class Team(Base):
    """A UCL club, keyed by UEFA's id, with model attack/defence ratings."""

    __tablename__ = "teams"

    uefa_team_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = _text_empty()
    attack_rating: Mapped[float] = _real("1")
    defence_rating: Mapped[float] = _real("1")
    updated_at: Mapped[datetime] = _updated_at()


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        Index("players_team_idx", "team_id"),
        Index("players_pos_idx", "position"),
    )

    uefa_player_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = _text_empty()
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teams.uefa_team_id", name="players_team_id_teams_uefa_team_id_fk"),
        nullable=False,
    )
    position: Mapped[str] = mapped_column(Text, nullable=False)  # GK | DEF | MID | FWD
    price: Mapped[float] = _real()
    uefa_total_points: Mapped[int] = _int0()
    uefa_form: Mapped[float] = _real()
    selected_pct: Mapped[float] = _real()
    status_code: Mapped[int] = _int0()  # 0 fit, 1 doubt, 2 out
    status_detail: Mapped[str] = _text_empty()
    fbref_id: Mapped[str | None] = mapped_column(Text)
    understat_id: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[Any | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = _updated_at()
    # net transfer pressure this matchday, ~-1..+1 (>0: price likely to rise)
    price_momentum: Mapped[float] = _real()
    # set-piece duty best guess: "", "PK", "PK2", "PK,CK", "FK"...
    set_piece: Mapped[str] = _text_empty()


class PlayerStat(Base):
    """Season underlying rates (xG/xA/shots per 90) per competition scope."""

    __tablename__ = "player_stats"
    __table_args__ = (
        Index("player_stats_player_scope_idx", "player_id", "scope", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "players.uefa_player_id",
            name="player_stats_player_id_players_uefa_player_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'combined'::text"))
    minutes: Mapped[float] = _real()
    matches: Mapped[int] = _int0()
    npxg90: Mapped[float] = _real()
    xag90: Mapped[float] = _real()
    shots90: Mapped[float] = _real()
    sca90: Mapped[float] = _real()
    save_pct: Mapped[float] = _real()
    source: Mapped[str] = _text_empty()
    updated_at: Mapped[datetime] = _updated_at()


class PlayerForm(Base):
    """Recent form + role layer (last-N matches across all competitions)."""

    __tablename__ = "player_form"

    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "players.uefa_player_id",
            name="player_form_player_id_players_uefa_player_id_fk",
            ondelete="CASCADE",
        ),
        primary_key=True,
        autoincrement=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'understat'::text"))
    source_team: Mapped[str] = _text_empty()
    team_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=TRUE)
    role: Mapped[str] = _text_empty()
    role_note: Mapped[str] = _text_empty()
    recent_matches: Mapped[int] = _int0()
    recent_starts: Mapped[int] = _int0()
    recent_minutes: Mapped[float] = _real()
    recent_goals: Mapped[float] = _real()
    recent_assists: Mapped[float] = _real()
    recent_npxg: Mapped[float] = _real()
    recent_xa: Mapped[float] = _real()
    recent_shots: Mapped[float] = _real()
    season_minutes: Mapped[float] = _real()
    season_npxg90: Mapped[float] = _real()
    season_xa90: Mapped[float] = _real()
    start_prob: Mapped[float] = _real()
    hot_score: Mapped[float] = _real()
    updated_at: Mapped[datetime] = _updated_at()
    avg_rating: Mapped[float] = _real()
    matches_14d: Mapped[int] = _int0()
    comps: Mapped[str] = _text_empty()


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (Index("fixtures_md_idx", "matchday"),)

    uefa_match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    matchday: Mapped[int] = mapped_column(Integer, nullable=False)
    home_team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teams.uefa_team_id", name="fixtures_home_team_id_teams_uefa_team_id_fk"),
        nullable=False,
    )
    away_team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teams.uefa_team_id", name="fixtures_away_team_id_teams_uefa_team_id_fk"),
        nullable=False,
    )
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'upcoming'::text"))
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    home_xg_est: Mapped[float] = _real()
    away_xg_est: Mapped[float] = _real()
    updated_at: Mapped[datetime] = _updated_at()


class Projection(Base):
    """Per-player, per-matchday expected points. Frozen once the matchday is live."""

    __tablename__ = "projections"
    __table_args__ = (
        Index("projections_player_md_idx", "player_id", "matchday", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "players.uefa_player_id",
            name="projections_player_id_players_uefa_player_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    matchday: Mapped[int] = mapped_column(Integer, nullable=False)
    p_start: Mapped[float] = _real()
    exp_minutes: Mapped[float] = _real()
    xpts: Mapped[float] = _real()
    xpts_captain: Mapped[float] = _real()
    value: Mapped[float] = _real()
    xpts_high: Mapped[float] = _real()
    xpts_low: Mapped[float] = _real()
    components: Mapped[Any | None] = mapped_column(JSONB)
    model_version: Mapped[str] = _text_empty()
    generated_at: Mapped[datetime] = _updated_at()


class PlayerScore(Base):
    """Actual matchday points — the ground truth projections are graded against."""

    __tablename__ = "player_scores"
    __table_args__ = (
        Index("player_scores_player_md_idx", "player_id", "matchday", unique=True),
        Index("player_scores_md_idx", "matchday"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.uefa_player_id", name="player_scores_player_id_fkey", ondelete="CASCADE"),
        nullable=False,
    )
    matchday: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = _int0()
    played: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    updated_at: Mapped[datetime] = _updated_at()


class LiveSnapshot(Base):
    """Point-in-time captures of the live matchday (the in-play points graph)."""

    __tablename__ = "live_snapshots"
    __table_args__ = (Index("live_snapshots_md_idx", "matchday", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    matchday: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = _updated_at()
    secured: Mapped[float] = _real()
    projected: Mapped[float] = _real()
    pre_match: Mapped[float] = _real()
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'live'::text"))
    blob: Mapped[Any | None] = mapped_column(JSONB)


class MySquad(Base):
    __tablename__ = "my_squad"
    __table_args__ = (Index("my_squad_md_player_idx", "matchday", "player_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    matchday: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.uefa_player_id", name="my_squad_player_id_players_uefa_player_id_fk"),
        nullable=False,
    )
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=TRUE)
    is_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    is_vice: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    bench_order: Mapped[int] = _int0()
    purchase_price: Mapped[float] = _real()
    updated_at: Mapped[datetime] = _updated_at()


class LeagueStanding(Base):
    """UCL mini-league table per matchday, with each rival's saved squad."""

    __tablename__ = "league_standings"
    __table_args__ = (
        Index("league_standings_key_idx", "league_id", "entry_id", "matchday", unique=True),
        Index("league_standings_league_idx", "league_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[str] = mapped_column(Text, nullable=False)
    entry_id: Mapped[str] = mapped_column(Text, nullable=False)
    manager_name: Mapped[str] = _text_empty()
    team_name: Mapped[str] = _text_empty()
    matchday: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = _int0()
    total_points: Mapped[int] = _int0()
    rank: Mapped[int] = _int0()
    prev_rank: Mapped[int] = _int0()
    squad: Mapped[Any | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = _updated_at()


class SetPieceRole(Base):
    """Hand-editable set-piece pecking order; wins over the computed guess."""

    __tablename__ = "set_piece_roles"

    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.uefa_player_id", name="set_piece_roles_player_id_fkey"),
        primary_key=True,
        autoincrement=False,
    )
    pen_rank: Mapped[int] = _int0()
    fk_rank: Mapped[int] = _int0()
    ck_rank: Mapped[int] = _int0()
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'::text"))
    note: Mapped[str] = _text_empty()
    updated_at: Mapped[datetime] = _updated_at()


class PlayerIdOverride(Base):
    """Manual identity fixes for the external-stats name matcher."""

    __tablename__ = "player_id_overrides"

    uefa_player_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    fbref_id: Mapped[str | None] = mapped_column(Text)
    understat_id: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str] = _text_empty()


# ---- shared -------------------------------------------------------------------------


class Setting(Base):
    """Small key/value store for configuration (league ids, encrypted cookies,
    model knobs)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = _text_empty()
    updated_at: Mapped[datetime] = _updated_at()


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = _updated_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    stage: Mapped[str] = _text_empty()
    notes: Mapped[str] = _text_empty()


# ---- FPL Draft + ESPN NFL (sport-agnostic draft board) ---------------------------


class DraftPlayer(Base):
    """One row per player per sport. Sport-specific extras ride in `raw`."""

    __tablename__ = "draft_players"
    __table_args__ = (Index("draft_players_sport_idx", "sport"),)

    sport: Mapped[str] = mapped_column(Text, primary_key=True)
    ext_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    team: Mapped[str] = _text_empty()
    positions: Mapped[str] = _text_empty()
    primary_pos: Mapped[str] = _text_empty()
    proj_points: Mapped[float] = _real()
    adp: Mapped[float] = _real()
    provider_rank: Mapped[int | None] = mapped_column(Integer)
    ecr_rank: Mapped[int | None] = mapped_column(Integer)
    ecr_tier: Mapped[int | None] = mapped_column(Integer)
    ecr_pos_rank: Mapped[str] = _text_empty()
    ecr_std: Mapped[float] = _real()
    vbd: Mapped[float] = _real()
    bye_week: Mapped[int | None] = mapped_column(Integer)
    injury_status: Mapped[str] = _text_empty()
    outlook: Mapped[str] = _text_empty()
    raw: Mapped[Any | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = _updated_at()


class DraftPick(Base):
    __tablename__ = "draft_picks"
    __table_args__ = (
        Index("draft_picks_sport_overall_idx", "sport", "overall", unique=True),
        Index("draft_picks_player_idx", "sport", "player_ext_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(Text, nullable=False)
    overall: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = _int0()
    pick_in_round: Mapped[int] = _int0()
    team_id: Mapped[int] = _int0()
    team_name: Mapped[str] = _text_empty()
    player_ext_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_mine: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'::text"))
    created_at: Mapped[datetime] = _updated_at()


# ---- league state (0002) — what used to be JSON strings in `settings` --------------


class League(Base):
    """One row per fantasy game we track: where the season is and how the
    league is configured. Written by each league's sync."""

    __tablename__ = "leagues"

    sport: Mapped[str] = mapped_column(Text, primary_key=True)  # ucl | fpl | nfl
    name: Mapped[str] = _text_empty()
    # UCL matchday / FPL gameweek / NFL week currently being planned for
    current_round: Mapped[int | None] = mapped_column(Integer)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    n_teams: Mapped[int | None] = mapped_column(Integer)
    # FPL: "c" classic / "h" head-to-head; NFL: "ppr" / "half" / "standard"
    scoring: Mapped[str] = _text_empty()
    regular_rounds: Mapped[int | None] = mapped_column(Integer)
    playoff_rounds: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )
    playoff_teams: Mapped[int | None] = mapped_column(Integer)
    seeding_rule: Mapped[str] = _text_empty()  # NFL: H2H_RECORD | TOTAL_POINTS_SCORED
    roster: Mapped[Any | None] = mapped_column(JSONB)  # squad slot counts
    lineup_slots: Mapped[Any | None] = mapped_column(JSONB)  # starting-lineup slots (NFL)
    updated_at: Mapped[datetime] = _updated_at()


class LeagueEntry(Base):
    """A manager/team in an FPL or NFL league, with their standing."""

    __tablename__ = "league_entries"

    sport: Mapped[str] = mapped_column(
        Text, ForeignKey("leagues.sport", ondelete="CASCADE"), primary_key=True
    )
    entry_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = _text_empty()
    is_mine: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    rank: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[float | None] = mapped_column(REAL)
    points_for: Mapped[float | None] = mapped_column(REAL)
    points_against: Mapped[float | None] = mapped_column(REAL)
    wins: Mapped[int | None] = mapped_column(Integer)
    draws: Mapped[int | None] = mapped_column(Integer)
    losses: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = _updated_at()


class Matchup(Base):
    """A head-to-head fixture between two league entries in a round."""

    __tablename__ = "matchups"

    sport: Mapped[str] = mapped_column(
        Text, ForeignKey("leagues.sport", ondelete="CASCADE"), primary_key=True
    )
    round: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    home_entry: Mapped[str] = mapped_column(Text, primary_key=True)
    away_entry: Mapped[str] = mapped_column(Text, primary_key=True)
    home_name: Mapped[str] = _text_empty()
    away_name: Mapped[str] = _text_empty()
    home_points: Mapped[float | None] = mapped_column(REAL)
    away_points: Mapped[float | None] = mapped_column(REAL)
    winner: Mapped[str | None] = mapped_column(Text)  # HOME | AWAY | TIE | UNDECIDED
    finished: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)


class LineupSlot(Base):
    """Your own FPL / NFL roster and the lineup you've set in the game."""

    __tablename__ = "my_lineup"

    sport: Mapped[str] = mapped_column(Text, primary_key=True)
    ext_id: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[int | None] = mapped_column(Integer)  # FPL pick order 1-15
    starter: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    captain: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    vice: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE)
    # FPL: "my-team" (live Pick Team) | "event/N" (last fielded XI); NFL: "espn"
    source: Mapped[str] = _text_empty()


class Document(Base):
    """A computed output the UI always reads whole — the optimizer's advice,
    the live-matchday state, a calibration report. JSON, keyed by name."""

    __tablename__ = "documents"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = _updated_at()
