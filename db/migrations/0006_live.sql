-- Live matchday: actual points per player per matchday (from UEFA's `curGDPts`
-- live feed) + point-in-time captures of the live-state blob.
--
-- `player_scores` is the ground truth the projection model is graded against
-- (`python -m fantasy_ingest.calibrate`) and the basis for live rival scoring.
-- `live_snapshots` powers the in-matchday points graph.
--
-- Applied with `cd web && npm run db:push` (drizzle-kit diffs schema.ts).

CREATE TABLE IF NOT EXISTS "player_scores" (
  "id" serial PRIMARY KEY,
  "player_id" integer NOT NULL REFERENCES "players" ("uefa_player_id") ON DELETE cascade,
  "matchday" integer NOT NULL,
  "points" integer NOT NULL DEFAULT 0,
  "played" boolean NOT NULL DEFAULT false,
  "final" boolean NOT NULL DEFAULT false,   -- their fixture has finished
  "updated_at" timestamptz NOT NULL DEFAULT now()
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS "player_scores_player_md_idx" ON "player_scores" ("player_id", "matchday");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "player_scores_md_idx" ON "player_scores" ("matchday");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "live_snapshots" (
  "id" serial PRIMARY KEY,
  "matchday" integer NOT NULL,
  "captured_at" timestamptz NOT NULL DEFAULT now(),
  "secured" real NOT NULL DEFAULT 0,
  "projected" real NOT NULL DEFAULT 0,
  "pre_match" real NOT NULL DEFAULT 0,
  "state" text NOT NULL DEFAULT 'live',
  "blob" jsonb
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "live_snapshots_md_idx" ON "live_snapshots" ("matchday", "captured_at");
