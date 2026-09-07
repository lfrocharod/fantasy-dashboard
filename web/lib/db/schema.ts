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
    // net transfer pressure this matchday, ~-1..+1: >0 → price likely to rise
    priceMomentum: real("price_momentum").notNull().default(0),
    // 0 = fit, 1 = doubt, 2 = out (UEFA "pStatus" style)
    statusCode: integer("status_code").notNull().default(0),
    statusDetail: text("status_detail").notNull().default(""),
    // set-piece duty best-guess: "", "PK", "PK2", "PK,CK", "FK" …
    setPiece: text("set_piece").notNull().default(""),
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

/**
 * Enhanced form + role layer from Understat (domestic leagues). Drives the
 * projection blend and the "who will actually start" view. One row per UEFA
 * player we could match.
 */
export const playerForm = pgTable("player_form", {
  playerId: integer("player_id")
    .primaryKey()
    .references(() => players.uefaPlayerId, { onDelete: "cascade" }),
  source: text("source").notNull().default("understat"),
  // where the source currently has them playing (name), and whether that matches
  // the UEFA team — false => probably transferred, exclude from recommendations.
  sourceTeam: text("source_team").notNull().default(""),
  teamOk: boolean("team_ok").notNull().default(true),
  // position they've ACTUALLY been playing: GK|DEF|MID|FWD  (may differ from UEFA)
  role: text("role").notNull().default(""),
  roleNote: text("role_note").notNull().default(""),
  // last-N (default 4) match aggregates
  recentMatches: integer("recent_matches").notNull().default(0),
  recentStarts: integer("recent_starts").notNull().default(0),
  recentMinutes: real("recent_minutes").notNull().default(0),
  recentGoals: real("recent_goals").notNull().default(0),
  recentAssists: real("recent_assists").notNull().default(0),
  recentNpxg: real("recent_npxg").notNull().default(0),
  recentXa: real("recent_xa").notNull().default(0),
  recentShots: real("recent_shots").notNull().default(0),
  // season per-90
  seasonMinutes: real("season_minutes").notNull().default(0),
  seasonNpxg90: real("season_npxg90").notNull().default(0),
  seasonXa90: real("season_xa90").notNull().default(0),
  // 0..1 — data-driven estimate; the model uses it, the UI shows it
  startProb: real("start_prob").notNull().default(0),
  hotScore: real("hot_score").notNull().default(0),
  // average match rating over the window (Sofascore, ~0-10)
  avgRating: real("avg_rating").notNull().default(0),
  // matches played in the last 14 days (fixture congestion / rotation risk)
  matches14d: integer("matches_14d").notNull().default(0),
  // competitions the recent matches came from, comma-joined
  comps: text("comps").notNull().default(""),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export type PlayerForm = typeof playerForm.$inferSelect;

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

/* ------------------------------------------------------------------ *
 * Draft assistant — sport-agnostic. sport = "nfl" | "nba" | "fpl".
 * ------------------------------------------------------------------ */

export const draftPlayers = pgTable(
  "draft_players",
  {
    sport: text("sport").notNull(),
    extId: text("ext_id").notNull(), // provider id (ESPN player id, FPL element, …)
    name: text("name").notNull(),
    team: text("team").notNull().default(""),
    // comma-separated eligible positions, e.g. "RB,FLEX"
    positions: text("positions").notNull().default(""),
    primaryPos: text("primary_pos").notNull().default(""),
    projPoints: real("proj_points").notNull().default(0),
    adp: real("adp").notNull().default(0),
    // provider's own draft rank (ESPN PPR rank, etc.)
    providerRank: integer("provider_rank"),
    // FantasyPros expert consensus rank + tier + disagreement (higher std = more contested)
    ecrRank: integer("ecr_rank"),
    ecrTier: integer("ecr_tier"),
    ecrPosRank: text("ecr_pos_rank").notNull().default(""),
    ecrStd: real("ecr_std").notNull().default(0),
    // points over replacement for the configured roster
    vbd: real("vbd").notNull().default(0),
    byeWeek: integer("bye_week"),
    injuryStatus: text("injury_status").notNull().default(""),
    outlook: text("outlook").notNull().default(""),
    raw: jsonb("raw"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    pk: uniqueIndex("draft_players_pk").on(t.sport, t.extId),
    bySport: index("draft_players_sport_idx").on(t.sport),
  }),
);

export const draftPicks = pgTable(
  "draft_picks",
  {
    id: serial("id").primaryKey(),
    sport: text("sport").notNull(),
    overall: integer("overall").notNull(),
    round: integer("round").notNull().default(0),
    pickInRound: integer("pick_in_round").notNull().default(0),
    teamId: integer("team_id").notNull().default(0),
    teamName: text("team_name").notNull().default(""),
    playerExtId: text("player_ext_id").notNull(),
    isMine: boolean("is_mine").notNull().default(false),
    source: text("source").notNull().default("manual"), // manual | espn
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    uq: uniqueIndex("draft_picks_sport_overall_idx").on(t.sport, t.overall),
    byPlayer: index("draft_picks_player_idx").on(t.sport, t.playerExtId),
  }),
);

export type DraftPlayer = typeof draftPlayers.$inferSelect;
export type DraftPick = typeof draftPicks.$inferSelect;

export type Team = typeof teams.$inferSelect;
export type Player = typeof players.$inferSelect;
export type Projection = typeof projections.$inferSelect;
export type Fixture = typeof fixtures.$inferSelect;
export type LeagueStanding = typeof leagueStandings.$inferSelect;
