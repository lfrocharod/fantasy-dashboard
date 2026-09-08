import { and, desc, eq, gte, inArray, lte, sql } from "drizzle-orm";
import { alias } from "drizzle-orm/pg-core";
import { db } from "@/lib/db";
import {
  fixtures,
  ingestRuns,
  leagueStandings,
  mySquad,
  playerForm,
  players,
  projections,
  teams,
} from "@/lib/db/schema";
import { getSettings, KEYS } from "@/lib/settings";
import { posFdr } from "@/lib/fdr";
import { pickFormationXI } from "@/lib/xi";
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
  // enhanced form layer (may be null if Understat had no match)
  priceMomentum: number;
  setPiece: string;
  role: string | null;
  roleNote: string | null;
  teamOk: boolean | null;
  startProb: number | null;
  hotScore: number | null;
  avgRating: number | null;
  matches14d: number | null;
  comps: string | null;
  recentGoals: number | null;
  recentAssists: number | null;
  recentStarts: number | null;
  recentMatches: number | null;
}

const playerSelect = {
  playerId: players.uefaPlayerId,
  name: players.name,
  position: players.position,
  teamId: players.teamId,
  teamName: teams.name,
  price: players.price,
  selectedPct: players.selectedPct,
  priceMomentum: players.priceMomentum,
  statusCode: players.statusCode,
  statusDetail: players.statusDetail,
  setPiece: players.setPiece,
  uefaForm: players.uefaForm,
  xpts: projections.xpts,
  xptsCaptain: projections.xptsCaptain,
  value: projections.value,
  pStart: projections.pStart,
  expMinutes: projections.expMinutes,
  components: projections.components,
  role: playerForm.role,
  roleNote: playerForm.roleNote,
  teamOk: playerForm.teamOk,
  startProb: playerForm.startProb,
  hotScore: playerForm.hotScore,
  avgRating: playerForm.avgRating,
  matches14d: playerForm.matches14d,
  comps: playerForm.comps,
  recentGoals: playerForm.recentGoals,
  recentAssists: playerForm.recentAssists,
  recentStarts: playerForm.recentStarts,
  recentMatches: playerForm.recentMatches,
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
    .leftJoin(playerForm, eq(playerForm.playerId, players.uefaPlayerId))
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
    .leftJoin(playerForm, eq(playerForm.playerId, players.uefaPlayerId))
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
      homeAtk: home.attackRating,
      homeDef: home.defenceRating,
      awayAtk: away.attackRating,
      awayDef: away.defenceRating,
    })
    .from(fixtures)
    .innerJoin(home, eq(home.uefaTeamId, fixtures.homeTeamId))
    .innerJoin(away, eq(away.uefaTeamId, fixtures.awayTeamId))
    .where(eq(fixtures.matchday, matchday))
    .orderBy(fixtures.kickoff);
}

export interface TickerCell {
  matchday: number;
  opp: string;
  oppCode: string;
  home: boolean;
  difficulty: number; // 1 (easiest) .. 5 (hardest) — blended
  attDifficulty: number; // for attackers (getting goals/assists)
  defDifficulty: number; // for keepers/defenders (clean sheet)
  kickoff: Date | null;
}

export interface TickerRow {
  teamId: number;
  team: string;
  code: string;
  cells: TickerCell[];
  avgDifficulty: number;
}

/**
 * Colour-coded fixture difficulty for every team over the next `ahead` matchdays.
 * Difficulty blends the opponent's attack rating (clean-sheet risk) and the
 * inverse of their defence rating (how hard to get attacking returns), nudged
 * for home/away. 1 = green (easy) … 5 = red (brutal).
 */
