import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { draftPlayers } from "@/lib/db/schema";
import { getSettings } from "@/lib/settings";
import { getDashboardSummary } from "@/lib/ucl/queries";
import { toPlayer as toFpl, bestXI as fplBestXI, type FplPlayer } from "@/app/fpl/lib";
import {
  toPlayer as toNfl,
  optimalLineup,
  weekPoints,
  OUT_STATUS,
  type NflPlayer,
} from "@/app/nfl/lib";

export interface Alert {
  league: "UCL" | "FPL" | "NFL";
  tone: "bad" | "warn" | "accent";
  text: string;
  href: string;
}

export interface HomeSummary {
  ucl: {
    active: boolean;
    matchday: number;
    deadlineIso: string | null;
    projected: number;
    captain: string | null;
    rank: number | null;
    leagueSize: number;
    xiFlags: number;
    ingestOk: boolean | null;
    ingestAt: string | null;
  };
  fpl: {
    active: boolean;
    gw: number | null;
    xiProj: number;
    rank: number | null;
    gapToNext: number | null;
    topClaim: { name: string; gain: number } | null;
    injured: number;
  };
  nfl: {
    active: boolean;
    week: number | null;
    myProj: number;
    oppName: string | null;
    oppProj: number | null;
    winPct: number | null;
    lineupIssues: number;
    topClaim: { name: string; gain: number } | null;
  };
  alerts: Alert[];
}

function hoursUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return (new Date(iso).getTime() - Date.now()) / 3.6e6;
}

