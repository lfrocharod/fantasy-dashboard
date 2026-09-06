import { and, desc, eq, gte, inArray, lte, sql } from "drizzle-orm";
import { alias } from "drizzle-orm/pg-core";
import { db } from "@/lib/db";
import {
  fixtures,
  ingestRuns,
  leagueStandings,
  mySquad,
  players,
  projections,
  teams,
} from "@/lib/db/schema";
import { getSettings, KEYS } from "@/lib/settings";
import type { Position } from "./formation";

export interface PlayerRow {
  playerId: number;
  name: string;
  position: Position;
  teamId: number;
  teamName: string;
  price: number;
  selectedPct: number;
  statusCode: number;
  statusDetail: string;
  uefaForm: number;
  xpts: number | null;
  xptsCaptain: number | null;
  value: number | null;
  pStart: number | null;
  expMinutes: number | null;
  components: unknown;
}

const playerSelect = {
  playerId: players.uefaPlayerId,
  name: players.name,
  position: players.position,
  teamId: players.teamId,
  teamName: teams.name,
  price: players.price,
  selectedPct: players.selectedPct,
  statusCode: players.statusCode,
  statusDetail: players.statusDetail,
  uefaForm: players.uefaForm,
  xpts: projections.xpts,
  xptsCaptain: projections.xptsCaptain,
  value: projections.value,
  pStart: projections.pStart,
  expMinutes: projections.expMinutes,
  components: projections.components,
} as const;

export async function getCurrentMatchday(): Promise<number> {
  const s = await getSettings([KEYS.currentMatchday]);
  const md = Number(s[KEYS.currentMatchday]);
  if (Number.isFinite(md) && md > 0) return md;
  // Fallback: highest matchday we have any fixture for.
  const row = await db
    .select({ md: sql<number>`max(${fixtures.matchday})` })
    .from(fixtures);
  return row[0]?.md ?? 1;
}

export async function getProjectedPlayers(opts: {
  matchday: number;
  position?: Position;
  maxPrice?: number;
  minPrice?: number;
  search?: string;
  limit?: number;
}): Promise<PlayerRow[]> {
  const conds = [eq(projections.matchday, opts.matchday)];
  if (opts.position) conds.push(eq(players.position, opts.position));
  if (opts.maxPrice != null) conds.push(lte(players.price, opts.maxPrice));
  if (opts.minPrice != null) conds.push(gte(players.price, opts.minPrice));
  if (opts.search) conds.push(sql`${players.name} ilike ${"%" + opts.search + "%"}`);

  const rows = await db
    .select(playerSelect)
    .from(players)
    .innerJoin(teams, eq(teams.uefaTeamId, players.teamId))
    .leftJoin(
      projections,
      and(eq(projections.playerId, players.uefaPlayerId), eq(projections.matchday, opts.matchday)),
    )
    .where(and(...conds))
    .orderBy(desc(projections.xpts))
    .limit(opts.limit ?? 100);

  return rows as PlayerRow[];
}

export interface SquadRow extends PlayerRow {
  isStarter: boolean;
  isCaptain: boolean;
  isVice: boolean;
  benchOrder: number;
  purchasePrice: number;
}

export async function getMySquad(matchday: number): Promise<SquadRow[]> {
  const rows = await db
    .select({
      ...playerSelect,
      isStarter: mySquad.isStarter,
      isCaptain: mySquad.isCaptain,
      isVice: mySquad.isVice,
      benchOrder: mySquad.benchOrder,
      purchasePrice: mySquad.purchasePrice,
    })
    .from(mySquad)
    .innerJoin(players, eq(players.uefaPlayerId, mySquad.playerId))
    .innerJoin(teams, eq(teams.uefaTeamId, players.teamId))
    .leftJoin(
      projections,
      and(eq(projections.playerId, players.uefaPlayerId), eq(projections.matchday, matchday)),
    )
    .where(eq(mySquad.matchday, matchday));

  return rows as SquadRow[];
}

export async function getFixtures(matchday: number) {
  const home = alias(teams, "home_team");
  const away = alias(teams, "away_team");
  return db
    .select({
      matchId: fixtures.uefaMatchId,
      matchday: fixtures.matchday,
      kickoff: fixtures.kickoff,
      status: fixtures.status,
      homeTeam: home.name,
      awayTeam: away.name,
      homeXg: fixtures.homeXgEst,
      awayXg: fixtures.awayXgEst,
      homeGoals: fixtures.homeGoals,
      awayGoals: fixtures.awayGoals,
    })
    .from(fixtures)
    .innerJoin(home, eq(home.uefaTeamId, fixtures.homeTeamId))
    .innerJoin(away, eq(away.uefaTeamId, fixtures.awayTeamId))
    .where(eq(fixtures.matchday, matchday))
    .orderBy(fixtures.kickoff);
}

