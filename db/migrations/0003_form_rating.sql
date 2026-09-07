ALTER TABLE "player_form" ADD COLUMN "avg_rating" real DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE "player_form" ADD COLUMN "matches_14d" integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE "player_form" ADD COLUMN "comps" text DEFAULT '' NOT NULL;