import {
  pgTable,
  serial,
  integer,
  bigint,
  text,
  real,
  boolean,
  timestamp,
  jsonb,
  uniqueIndex,
  index,
} from "drizzle-orm/pg-core";

/**
 * All tables are keyed by UEFA's own numeric ids where one exists, so ingestion
 * can upsert idempotently. `*_json` columns hold raw payload slices we haven't
 * modelled yet, so the UI can still surface them without a migration.
 */

export const teams = pgTable("teams", {
  uefaTeamId: integer("uefa_team_id").primaryKey(),
  name: text("name").notNull(),
  code: text("code").notNull().default(""),
  attackRating: real("attack_rating").notNull().default(1),
  defenceRating: real("defence_rating").notNull().default(1),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const players = pgTable(
  "players",
  {
    uefaPlayerId: integer("uefa_player_id").primaryKey(),
    name: text("name").notNull(),
    displayName: text("display_name").notNull().default(""),
    teamId: integer("team_id")
      .notNull()
      .references(() => teams.uefaTeamId),
    // GK | DEF | MID | FWD
    position: text("position").notNull(),
    price: real("price").notNull().default(0),
    uefaTotalPoints: integer("uefa_total_points").notNull().default(0),
    uefaForm: real("uefa_form").notNull().default(0),
    selectedPct: real("selected_pct").notNull().default(0),
    // 0 = fit, 1 = doubt, 2 = out (UEFA "pStatus" style)
    statusCode: integer("status_code").notNull().default(0),
    statusDetail: text("status_detail").notNull().default(""),
    fbrefId: text("fbref_id"),
    understatId: text("understat_id"),
    raw: jsonb("raw"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    byTeam: index("players_team_idx").on(t.teamId),
    byPos: index("players_pos_idx").on(t.position),
  }),
);

/** Rolling underlying numbers from FBref / Understat, per competition scope. */
export const playerStats = pgTable(
  "player_stats",
  {
    id: serial("id").primaryKey(),
    playerId: integer("player_id")
      .notNull()
      .references(() => players.uefaPlayerId, { onDelete: "cascade" }),
    // "ucl" | "domestic" | "combined"
    scope: text("scope").notNull().default("combined"),
    minutes: real("minutes").notNull().default(0),
    matches: integer("matches").notNull().default(0),
    npxg90: real("npxg90").notNull().default(0),
    xag90: real("xag90").notNull().default(0),
    shots90: real("shots90").notNull().default(0),
    sca90: real("sca90").notNull().default(0),
    // GK only
    savePct: real("save_pct").notNull().default(0),
    source: text("source").notNull().default(""),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    uq: uniqueIndex("player_stats_player_scope_idx").on(t.playerId, t.scope),
  }),
);

export const fixtures = pgTable(
  "fixtures",
  {
    uefaMatchId: bigint("uefa_match_id", { mode: "number" }).primaryKey(),
    matchday: integer("matchday").notNull(),
    homeTeamId: integer("home_team_id")
      .notNull()
      .references(() => teams.uefaTeamId),
    awayTeamId: integer("away_team_id")
      .notNull()
      .references(() => teams.uefaTeamId),
    kickoff: timestamp("kickoff", { withTimezone: true }),
    // "upcoming" | "live" | "finished"
    status: text("status").notNull().default("upcoming"),
    homeGoals: integer("home_goals"),
    awayGoals: integer("away_goals"),
    homeXgEst: real("home_xg_est").notNull().default(0),
    awayXgEst: real("away_xg_est").notNull().default(0),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    byMd: index("fixtures_md_idx").on(t.matchday),
  }),
);

export const projections = pgTable(
  "projections",
  {
    id: serial("id").primaryKey(),
    playerId: integer("player_id")
      .notNull()
      .references(() => players.uefaPlayerId, { onDelete: "cascade" }),
    matchday: integer("matchday").notNull(),
    pStart: real("p_start").notNull().default(0),
    expMinutes: real("exp_minutes").notNull().default(0),
    xpts: real("xpts").notNull().default(0),
    xptsCaptain: real("xpts_captain").notNull().default(0),
    // xpts per unit price
    value: real("value").notNull().default(0),
    // ceiling / floor from a small simulation
    xptsHigh: real("xpts_high").notNull().default(0),
    xptsLow: real("xpts_low").notNull().default(0),
    components: jsonb("components"),
    modelVersion: text("model_version").notNull().default(""),
    generatedAt: timestamp("generated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    uq: uniqueIndex("projections_player_md_idx").on(t.playerId, t.matchday),
  }),
);

/** Our own squad as read back from UEFA for a given matchday. */
export const mySquad = pgTable(
  "my_squad",
  {
    id: serial("id").primaryKey(),
    matchday: integer("matchday").notNull(),
    playerId: integer("player_id")
      .notNull()
      .references(() => players.uefaPlayerId),
    isStarter: boolean("is_starter").notNull().default(true),
    isCaptain: boolean("is_captain").notNull().default(false),
    isVice: boolean("is_vice").notNull().default(false),
    benchOrder: integer("bench_order").notNull().default(0),
    purchasePrice: real("purchase_price").notNull().default(0),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    uq: uniqueIndex("my_squad_md_player_idx").on(t.matchday, t.playerId),
  }),
);

export const leagueStandings = pgTable(
  "league_standings",
  {
    id: serial("id").primaryKey(),
    leagueId: text("league_id").notNull(),
    entryId: text("entry_id").notNull(),
    managerName: text("manager_name").notNull().default(""),
    teamName: text("team_name").notNull().default(""),
    matchday: integer("matchday").notNull(),
    points: integer("points").notNull().default(0),
    totalPoints: integer("total_points").notNull().default(0),
    rank: integer("rank").notNull().default(0),
    prevRank: integer("prev_rank").notNull().default(0),
    squad: jsonb("squad"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    uq: uniqueIndex("league_standings_key_idx").on(t.leagueId, t.entryId, t.matchday),
    byLeague: index("league_standings_league_idx").on(t.leagueId),
  }),
);

/** Small key/value store: config + encrypted UEFA session token. */
export const settings = pgTable("settings", {
  key: text("key").primaryKey(),
  value: text("value").notNull().default(""),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const playerIdOverrides = pgTable("player_id_overrides", {
  uefaPlayerId: integer("uefa_player_id").primaryKey(),
  fbrefId: text("fbref_id"),
  understatId: text("understat_id"),
  note: text("note").notNull().default(""),
});

export const ingestRuns = pgTable("ingest_runs", {
  id: serial("id").primaryKey(),
  startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
  ok: boolean("ok").notNull().default(false),
  stage: text("stage").notNull().default(""),
  notes: text("notes").notNull().default(""),
});

export type Team = typeof teams.$inferSelect;
export type Player = typeof players.$inferSelect;
export type Projection = typeof projections.$inferSelect;
export type Fixture = typeof fixtures.$inferSelect;
export type LeagueStanding = typeof leagueStandings.$inferSelect;