export async function getFixtureTicker(fromMatchday: number, ahead = 5): Promise<TickerRow[]> {
  const toMd = fromMatchday + ahead - 1;
  const home = alias(teams, "home_team");
  const away = alias(teams, "away_team");
  const fx = await db
    .select({
      matchday: fixtures.matchday,
      kickoff: fixtures.kickoff,
      homeId: fixtures.homeTeamId,
      awayId: fixtures.awayTeamId,
      homeName: home.name,
      awayName: away.name,
      homeCode: home.code,
      awayCode: away.code,
      homeAtk: home.attackRating,
      homeDef: home.defenceRating,
      awayAtk: away.attackRating,
      awayDef: away.defenceRating,
    })
    .from(fixtures)
    .innerJoin(home, eq(home.uefaTeamId, fixtures.homeTeamId))
    .innerJoin(away, eq(away.uefaTeamId, fixtures.awayTeamId))
    .where(and(gte(fixtures.matchday, fromMatchday), lte(fixtures.matchday, toMd)))
    .orderBy(fixtures.matchday, fixtures.kickoff);

  const rate = (oppAtk: number, oppDef: number, isHome: boolean) => {
    const raw = 0.55 * (oppAtk - 1) + 0.55 * (1 - oppDef) + (isHome ? -0.35 : 0.35);
    return Math.max(1, Math.min(5, Math.round(3 + 2.2 * raw)));
  };

  const rows = new Map<number, TickerRow>();
  const ensure = (id: number, name: string, code: string) => {
    let r = rows.get(id);
    if (!r) {
      r = { teamId: id, team: name, code: code ?? "", cells: [], avgDifficulty: 0 };
      rows.set(id, r);
    }
    return r;
  };

  for (const f of fx) {
    const h = posFdr(f.awayAtk, f.awayDef, true, "FWD", "ucl");
    const hd = posFdr(f.awayAtk, f.awayDef, true, "DEF", "ucl");
    ensure(f.homeId, f.homeName, f.homeCode ?? "").cells.push({
      matchday: f.matchday,
      opp: f.awayName,
      oppCode: f.awayCode ?? "",
      home: true,
      difficulty: rate(f.awayAtk, f.awayDef, true),
      attDifficulty: h.att,
      defDifficulty: hd.def,
      kickoff: f.kickoff,
    });
    const a = posFdr(f.homeAtk, f.homeDef, false, "FWD", "ucl");
    const ad = posFdr(f.homeAtk, f.homeDef, false, "DEF", "ucl");
    ensure(f.awayId, f.awayName, f.awayCode ?? "").cells.push({
      matchday: f.matchday,
      opp: f.homeName,
      oppCode: f.homeCode ?? "",
      home: false,
      difficulty: rate(f.homeAtk, f.homeDef, false),
      attDifficulty: a.att,
      defDifficulty: ad.def,
      kickoff: f.kickoff,
    });
  }

  const out = [...rows.values()];
  for (const r of out) {
    r.cells.sort((a, b) => a.matchday - b.matchday);
    r.avgDifficulty = r.cells.length
      ? r.cells.reduce((s, c) => s + c.difficulty, 0) / r.cells.length
      : 0;
  }
  return out.sort((a, b) => a.avgDifficulty - b.avgDifficulty || a.team.localeCompare(b.team));
}

export interface TeamDossier {
  teamId: number;
  team: string;
  code: string;
  attackRating: number;
  defenceRating: number;
  fixtures: TickerCell[];
  avgDifficulty: number;
  probableXI: PlayerRow[]; // a formation-legal XI: the likeliest starter at each slot
  bench: PlayerRow[]; // next likeliest to feature (subs / fringe)
  setPieces: { pk: PlayerRow[]; fk: PlayerRow[]; ck: PlayerRow[] };
  doubts: PlayerRow[]; // injury / rotation flags
  movedOn: PlayerRow[]; // our roster has them here but the form cross-check says otherwise
  topPicks: PlayerRow[]; // best xPts this matchday
}

/** Chance a player starts — prefer the composed projection value (blends
 * recent form + season minutes + price), fall back to the raw form value, then
 * to a prior from xPts. */