export async function getHomeSummary(): Promise<HomeSummary> {
  const [uclRaw, fplRows, nflRows, s] = await Promise.all([
    getDashboardSummary().catch(() => null),
    db.select().from(draftPlayers).where(eq(draftPlayers.sport, "fpl")).catch(() => []),
    db.select().from(draftPlayers).where(eq(draftPlayers.sport, "nfl")).catch(() => []),
    getSettings([
      "model.optimizer_output",
      "draft.fpl.my_squad", "draft.fpl.standings",
      "draft.nfl.my_roster", "draft.nfl.week", "draft.nfl.schedule",
      "draft.nfl.slots", "draft.nfl.standings",
    ]),
  ]);
  const alerts: Alert[] = [];

  // ---------- UCL ----------
  let opt: Record<string, unknown> = {};
  try {
    opt = s["model.optimizer_output"] ? JSON.parse(s["model.optimizer_output"]) : {};
  } catch {
    /* ignore */
  }
  const captains = opt.captains as { safePick?: { name?: string } } | undefined;
  const timing = opt.matchdayTiming as { liveOptions?: string[] } | undefined;
  const ucl = {
    active: !!uclRaw && (uclRaw.squadSize ?? 0) > 0,
    matchday: uclRaw?.matchday ?? 0,
    deadlineIso: uclRaw?.deadlineIso ?? null,
    projected: Math.round(uclRaw?.projectedPoints ?? 0),
    captain: captains?.safePick?.name ?? null,
    rank: uclRaw?.myRank ?? null,
    leagueSize: uclRaw?.leagueSize ?? 0,
    xiFlags: 0,
    ingestOk: uclRaw?.ingest?.ok ?? null,
    ingestAt: (uclRaw?.ingest?.at ?? null) as string | null,
  };
  const uh = hoursUntil(ucl.deadlineIso);
  if (ucl.active && uh != null && uh > 0 && uh < 48) {
    alerts.push({
      league: "UCL",
      tone: uh < 12 ? "bad" : "warn",
      text: `Champions League deadline in ${uh < 1 ? "<1h" : `${Math.round(uh)}h`} — set your XI & captain${ucl.captain ? ` (${ucl.captain})` : ""}.`,
      href: "/ucl/optimizer",
    });
  }
  if (timing?.liveOptions?.length) {
    alerts.push({
      league: "UCL",
      tone: "accent",
      text: `Bench your late-day options (${timing.liveOptions.slice(0, 3).join(", ")}) — you can sub them in after the early games.`,
      href: "/ucl/optimizer",
    });
  }

  // ---------- FPL ----------
  const fplPlayers: FplPlayer[] = (fplRows as Record<string, unknown>[]).map(toFpl);
  let mySquadIds: string[] = [];
  try {
    mySquadIds = s["draft.fpl.my_squad"] ? JSON.parse(s["draft.fpl.my_squad"]) : [];
  } catch {
    /* ignore */
  }
  const fplById = new Map(fplPlayers.map((p) => [p.extId, p]));
  const fplSquad = mySquadIds.map((id) => fplById.get(id)).filter(Boolean) as FplPlayer[];
  const fplXi = fplSquad.length >= 11 ? fplBestXI(fplSquad) : null;
  const fplInjured = fplSquad.filter((p) => p.unavailable).length;
  const fplFreeTop = fplPlayers
    .filter((p) => p.available && !mySquadIds.includes(p.extId) && !p.unavailable)
    .sort((a, b) => b.horizon - a.horizon)[0];
  const fplWorstStarter = fplXi ? Math.min(...fplXi.xi.map((p) => p.horizon)) : 0;
  const fpl = {
    active: fplSquad.length > 0,
    gw: fplPlayers[0]?.gws?.[0]?.gw ?? null,
    xiProj: fplXi ? Math.round(fplXi.xi.reduce((a, p) => a + p.proj, 0)) : 0,
    rank: null as number | null,
    gapToNext: null as number | null,
    topClaim:
      fplFreeTop && fplFreeTop.horizon - fplWorstStarter > 4
        ? { name: fplFreeTop.name, gain: Math.round(fplFreeTop.horizon - fplWorstStarter) }
        : null,
    injured: fplInjured,
  };
  if (fpl.active && fplInjured > 0) {
    alerts.push({
      league: "FPL",
      tone: "warn",
      text: `${fplInjured} player${fplInjured > 1 ? "s" : ""} in your FPL squad flagged injured/doubtful — check your lineup.`,
      href: "/fpl",
    });
  }
  if (fpl.topClaim) {
    alerts.push({
      league: "FPL",
      tone: "accent",
      text: `Waiver upgrade available: ${fpl.topClaim.name} projects +${fpl.topClaim.gain} over your weakest starter.`,
      href: "/fpl",
    });
  }

  // ---------- NFL ----------
  const nflPlayers: NflPlayer[] = (nflRows as Record<string, unknown>[]).map(toNfl);
  let nflRosterIds: string[] = [];
  try {
    nflRosterIds = s["draft.nfl.my_roster"] ? JSON.parse(s["draft.nfl.my_roster"]) : [];
  } catch {
    /* ignore */
  }
  let nflSlots: Record<string, number> = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 };
  try {
    if (s["draft.nfl.slots"]) nflSlots = JSON.parse(s["draft.nfl.slots"]);
  } catch {
    /* ignore */
  }
  const nflWeek = Number(s["draft.nfl.week"]) || null;
  const nflById = new Map(nflPlayers.map((p) => [p.extId, p]));
  const nflRoster = nflRosterIds.map((id) => nflById.get(id)).filter(Boolean) as NflPlayer[];
  const nflLineup = nflRoster.length ? optimalLineup(nflRoster, nflSlots, 0) : null;
  const startIds = new Set(nflLineup?.starters.map((x) => x.p?.extId).filter(Boolean) as string[]);
  // lineup issues: a benched player projecting above a starter, or a starter OUT / on bye
  let nflIssues = 0;
  if (nflLineup) {
    for (const st of nflLineup.starters) {
      if (st.p && (OUT_STATUS.has(st.p.injury) || st.p.onBye)) nflIssues++;
    }
    const benchBest = Math.max(
      0,
      ...nflRoster.filter((p) => !startIds.has(p.extId)).map((p) => weekPoints(p, 0)),
    );
    const startWorst = Math.min(
      ...nflLineup.starters.filter((x) => x.p && x.slot !== "K" && x.slot !== "DST").map((x) => weekPoints(x.p!, 0)),
    );
    if (benchBest > startWorst + 2) nflIssues++;
  }
  let nflSchedule: { week: number; home: number; away: number; home_name: string; away_name: string }[] = [];
  try {
    nflSchedule = s["draft.nfl.schedule"] ? JSON.parse(s["draft.nfl.schedule"]) : [];
  } catch {
    /* ignore */
  }
  const myTeamId =
    Number((await getSettings(["draft.nfl.my_team_id"]))["draft.nfl.my_team_id"]) || null;
  const match = nflSchedule.find(
    (m) => m.week === nflWeek && (m.home === myTeamId || m.away === myTeamId),
  );
  const oppId = match ? (match.home === myTeamId ? match.away : match.home) : null;
  const oppRoster = nflPlayers.filter((p) => p.ownerTeamId === oppId);
  const oppLineup = oppRoster.length ? optimalLineup(oppRoster, nflSlots, 0) : null;
  const myProj = nflLineup ? Math.round(nflLineup.total) : 0;
  const oppProj = oppLineup ? Math.round(oppLineup.total) : null;
  const winPct =
    oppProj != null ? Math.round(100 / (1 + Math.exp(-(myProj - oppProj) / 16))) : null;
  const nflFreeTop = nflPlayers
    .filter((p) => p.available && !nflRosterIds.includes(p.extId) && !OUT_STATUS.has(p.injury))
    .sort((a, b) => b.vor - a.vor)[0];
  const nflWorstStarter = nflLineup
    ? Math.min(...nflLineup.starters.filter((x) => x.p).map((x) => x.p!.rosProj))
    : 0;
  const nfl = {
    active: nflRoster.length > 0,
    week: nflWeek,
    myProj,
    oppName: oppId ? (match!.home === myTeamId ? match!.away_name : match!.home_name) : null,
    oppProj,
    winPct,
    lineupIssues: nflIssues,
    topClaim:
      nflFreeTop && nflFreeTop.rosProj - nflWorstStarter > 12
        ? { name: nflFreeTop.name, gain: Math.round(nflFreeTop.rosProj - nflWorstStarter) }
        : null,
  };
  if (nfl.active && nflIssues > 0) {
    alerts.push({
      league: "NFL",
      tone: "bad",
      text: `Your NFL lineup has ${nflIssues} issue${nflIssues > 1 ? "s" : ""} (a starter is OUT/on bye, or a bench player out-projects a starter).`,
      href: "/nfl",
    });
  }
  if (nfl.active && winPct != null && winPct < 45) {
    alerts.push({
      league: "NFL",
      tone: "warn",
      text: `You're the underdog vs ${nfl.oppName} this week (${winPct}% win) — consider a ceiling play or a waiver move.`,
      href: "/nfl",
    });
  }

  return { ucl, fpl, nfl, alerts };
}
