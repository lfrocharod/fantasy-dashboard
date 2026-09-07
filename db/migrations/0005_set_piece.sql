-- Set-piece duty. `set_piece` on players is the computed best-guess
-- ("PK" / "PK,CK" / "FK" …); `set_piece_roles` is a hand-editable override
-- keyed by player, so you can correct it as pecking orders change.
ALTER TABLE "players" ADD COLUMN "set_piece" text DEFAULT '' NOT NULL;

CREATE TABLE IF NOT EXISTS "set_piece_roles" (
  "player_id" integer PRIMARY KEY REFERENCES "players" ("uefa_player_id"),
  "pen_rank" integer NOT NULL DEFAULT 0,   -- 1 = first-choice penalty taker, 2 = backup
  "fk_rank" integer NOT NULL DEFAULT 0,    -- direct free-kick order
  "ck_rank" integer NOT NULL DEFAULT 0,    -- corner order (assist upside)
  "source" text NOT NULL DEFAULT 'manual',
  "note" text NOT NULL DEFAULT '',
  "updated_at" timestamptz NOT NULL DEFAULT now()
);
