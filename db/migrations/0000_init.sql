CREATE TABLE "fixtures" (
	"uefa_match_id" bigint PRIMARY KEY NOT NULL,
	"matchday" integer NOT NULL,
	"home_team_id" integer NOT NULL,
	"away_team_id" integer NOT NULL,
	"kickoff" timestamp with time zone,
	"status" text DEFAULT 'upcoming' NOT NULL,
	"home_goals" integer,
	"away_goals" integer,
	"home_xg_est" real DEFAULT 0 NOT NULL,
	"away_xg_est" real DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "ingest_runs" (
	"id" serial PRIMARY KEY NOT NULL,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone,
	"ok" boolean DEFAULT false NOT NULL,
	"stage" text DEFAULT '' NOT NULL,
	"notes" text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "league_standings" (
	"id" serial PRIMARY KEY NOT NULL,
	"league_id" text NOT NULL,
	"entry_id" text NOT NULL,
	"manager_name" text DEFAULT '' NOT NULL,
	"team_name" text DEFAULT '' NOT NULL,
	"matchday" integer NOT NULL,
	"points" integer DEFAULT 0 NOT NULL,
	"total_points" integer DEFAULT 0 NOT NULL,
	"rank" integer DEFAULT 0 NOT NULL,
	"prev_rank" integer DEFAULT 0 NOT NULL,
	"squad" jsonb,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "my_squad" (
	"id" serial PRIMARY KEY NOT NULL,
	"matchday" integer NOT NULL,
	"player_id" integer NOT NULL,
	"is_starter" boolean DEFAULT true NOT NULL,
	"is_captain" boolean DEFAULT false NOT NULL,
	"is_vice" boolean DEFAULT false NOT NULL,
	"bench_order" integer DEFAULT 0 NOT NULL,
	"purchase_price" real DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "player_id_overrides" (
	"uefa_player_id" integer PRIMARY KEY NOT NULL,
	"fbref_id" text,
	"understat_id" text,
	"note" text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "player_stats" (
	"id" serial PRIMARY KEY NOT NULL,
	"player_id" integer NOT NULL,
	"scope" text DEFAULT 'combined' NOT NULL,
	"minutes" real DEFAULT 0 NOT NULL,
	"matches" integer DEFAULT 0 NOT NULL,
	"npxg90" real DEFAULT 0 NOT NULL,
	"xag90" real DEFAULT 0 NOT NULL,
	"shots90" real DEFAULT 0 NOT NULL,
	"sca90" real DEFAULT 0 NOT NULL,
	"save_pct" real DEFAULT 0 NOT NULL,
	"source" text DEFAULT '' NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "players" (
	"uefa_player_id" integer PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"display_name" text DEFAULT '' NOT NULL,
	"team_id" integer NOT NULL,
	"position" text NOT NULL,
	"price" real DEFAULT 0 NOT NULL,
	"uefa_total_points" integer DEFAULT 0 NOT NULL,
	"uefa_form" real DEFAULT 0 NOT NULL,
	"selected_pct" real DEFAULT 0 NOT NULL,
	"status_code" integer DEFAULT 0 NOT NULL,
	"status_detail" text DEFAULT '' NOT NULL,
	"fbref_id" text,
	"understat_id" text,
	"raw" jsonb,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "projections" (
	"id" serial PRIMARY KEY NOT NULL,
	"player_id" integer NOT NULL,
	"matchday" integer NOT NULL,
	"p_start" real DEFAULT 0 NOT NULL,
	"exp_minutes" real DEFAULT 0 NOT NULL,
	"xpts" real DEFAULT 0 NOT NULL,
	"xpts_captain" real DEFAULT 0 NOT NULL,
	"value" real DEFAULT 0 NOT NULL,
	"xpts_high" real DEFAULT 0 NOT NULL,
	"xpts_low" real DEFAULT 0 NOT NULL,
	"components" jsonb,
	"model_version" text DEFAULT '' NOT NULL,
	"generated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "settings" (
	"key" text PRIMARY KEY NOT NULL,
	"value" text DEFAULT '' NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "teams" (
	"uefa_team_id" integer PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"code" text DEFAULT '' NOT NULL,
	"attack_rating" real DEFAULT 1 NOT NULL,
	"defence_rating" real DEFAULT 1 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "fixtures" ADD CONSTRAINT "fixtures_home_team_id_teams_uefa_team_id_fk" FOREIGN KEY ("home_team_id") REFERENCES "public"."teams"("uefa_team_id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "fixtures" ADD CONSTRAINT "fixtures_away_team_id_teams_uefa_team_id_fk" FOREIGN KEY ("away_team_id") REFERENCES "public"."teams"("uefa_team_id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "my_squad" ADD CONSTRAINT "my_squad_player_id_players_uefa_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."players"("uefa_player_id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player_stats" ADD CONSTRAINT "player_stats_player_id_players_uefa_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."players"("uefa_player_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "players" ADD CONSTRAINT "players_team_id_teams_uefa_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("uefa_team_id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "projections" ADD CONSTRAINT "projections_player_id_players_uefa_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."players"("uefa_player_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "fixtures_md_idx" ON "fixtures" USING btree ("matchday");--> statement-breakpoint
CREATE UNIQUE INDEX "league_standings_key_idx" ON "league_standings" USING btree ("league_id","entry_id","matchday");--> statement-breakpoint
CREATE INDEX "league_standings_league_idx" ON "league_standings" USING btree ("league_id");--> statement-breakpoint
CREATE UNIQUE INDEX "my_squad_md_player_idx" ON "my_squad" USING btree ("matchday","player_id");--> statement-breakpoint
CREATE UNIQUE INDEX "player_stats_player_scope_idx" ON "player_stats" USING btree ("player_id","scope");--> statement-breakpoint
CREATE INDEX "players_team_idx" ON "players" USING btree ("team_id");--> statement-breakpoint
CREATE INDEX "players_pos_idx" ON "players" USING btree ("position");--> statement-breakpoint
CREATE UNIQUE INDEX "projections_player_md_idx" ON "projections" USING btree ("player_id","matchday");