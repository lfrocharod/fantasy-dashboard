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
  // FPL Draft
  entryId: string | null;
  mySquad: string[]; // element ext ids
  standings: unknown[];
  schedule: unknown[];
  fplMode: string; // 'c' classic / 'h' head-to-head
  // NFL in-season
  nflWeek: number;
  nflPlayoffWeeks: number[];
  nflSlots: Record<string, number>;
  nflMyRoster: string[];
}

const DEFAULT_ROSTER: Record<string, number> = {
  QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BE: 6,
};

function k(sport: string, key: string) {
  return `draft.${sport}.${key}`;
}

const FPL_ROSTER: Record<string, number> = { GKP: 2, DEF: 5, MID: 5, FWD: 3 };

function jsonArr(v: string | undefined): unknown[] {
  try { return v ? JSON.parse(v) : []; } catch { return []; }
}
function jsonObj(v: string | undefined): Record<string, number> {
  try { return v ? JSON.parse(v) : {}; } catch { return {}; }
}

export async function getDraftConfig(sport: Sport): Promise<DraftConfig> {
  const s = await getSettings([
    k(sport, "teams"), k(sport, "my_slot"), k(sport, "my_team_id"),
    k(sport, "roster"), k(sport, "scoring"), k(sport, "year"),
    k(sport, "espn_s2"), k(sport, "swid"), k(sport, "league_id"),
    k(sport, "entry_id"), k(sport, "pl_profile"),
    k(sport, "my_squad"), k(sport, "standings"), k(sport, "schedule"), k(sport, "mode"),
    k(sport, "week"), k(sport, "playoff_weeks"), k(sport, "slots"), k(sport, "my_roster"),
  ]);
  const fpl = sport === "fpl";
  let roster = fpl ? FPL_ROSTER : DEFAULT_ROSTER;
  try {
    if (s[k(sport, "roster")]) roster = JSON.parse(s[k(sport, "roster")]);
  } catch {
    /* keep default */
  }
  let mySquad: string[] = [];
  let standings: unknown[] = [];
  let schedule: unknown[] = [];
  try {
    if (s[k(sport, "my_squad")]) mySquad = JSON.parse(s[k(sport, "my_squad")]);
  } catch {
    /* ignore */
  }
  try {
    if (s[k(sport, "standings")]) standings = JSON.parse(s[k(sport, "standings")]);
  } catch {
    /* ignore */
  }
  try {
    if (s[k(sport, "schedule")]) schedule = JSON.parse(s[k(sport, "schedule")]);
  } catch {
    /* ignore */
  }
  return {
    sport,
    teams: Number(s[k(sport, "teams")]) || (fpl ? 8 : 12),
    mySlot: s[k(sport, "my_slot")] ? Number(s[k(sport, "my_slot")]) : null,
    myTeamId: s[k(sport, "my_team_id")] ? Number(s[k(sport, "my_team_id")]) : null,
    roster,
    scoring: s[k(sport, "scoring")] || (fpl ? "draft" : "ppr"),
    hasCookies: fpl
      ? Boolean(s[k(sport, "pl_profile")])
      : Boolean(s[k(sport, "espn_s2")] && s[k(sport, "swid")]),
    year: Number(s[k(sport, "year")]) || 2026,
    entryId: s[k(sport, "entry_id")] ?? null,
    mySquad,
    standings,
    schedule,
    fplMode: s[k(sport, "mode")] || "c",
    nflWeek: Number(s[k(sport, "week")]) || 1,
    nflPlayoffWeeks: jsonArr(s[k(sport, "playoff_weeks")]) as number[],
    nflSlots: jsonObj(s[k(sport, "slots")]),
    nflMyRoster: jsonArr(s[k(sport, "my_roster")]) as string[],
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
