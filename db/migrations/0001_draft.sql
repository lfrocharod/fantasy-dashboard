CREATE TABLE "draft_picks" (
	"id" serial PRIMARY KEY NOT NULL,
	"sport" text NOT NULL,
	"overall" integer NOT NULL,
	"round" integer DEFAULT 0 NOT NULL,
	"pick_in_round" integer DEFAULT 0 NOT NULL,
	"team_id" integer DEFAULT 0 NOT NULL,
	"team_name" text DEFAULT '' NOT NULL,
	"player_ext_id" text NOT NULL,
	"is_mine" boolean DEFAULT false NOT NULL,
	"source" text DEFAULT 'manual' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "draft_players" (
	"sport" text NOT NULL,
	"ext_id" text NOT NULL,
	"name" text NOT NULL,
	"team" text DEFAULT '' NOT NULL,
	"positions" text DEFAULT '' NOT NULL,
	"primary_pos" text DEFAULT '' NOT NULL,
	"proj_points" real DEFAULT 0 NOT NULL,
	"adp" real DEFAULT 0 NOT NULL,
	"provider_rank" integer,
	"ecr_rank" integer,
	"ecr_tier" integer,
	"ecr_pos_rank" text DEFAULT '' NOT NULL,
	"ecr_std" real DEFAULT 0 NOT NULL,
	"vbd" real DEFAULT 0 NOT NULL,
	"bye_week" integer,
	"injury_status" text DEFAULT '' NOT NULL,
	"outlook" text DEFAULT '' NOT NULL,
	"raw" jsonb,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX "draft_picks_sport_overall_idx" ON "draft_picks" USING btree ("sport","overall");--> statement-breakpoint
CREATE INDEX "draft_picks_player_idx" ON "draft_picks" USING btree ("sport","player_ext_id");--> statement-breakpoint
CREATE UNIQUE INDEX "draft_players_pk" ON "draft_players" USING btree ("sport","ext_id");--> statement-breakpoint
CREATE INDEX "draft_players_sport_idx" ON "draft_players" USING btree ("sport");