CREATE TABLE "player_form" (
	"player_id" integer PRIMARY KEY NOT NULL,
	"source" text DEFAULT 'understat' NOT NULL,
	"source_team" text DEFAULT '' NOT NULL,
	"team_ok" boolean DEFAULT true NOT NULL,
	"role" text DEFAULT '' NOT NULL,
	"role_note" text DEFAULT '' NOT NULL,
	"recent_matches" integer DEFAULT 0 NOT NULL,
	"recent_starts" integer DEFAULT 0 NOT NULL,
	"recent_minutes" real DEFAULT 0 NOT NULL,
	"recent_goals" real DEFAULT 0 NOT NULL,
	"recent_assists" real DEFAULT 0 NOT NULL,
	"recent_npxg" real DEFAULT 0 NOT NULL,
	"recent_xa" real DEFAULT 0 NOT NULL,
	"recent_shots" real DEFAULT 0 NOT NULL,
	"season_minutes" real DEFAULT 0 NOT NULL,
	"season_npxg90" real DEFAULT 0 NOT NULL,
	"season_xa90" real DEFAULT 0 NOT NULL,
	"start_prob" real DEFAULT 0 NOT NULL,
	"hot_score" real DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "player_form" ADD CONSTRAINT "player_form_player_id_players_uefa_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."players"("uefa_player_id") ON DELETE cascade ON UPDATE no action;