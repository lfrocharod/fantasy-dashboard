/**
 * Records what the ORIGINAL TypeScript logic (the old web app's
 * app/fpl/lib.ts and app/nfl/lib.ts) returns for tests/parity/inputs.json.
 * The Python ports must reproduce these outputs (tests/test_parity_*.py).
 *
 * One-off migration tool — run while web/ still exists:
 *   cd web && npx tsx --tsconfig tsconfig.json ../backend/tests/parity/record_goldens.ts
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as F from "../../../web/app/fpl/lib";
import * as N from "../../../web/app/nfl/lib";

const here = dirname(fileURLToPath(import.meta.url));
const input = JSON.parse(readFileSync(join(here, "inputs.json"), "utf8"));
const ids = (ps: { extId: string }[]) => ps.map((p) => p.extId);

// ---------------- FPL ----------------
const fplIn = input.fpl;
const fp: F.FplPlayer[] = fplIn.players.map(F.toPlayer);
const byId = new Map(fp.map((p) => [p.extId, p]));
const myEntry: string = fplIn.myEntryId;
const managers = F.groupByManager(fp, [], myEntry, fplIn.fallbackNames);
const me = managers.find((m) => m.isMine)!;
const rivals = managers.filter((m) => !m.isMine);
const owners = new Map<string, { name: string; ids: Set<string> }>();
for (const mg of rivals) owners.set(mg.entryId, { name: mg.name, ids: new Set(ids(mg.players)) });
const free = fp.filter((p) => p.available && !me.players.some((x) => x.extId === p.extId));
const H: F.Horizon[] = ["short", "medium", "season"];

const fpl = {
  players: fp.map((p) => ({
    extId: p.extId,
    status: p.status,
    available: p.available,
    oppFactor: F.oppFactor(p),
    oppTag: F.oppTag(p),
    value: H.map((h) => F.valueFor(p, h)),
    neutral: H.map((h) => F.neutralValue(p, h)),
    claimable: H.map((h) => F.claimable(p, h)),
    rosterable: F.rosterable(p),
  })),
  bestXI: (() => {
    const xi = F.bestXI(me.players);
    const xiRos = F.bestXI(me.players, (p) => p.ros);
    return {
      xi: ids(xi.xi), bench: ids(xi.bench), formation: xi.formation,
      rosXi: ids(xiRos.xi), rosBench: ids(xiRos.bench), rosFormation: xiRos.formation,
    };
  })(),
  squadHorizon: F.squadHorizon(me.players, [0, 1, 2, 3, 4, 5]),
  xiValue: H.map((h) => F.xiValue(me.players, h)),
  managers: managers.map((m) => ({
    entryId: m.entryId, name: m.name, isMine: m.isMine, players: ids(m.players),
    byPos: Object.fromEntries(Object.entries(m.byPos).map(([k, v]) => [k, ids(v)])),
    totalMedium: m.total.medium, totalSeason: m.total.season,
  })),
  // every manager takes a turn as "me", for coverage
  perManager: managers.map((m) => {
    const others = managers.filter((x) => x.entryId !== m.entryId);
    const own = new Map<string, { name: string; ids: Set<string> }>();
    for (const o of others) own.set(o.entryId, { name: o.name, ids: new Set(ids(o.players)) });
    const mineIds = new Set(ids(m.players));
    const fa = fp.filter((p) => p.available && !mineIds.has(p.extId));
    const xi = F.bestXI(m.players);
    return {
      entryId: m.entryId,
      xi: ids(xi.xi), bench: ids(xi.bench), formation: xi.formation,
      xiValue: H.map((h) => F.xiValue(m.players, h)),
      weakSpots: H.map((h) =>
        F.weakSpots(xi.xi, fa, h).map((u) => ({ out: u.out.extId, in: u.in.extId, gain: u.gain })),
      ),
      tradeIdeas: H.map((h) =>
        F.tradeIdeas(m.players, fp, own, 4, h).map((t) => ({
          rival: t.rivalName, give: ids(t.give), get: ids(t.get), myGain: t.myGain, theirGain: t.theirGain,
        })),
      ),
    };
  }),
  evaluateTrade: fplIn.trades.map((t: { owner?: string; give: string[]; get: string[] }) =>
    F.evaluateTrade(
      t.give.map((x) => byId.get(x)!), t.get.map((x) => byId.get(x)!),
      (managers.find((m) => m.entryId === (t.owner ?? myEntry)) ?? me).players,
    ),
  ),
  stash: ids(F.stashCandidates(fp, new Set(ids(me.players)))),
  clubFixtures: F.clubFixtures(fp).map((c) => ({ team: c.team, avgFdr: c.avgFdr, cells: c.cells })),
  clubDossiers: F.clubDossiers(fp).map((d) => ({
    team: d.team, avgFdr: d.avgFdr, probableXI: ids(d.probableXI), bench: ids(d.bench),
    pk: ids(d.setPieces.pk), fk: ids(d.setPieces.fk), ck: ids(d.setPieces.ck),
    doubts: ids(d.doubts), keyPlayers: ids(d.keyPlayers),
  })),
  predictClaims: F.predictClaims(managers, fp, myEntry).map((c) => ({
    rival: c.rivalName, weakPos: c.weakPos, weakStarter: c.weakStarter, target: c.target.extId, gain: c.gain,
  })),
  sortHorizon: ids(F.sortPlayers(fp, "horizon")),
};

// ---------------- NFL ----------------
const nflIn = input.nfl;
const np: N.NflPlayer[] = nflIn.players.map(N.toPlayer);
const nById = new Map(np.map((p) => [p.extId, p]));
const teams = N.groupTeams(np, nflIn.myTeamId);
const nMe = teams.find((t) => t.isMine)!;
const nRivals = teams.filter((t) => !t.isMine);
const slots = nflIn.slots;
const lineupOut = (l: ReturnType<typeof N.optimalLineup>) => ({
  starters: l.starters.map((s) => [s.slot, s.p?.extId ?? null]),
  bench: ids(l.bench),
  total: l.total,
});

const nfl = {
  players: np.map((p) => ({
    extId: p.extId,
    available: p.available,
    usageTag: N.usageTag(p),
    oppFactor: N.oppFactor(p),
    adjRos: N.adjRos(p),
    oppTag: N.oppTag(p),
    weekPoints: [0, 1, 2, 3].map((w) => N.weekPoints(p, w)),
    weekPointsWl: [1, 2, 5].map((w) => N.weekPoints(p, w, 7)),
    weekRange: [0, 1].map((w) => N.weekRange(p, w)),
    modeScores: (["floor", "mean", "ceiling"] as const).map((m) => N.modeScore(m)(p)),
  })),
  lineupModes: [10, 40, 41, 61.9, 62, 90].flatMap((w) => [N.lineupMode(w, false), N.lineupMode(w, true)]),
  winProb: [-60, -19, -0.5, 0, 0.5, 7, 19, 60].map((m) => N.winProbFromMargin(m)),
  teams: teams.map((t) => ({
    teamId: t.teamId, name: t.name, isMine: t.isMine, players: ids(t.players), rosTotal: t.rosTotal,
    byPos: Object.fromEntries(Object.entries(t.byPos).map(([k, v]) => [k, ids(v)])),
  })),
  lineups: [
    lineupOut(N.optimalLineup(nMe.players, slots, 0)),
    lineupOut(N.optimalLineup(nMe.players, slots, 2)),
    lineupOut(N.optimalLineup(nMe.players, slots, 0, N.modeScore("ceiling"))),
    lineupOut(N.optimalLineup(nMe.players, slots, 0, N.modeScore("floor"))),
    lineupOut(N.optimalLineup(nRivals[0].players, slots, 0)),
  ],
  startSit: (() => {
    const st = new Set(N.optimalLineup(nMe.players, slots, 0).starters.map((s) => s.p?.extId).filter(Boolean) as string[]);
    return nMe.players.map((p) => [p.extId, N.startSitCall(p, st)]);
  })(),
  tradeIdeas: N.nflTradeIdeas(nMe, nRivals, slots).map((t) => ({
    rival: t.rivalName, rivalTeamId: t.rivalTeamId, give: t.give.extId, get: t.get.extId,
    myGain: t.myGain, theirGain: t.theirGain,
  })),
  clubFixtures: N.nflClubFixtures(np).map((c) => ({ team: c.team, avgFdr: c.avgFdr })),
  clubDossiers: N.nflClubDossiers(np).map((d) => ({
    team: d.team, avgFdr: d.avgFdr, starters: ids(d.starters), bench: ids(d.bench), doubts: ids(d.doubts), bye: d.bye,
  })),
  playoffs: N.simPlayoffs(
    teams, nflIn.standings, nflIn.schedule, slots, nflIn.week, nflIn.regWeeks, nflIn.playoffTeams,
    nflIn.myTeamId, "H2H_RECORD", 20000,
  ).map((o) => ({ teamId: o.teamId, projWins: o.projWins, projPf: o.projPf, playoffPct: o.playoffPct, byePct: o.byePct })),
  playoffsByPoints: N.simPlayoffs(
    teams, nflIn.standings, nflIn.schedule, slots, nflIn.week, nflIn.regWeeks, nflIn.playoffTeams,
    nflIn.myTeamId, "TOTAL_POINTS_SCORED", 20000,
  ).map((o) => ({ teamId: o.teamId, projWins: o.projWins, projPf: o.projPf, playoffPct: o.playoffPct, byePct: o.byePct })),
};
void nById;

writeFileSync(join(here, "goldens.json"), JSON.stringify({ fpl, nfl }));
console.log("wrote goldens.json");