/** Official Sofascore lineup status baked into the projection, once confirmed
 * (~1h pre-KO): "start" | "bench" | null. Ground truth — beats every model
 * number. */
export function confirmedOf(p: { components?: unknown }): "start" | "bench" | null {
  const v = (p.components as Record<string, number> | undefined)?.confirmed;
  return v === 1 ? "start" : v === -1 ? "bench" : null;
}

function startScore(p: PlayerRow): number {
  const c = confirmedOf(p);
  if (c === "bench") return 0;
  if (c === "start") return Math.max(0.99, p.pStart ?? 0.99);
  const s = p.pStart ?? p.startProb;
  if (s != null && s > 0) return s;
  return Math.max(0.12, Math.min(0.7, (p.xpts ?? 0) / 6));
}

/**
 * Pick a plausible XI shaped to the team's actual formation: one keeper, then
 * the lines sized by how many clear starters play in each. See lib/xi.ts.
 */
function probableXIAndBench(list: PlayerRow[]): [PlayerRow[], PlayerRow[]] {
  const pool = list.filter((p) => p.teamOk !== false && p.statusCode < 2);
  const { xi, bench } = pickFormationXI(pool, {
    isGK: (p) => p.position === "GK",
    isDEF: (p) => p.position === "DEF",
    isMID: (p) => p.position === "MID",
    isFWD: (p) => p.position === "FWD",
    score: startScore,
  });
  return [xi, bench];
}

/** Per-club dossier: strength, fixture run, probable XI, set-piece duty, flags. */
export async function getTeamDossiers(matchday: number): Promise<TeamDossier[]> {
  const [teamRows, ticker, playerRows] = await Promise.all([
    db.select().from(teams).orderBy(teams.name),
    getFixtureTicker(matchday, 5),
    db
      .select(playerSelect)
      .from(players)
      .innerJoin(teams, eq(teams.uefaTeamId, players.teamId))
      .leftJoin(
        projections,
        and(eq(projections.playerId, players.uefaPlayerId), eq(projections.matchday, matchday)),
      )
      .leftJoin(playerForm, eq(playerForm.playerId, players.uefaPlayerId)) as Promise<PlayerRow[]>,
  ]);

  const tickerByTeam = new Map(ticker.map((r) => [r.teamId, r]));
  const byTeam = new Map<number, PlayerRow[]>();
  for (const p of playerRows) {
    const list = byTeam.get(p.teamId) ?? [];
    list.push(p);
    byTeam.set(p.teamId, list);
  }

  const spRank = (p: PlayerRow, tag: string) =>
    (p.setPiece ?? "").split(",").map((s) => s.trim()).includes(tag);

  return teamRows
    .map((t) => {
      const list = byTeam.get(t.uefaTeamId) ?? [];
      const tk = tickerByTeam.get(t.uefaTeamId);
      const [probableXI, bench] = probableXIAndBench(list);
      return {
        teamId: t.uefaTeamId,
        team: t.name,
        code: t.code ?? "",
        attackRating: t.attackRating,
        defenceRating: t.defenceRating,
        fixtures: tk?.cells ?? [],
        avgDifficulty: tk?.avgDifficulty ?? 0,
        probableXI,
        bench,
        setPieces: {
          pk: list.filter((p) => spRank(p, "PK")),
          fk: list.filter((p) => spRank(p, "FK")),
          ck: list.filter((p) => spRank(p, "CK")),
        },
        doubts: list
          .filter((p) => p.statusCode >= 1)
          .sort((a, b) => b.statusCode - a.statusCode || (b.xpts ?? 0) - (a.xpts ?? 0)),
        movedOn: list.filter((p) => p.teamOk === false),
        topPicks: [...list]
          .filter((p) => (p.xpts ?? 0) > 0)
          .sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0))
          .slice(0, 5),
      };
    })
    .sort((a, b) => a.avgDifficulty - b.avgDifficulty || a.team.localeCompare(b.team));
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