export async function getLeagueTable(matchday: number) {
  const s = await getSettings([KEYS.leagueId, KEYS.entryId]);
  const leagueId = s[KEYS.leagueId];
  if (!leagueId) return { leagueId: null, rows: [], myEntryId: null };

  const rows = await db
    .select()
    .from(leagueStandings)
    .where(and(eq(leagueStandings.leagueId, leagueId), eq(leagueStandings.matchday, matchday)))
    .orderBy(leagueStandings.rank);

  return { leagueId, myEntryId: s[KEYS.entryId] ?? null, rows };
}

/** Points-by-matchday history for every entry, for analytics / power rankings. */
export async function getLeagueHistory() {
  const s = await getSettings([KEYS.leagueId, KEYS.entryId]);
  const leagueId = s[KEYS.leagueId];
  if (!leagueId) return { leagueId: null, myEntryId: null, rows: [] };
  const rows = await db
    .select({
      entryId: leagueStandings.entryId,
      managerName: leagueStandings.managerName,
      teamName: leagueStandings.teamName,
      matchday: leagueStandings.matchday,
      points: leagueStandings.points,
      totalPoints: leagueStandings.totalPoints,
      rank: leagueStandings.rank,
    })
    .from(leagueStandings)
    .where(eq(leagueStandings.leagueId, leagueId))
    .orderBy(leagueStandings.matchday, leagueStandings.rank);
  return { leagueId, myEntryId: s[KEYS.entryId] ?? null, rows };
}

export async function getIngestHealth() {
  const row = await db
    .select()
    .from(ingestRuns)
    .orderBy(desc(ingestRuns.startedAt))
    .limit(1);
  return row[0] ?? null;
}

export async function getDashboardSummary() {
  const md = await getCurrentMatchday();
  const s = await getSettings([KEYS.deadline, KEYS.entryId, KEYS.uefaAuthState, KEYS.uefaTokenSavedAt]);
  const [squad, table, health, fx] = await Promise.all([
    getMySquad(md),
    getLeagueTable(md),
    getIngestHealth(),
    getFixtures(md),
  ]);

  const myRow = table.rows.find((r) => r.entryId === table.myEntryId) ?? null;
  const projectedXI = topXIByXpts(squad);

  return {
    matchday: md,
    deadlineIso: s[KEYS.deadline] ?? null,
    authState: s[KEYS.uefaAuthState] ?? "unknown",
    tokenSavedAt: s[KEYS.uefaTokenSavedAt] ?? null,
    squadValue: round(squad.reduce((a, r) => a + (r.price || 0), 0)),
    squadSize: squad.length,
    projectedPoints: round(
      projectedXI.reduce((a, r) => a + (r.xpts ?? 0), 0) +
        (projectedXI.find((r) => r.isCaptain)?.xpts ?? maxXpts(projectedXI)),
    ),
    myRank: myRow?.rank ?? null,
    myPointsLast: myRow?.points ?? null,
    myTotalPoints: myRow?.totalPoints ?? null,
    leagueSize: table.rows.length,
    fixtureCount: fx.length,
    ingest: health
      ? { ok: health.ok, stage: health.stage, at: health.finishedAt ?? health.startedAt, notes: health.notes }
      : null,
  };
}

function maxXpts(rows: { xpts: number | null }[]): number {
  return rows.reduce((m, r) => Math.max(m, r.xpts ?? 0), 0);
}

function topXIByXpts(squad: SquadRow[]): SquadRow[] {
  // Cheap heuristic for the dashboard card only; the real optimizer is in Python.
  return [...squad].sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)).slice(0, 11);
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}

export async function playersByIds(ids: number[]): Promise<PlayerRow[]> {
  if (ids.length === 0) return [];
  const rows = await db
    .select(playerSelect)
    .from(players)
    .innerJoin(teams, eq(teams.uefaTeamId, players.teamId))
    .leftJoin(projections, eq(projections.playerId, players.uefaPlayerId))
    .where(inArray(players.uefaPlayerId, ids));
  return rows as PlayerRow[];
}
