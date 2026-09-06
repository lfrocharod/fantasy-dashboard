import { and, asc, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { draftPicks, draftPlayers } from "@/lib/db/schema";
import { getSettings } from "@/lib/settings";

export type Sport = "nfl" | "nba" | "fpl";

export interface DraftConfig {
  sport: Sport;
  teams: number;
  mySlot: number | null; // 1-based draft position
  myTeamId: number | null;
  roster: Record<string, number>;
  scoring: string;
  hasCookies: boolean;
  year: number;
}

const DEFAULT_ROSTER: Record<string, number> = {
  QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BE: 6,
};

function k(sport: string, key: string) {
  return `draft.${sport}.${key}`;
}

export async function getDraftConfig(sport: Sport): Promise<DraftConfig> {
  const s = await getSettings([
    k(sport, "teams"), k(sport, "my_slot"), k(sport, "my_team_id"),
    k(sport, "roster"), k(sport, "scoring"), k(sport, "year"),
    k(sport, "espn_s2"), k(sport, "swid"), k(sport, "league_id"),
  ]);
  let roster = DEFAULT_ROSTER;
  try {
    if (s[k(sport, "roster")]) roster = JSON.parse(s[k(sport, "roster")]);
  } catch {
    /* keep default */
  }
  return {
    sport,
    teams: Number(s[k(sport, "teams")]) || 12,
    mySlot: s[k(sport, "my_slot")] ? Number(s[k(sport, "my_slot")]) : null,
    myTeamId: s[k(sport, "my_team_id")] ? Number(s[k(sport, "my_team_id")]) : null,
    roster,
    scoring: s[k(sport, "scoring")] || "ppr",
    hasCookies: Boolean(s[k(sport, "espn_s2")] && s[k(sport, "swid")]),
    year: Number(s[k(sport, "year")]) || 2026,
  };
}

export async function getBoard(sport: Sport) {
  const [players, picks, config] = await Promise.all([
    db.select().from(draftPlayers).where(eq(draftPlayers.sport, sport)),
    db
      .select()
      .from(draftPicks)
      .where(eq(draftPicks.sport, sport))
      .orderBy(asc(draftPicks.overall)),
    getDraftConfig(sport),
  ]);
  return { players, picks, config };
}

export async function addManualPick(sport: Sport, extId: string, opts: {
  isMine?: boolean;
  teamId?: number;
  teamName?: string;
}) {
  const existing = await db
    .select({ overall: draftPicks.overall })
    .from(draftPicks)
    .where(eq(draftPicks.sport, sport))
    .orderBy(asc(draftPicks.overall));
  const nextOverall = (existing.at(-1)?.overall ?? 0) + 1;
  await db
    .insert(draftPicks)
    .values({
      sport,
      overall: nextOverall,
      playerExtId: extId,
      isMine: opts.isMine ?? false,
      teamId: opts.teamId ?? 0,
      teamName: opts.teamName ?? (opts.isMine ? "Me" : ""),
      source: "manual",
    })
    .onConflictDoNothing();
  return nextOverall;
}

export async function undoLastManualPick(sport: Sport) {
  const rows = await db
    .select()
    .from(draftPicks)
    .where(and(eq(draftPicks.sport, sport), eq(draftPicks.source, "manual")))
    .orderBy(asc(draftPicks.overall));
  const last = rows.at(-1);
  if (!last) return false;
  await db.delete(draftPicks).where(eq(draftPicks.id, last.id));
  return true;
}

export async function resetPicks(sport: Sport) {
  await db.delete(draftPicks).where(eq(draftPicks.sport, sport));
}