export interface RivalPlayer {
  playerId: number;
  name: string;
  position: string;
  team: string;
  xpts: number;
  mine: boolean;
}

export interface RivalRow {
  entryId: string;
  managerName: string;
  teamName: string;
  rank: number;
  totalPoints: number;
  projectedPoints: number;
  gapVsMe: number; // rival projected − my projected (positive → they out-project me)
  overlap: number; // shared players out of 15
  theirDifferentials: RivalPlayer[]; // they own, I don't
  myEdges: RivalPlayer[]; // I own, they don't
}

export interface RivalReport {
  ready: boolean;
  myProjectedPoints: number;
  myRank: number | null;
  rivals: RivalRow[];
  templateRisk: { playerId: number; name: string; xpts: number; ownedByRivals: number }[];
  commonThreats: { playerId: number; name: string; xpts: number; ownedByRivals: number }[];
  effectiveOwnership: {
    playerId: number;
    name: string;
    team: string;
    xpts: number;
    ownedPct: number; // % of the mini-league (incl. you) that owns them
    mine: boolean;
  }[];
  captainPicks: { playerId: number; name: string; count: number; mine: boolean }[];
  strategy: { mode: "protect" | "hold" | "chase" | "free"; text: string; mdsLeft: number } | null;
  rivalCount: number;
}

/** A rival's saved squad — new rows are [{id,c,s,b}], older ones a bare list. */
function normSquad(raw: unknown): {
  ids: number[];
  captainId: number | null;
  starterIds: Set<number>;
} {
  if (!Array.isArray(raw) || raw.length === 0)
    return { ids: [], captainId: null, starterIds: new Set() };
  if (typeof raw[0] === "number")
    return { ids: raw as number[], captainId: null, starterIds: new Set() };
  const arr = raw as { id: number; c?: boolean; s?: boolean }[];
  return {
    ids: arr.map((x) => x.id),
    captainId: arr.find((x) => x.c)?.id ?? null,
    starterIds: new Set(arr.filter((x) => x.s).map((x) => x.id)),
  };
}

/**
 * Project every mini-league rival's matchday score from their saved squad, show
 * the gap to mine, the players they have that I don't (and vice-versa), plus
 * template risk. Empty until squads have been ingested (post-MD1).
 */
