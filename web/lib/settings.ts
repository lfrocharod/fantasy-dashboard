import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { settings } from "@/lib/db/schema";

/**
 * Typed accessors over the `settings` key/value table. Both the web app and the
 * Python ingestion job read/write these keys, so keep names in sync with
 * ingest/fantasy_ingest/config.py.
 */

export const KEYS = {
  leagueId: "ucl.league_id",
  leagueCode: "ucl.league_code",
  entryId: "ucl.entry_id",
  currentMatchday: "ucl.current_matchday",
  deadline: "ucl.deadline_iso",
  // AES-GCM encrypted (see lib/crypto.ts). One of these is enough for ingestion.
  uefaToken: "ucl.uefa_token_enc",
  uefaTokenSavedAt: "ucl.uefa_token_saved_at",
  uefaAuthState: "ucl.uefa_auth_state", // "credentials_ok" | "token" | "stale" | "unknown"
  // Model knobs, JSON.
  modelParams: "model.params",
  // Latest optimizer result (best XI + transfer suggestions), JSON, written by ingestion.
  optimizerOutput: "model.optimizer_output",
} as const;

export async function getSetting(key: string): Promise<string | null> {
  const row = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, key))
    .limit(1);
  return row[0]?.value ?? null;
}

export async function getSettings(keys: string[]): Promise<Record<string, string>> {
  const rows = await db.select().from(settings);
  const wanted = new Set(keys);
  const out: Record<string, string> = {};
  for (const r of rows) if (wanted.has(r.key)) out[r.key] = r.value;
  return out;
}

export async function setSetting(key: string, value: string): Promise<void> {
  await db
    .insert(settings)
    .values({ key, value, updatedAt: new Date() })
    .onConflictDoUpdate({
      target: settings.key,
      set: { value, updatedAt: new Date() },
    });
}