export async function getRivals(matchday: number): Promise<RivalReport> {
  const s = await getSettings([KEYS.leagueId, KEYS.entryId]);
  const leagueId = s[KEYS.leagueId];
  const myEntryId = s[KEYS.entryId] ?? null;
  const empty: RivalReport = {
    ready: false,
    myProjectedPoints: 0,
    myRank: null,
    rivals: [],
    templateRisk: [],
    commonThreats: [],
    effectiveOwnership: [],
    captainPicks: [],
    strategy: null,
    rivalCount: 0,
  };
  if (!leagueId) return empty;

  const standings = await db
    .select()
    .from(leagueStandings)
    .where(and(eq(leagueStandings.leagueId, leagueId), eq(leagueStandings.matchday, matchday)))
    .orderBy(leagueStandings.rank);

  const parsed = new Map(standings.map((r) => [r.entryId, normSquad(r.squad)]));
  const withSquads = standings.filter((r) => (parsed.get(r.entryId)?.ids.length ?? 0) > 0);
  if (withSquads.length === 0) return empty;

  const mySquad = await getMySquad(matchday);
  const myIds = new Set<number>(mySquad.map((r) => r.playerId));
  const myStarterIds = new Set<number>(
    mySquad.filter((r) => r.isStarter).map((r) => r.playerId),
  );
  const myCaptainId = mySquad.find((r) => r.isCaptain)?.playerId ?? null;

  const allIds = new Set<number>(myIds);
  for (const r of withSquads) for (const id of parsed.get(r.entryId)!.ids) allIds.add(id);

  const meta = await db
    .select({
      playerId: players.uefaPlayerId,
      name: players.name,
      position: players.position,
      team: teams.name,
      xpts: projections.xpts,
    })
    .from(players)
    .innerJoin(teams, eq(teams.uefaTeamId, players.teamId))
    .leftJoin(
      projections,
      and(eq(projections.playerId, players.uefaPlayerId), eq(projections.matchday, matchday)),
    )
    .where(inArray(players.uefaPlayerId, [...allIds]));
  const m = new Map(meta.map((x) => [x.playerId, x]));

  const projectSquad = (
    ids: number[],
    captainId: number | null,
    starterIds: Set<number>,
  ): number => {
    const rows = ids.map((id) => m.get(id)).filter(Boolean) as typeof meta;
    // their actual XI if we have starter flags, else our best guess (top 11 by xPts)
    const xi =
      starterIds.size >= 11
        ? rows.filter((r) => starterIds.has(r.playerId))
        : [...rows].sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)).slice(0, 11);
    const total = xi.reduce((a, r) => a + (r.xpts ?? 0), 0);
    // captain doubles once more: their pick if known, else the top XI scorer
    const capX =
      (captainId != null ? m.get(captainId)?.xpts : undefined) ??
      Math.max(0, ...xi.map((r) => r.xpts ?? 0));
    return total + capX;
  };

  const myProjectedPoints = round(projectSquad([...myIds], myCaptainId, myStarterIds));
  const myRank = standings.find((r) => r.entryId === myEntryId)?.rank ?? null;

  const mkP = (id: number, mine: boolean): RivalPlayer | null => {
    const x = m.get(id);
    if (!x) return null;
    return {
      playerId: id,
      name: x.name,
      position: x.position,
      team: x.team,
      xpts: x.xpts ?? 0,
      mine,
    };
  };

  const rivalStandings = withSquads.filter((r) => r.entryId !== myEntryId);

  const rivals: RivalRow[] = rivalStandings
    .map((r) => {
      const { ids, captainId, starterIds } = parsed.get(r.entryId)!;
      const theirSet = new Set(ids);
      const theirDiff = (ids.filter((id) => !myIds.has(id)).map((id) => mkP(id, false)).filter(Boolean) as RivalPlayer[]).sort(
        (a, b) => b.xpts - a.xpts,
      );
      const myEdges = ([...myIds].filter((id) => !theirSet.has(id)).map((id) => mkP(id, true)).filter(Boolean) as RivalPlayer[]).sort(
        (a, b) => b.xpts - a.xpts,
      );
      const proj = round(projectSquad(ids, captainId, starterIds));
      return {
        entryId: r.entryId,
        managerName: r.managerName,
        teamName: r.teamName,
        rank: r.rank,
        totalPoints: r.totalPoints,
        projectedPoints: proj,
        gapVsMe: round(proj - myProjectedPoints),
        overlap: 15 - theirDiff.length,
        theirDifferentials: theirDiff.slice(0, 6),
        myEdges: myEdges.slice(0, 6),
      };
    })
    .sort((a, b) => a.rank - b.rank);

  const ownCount = new Map<number, number>();
  for (const r of rivalStandings)
    for (const id of parsed.get(r.entryId)!.ids) ownCount.set(id, (ownCount.get(id) ?? 0) + 1);

  const templateRisk = [...myIds]
    .map((id) => {
      const x = m.get(id);
      return {
        playerId: id,
        name: x?.name ?? String(id),
        xpts: x?.xpts ?? 0,
        ownedByRivals: ownCount.get(id) ?? 0,
      };
    })
    .filter((r) => r.ownedByRivals > 0)
    .sort((a, b) => b.ownedByRivals - a.ownedByRivals || b.xpts - a.xpts);

  const half = Math.ceil(rivalStandings.length / 2);
  const commonThreats = [...ownCount.entries()]
    .filter(([id, n]) => n >= half && !myIds.has(id))
    .map(([id, n]) => {
      const x = m.get(id);
      return { playerId: id, name: x?.name ?? String(id), xpts: x?.xpts ?? 0, ownedByRivals: n };
    })
    .sort((a, b) => b.ownedByRivals - a.ownedByRivals || b.xpts - a.xpts);

  // effective ownership across the mini-league (your rivals + you)
  const leagueSize = withSquads.length;
  const ownAll = new Map<number, number>();
  for (const r of withSquads)
    for (const id of parsed.get(r.entryId)!.ids) ownAll.set(id, (ownAll.get(id) ?? 0) + 1);
  const effectiveOwnership = [...allIds]
    .map((id) => {
      const x = m.get(id);
      return {
        playerId: id,
        name: x?.name ?? String(id),
        team: x?.team ?? "",
        xpts: x?.xpts ?? 0,
        ownedPct: Math.round((100 * (ownAll.get(id) ?? 0)) / leagueSize),
        mine: myIds.has(id),
      };
    })
    .filter((r) => r.xpts > 0)
    .sort((a, b) => b.xpts - a.xpts);

  // who the mini-league is captaining this matchday
  const capCount = new Map<number, number>();
  for (const r of withSquads) {
    const cid = parsed.get(r.entryId)?.captainId;
    if (cid) capCount.set(cid, (capCount.get(cid) ?? 0) + 1);
  }
  const captainPicks = [...capCount.entries()]
    .map(([id, count]) => ({
      playerId: id,
      name: m.get(id)?.name ?? String(id),
      count,
      mine: myCaptainId === id,
    }))
    .sort((a, b) => b.count - a.count);

  // chase / protect: what your table position says about how to play the armband
  // and differentials over the rest of the league phase
  const mdsLeft = Math.max(0, 8 - matchday + 1);
  const meStanding = standings.find((r) => r.entryId === myEntryId);
  const rank = meStanding?.rank ?? null;
  const room = mdsLeft * 14; // ~a plausible points swing between two managers per MD
  let strategy: RivalReport["strategy"] = null;
  if (rank != null && meStanding) {
    const behind = standings.find((r) => r.rank === rank + 1);
    const ahead = standings.find((r) => r.rank === rank - 1);
    const gapAhead = ahead ? ahead.totalPoints - meStanding.totalPoints : null;
    const leadOverBehind = behind ? meStanding.totalPoints - behind.totalPoints : null;
    if (rank === 1) {
      strategy =
        (leadOverBehind ?? 999) > room
          ? {
              mode: "protect",
              mdsLeft,
              text: `You lead by ${leadOverBehind ?? "—"} with ${mdsLeft} MD left — protect it. Own what your rivals own (template), take the safe captain, and don't chase differentials that only help if they blow up.`,
            }
          : {
              mode: "hold",
              mdsLeft,
              text: `Lead is only ${leadOverBehind ?? "—"} with ${mdsLeft} MD left — match your nearest rival's captain and their big differentials so a single haul can't flip the table.`,
            };
    } else if (gapAhead != null && gapAhead <= room) {
      strategy = {
        mode: "chase",
        mdsLeft,
        text: `${gapAhead} pts behind ${ahead?.managerName ?? "the spot ahead"} with ${mdsLeft} MD left — you need variance. Fade template, take the aggressive (differential) captain, and prioritise low-owned high-xPts players from the list below.`,
      };
    } else {
      strategy = {
        mode: "free",
        mdsLeft,
        text: `Out of realistic range of a prize place — just play the highest expected points every matchday, no need to hedge or gamble.`,
      };
    }
  }

  return {
    ready: true,
    myProjectedPoints,
    myRank,
    rivals,
    templateRisk,
    commonThreats,
    effectiveOwnership,
    captainPicks,
    strategy,
    rivalCount: rivalStandings.length,
  };
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
    .leftJoin(playerForm, eq(playerForm.playerId, players.uefaPlayerId))
    .where(inArray(players.uefaPlayerId, ids));
  return rows as PlayerRow[];
}
