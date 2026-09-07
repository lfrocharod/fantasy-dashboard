import type { DraftConfig } from "@/lib/draft/queries";

export interface WeekOpp {
  week: number;
  opp: string;
  home: boolean | null;
  fdr: number; // 1 easy … 5 hard, 0 = bye/unknown
}

export interface NflPlayer {
  extId: string;
  name: string;
  pos: string; // QB RB WR TE K DST
  team: string; // pro team abbr
  weekProj: number;
  rosProj: number;
  vor: number;
  ecrRank: number | null;
  ecrTier: number | null;
  bye: number;
  onBye: boolean;
  injury: string; // ACTIVE / QUESTIONABLE / DOUBTFUL / OUT / IR / SUSPENSION
  pctOwned: number;
  pctStarted: number;
  slot: string; // current lineup slot (QB/RB/WR/TE/FLEX/DST/K/BE/IR)
  ownerTeamId: number | null;
  ownerName: string;
  available: boolean;
  nextOpp: string;
  nextFdr: number;
  matchups: WeekOpp[];
}

export const FLEX_POS = new Set(["RB", "WR", "TE"]);
export const START_POS = ["QB", "RB", "WR", "TE", "FLEX", "DST", "K"] as const;
export const POS_COLOR: Record<string, string> = {
  QB: "#8957e5", RB: "#1a7f37", WR: "#1f6feb", TE: "#b7791f", K: "#6b7280", DST: "#cf222e",
};
export const FDR_BG: Record<number, string> = {
  1: "rgba(34,197,94,0.32)",
  2: "rgba(132,204,22,0.24)",
  3: "rgba(148,163,184,0.14)",
  4: "rgba(249,115,22,0.24)",
  5: "rgba(239,68,68,0.30)",
};
export const OUT_STATUS = new Set(["OUT", "IR", "SUSPENSION", "DOUBTFUL"]);

export function toPlayer(p: Record<string, unknown>): NflPlayer {
  const raw = (p.raw ?? {}) as Record<string, unknown>;
  return {
    extId: String(p.extId),
    name: String(p.name),
    pos: String(p.primaryPos ?? ""),
    team: String(p.team ?? ""),
    weekProj: Number(raw.weekProj ?? p.projPoints ?? 0),
    rosProj: Number(raw.rosProj ?? 0),
    vor: Number(p.vbd ?? 0),
    ecrRank: (p.ecrRank as number) ?? null,
    ecrTier: (p.ecrTier as number) ?? null,
    bye: Number(raw.bye ?? 0),
    onBye: raw.onBye === true,
    injury: String(raw.injury ?? "ACTIVE"),
    pctOwned: Number(raw.pctOwned ?? 0),
    pctStarted: Number(raw.pctStarted ?? 0),
    slot: String(raw.slot ?? ""),
    ownerTeamId: (raw.ownerTeamId as number) ?? null,
    ownerName: String(raw.ownerName ?? ""),
    available: raw.available !== false && !raw.ownerName,
    nextOpp: String(raw.next_opp ?? ""),
    nextFdr: Number(raw.next_fdr ?? 0),
    matchups: (raw.matchups as WeekOpp[]) ?? [],
  };
}

/** Points a player is expected to score in a given week (0 on bye / out). */
export function weekPoints(p: NflPlayer, weekIdx: number): number {
  const m = p.matchups[weekIdx];
  if (!m || m.opp === "BYE" || m.opp === "") return 0;
  if (weekIdx === 0 && OUT_STATUS.has(p.injury)) return 0;
  // taper future weeks toward the ROS average as fixture certainty drops
  const perWeek = p.rosProj > 0 ? p.rosProj / Math.max(1, p.matchups.filter((x) => x.opp && x.opp !== "BYE").length) : 0;
  const base = weekIdx === 0 ? p.weekProj : 0.55 * p.weekProj + 0.45 * perWeek;
  const fdrAdj = m.fdr ? 1 + (3 - m.fdr) * 0.05 : 1;
  return Math.max(0, base * fdrAdj);
}

/** Fill the optimal starting lineup for `weekIdx` from a roster. */
export function optimalLineup(
  roster: NflPlayer[],
  slots: Record<string, number>,
  weekIdx = 0,
): { starters: { slot: string; p: NflPlayer | null }[]; bench: NflPlayer[]; total: number } {
  const score = (p: NflPlayer) => weekPoints(p, weekIdx);
  const avail = roster.filter((p) => score(p) > 0).sort((a, b) => score(b) - score(a));
  const used = new Set<string>();
  const starters: { slot: string; p: NflPlayer | null }[] = [];
  const order = ["QB", "RB", "WR", "TE", "FLEX", "DST", "K"];
  for (const slot of order) {
    for (let i = 0; i < (slots[slot] ?? 0); i++) {
      const pick = avail.find(
        (p) =>
          !used.has(p.extId) &&
          (slot === "FLEX" ? FLEX_POS.has(p.pos) : p.pos === slot),
      );
      if (pick) used.add(pick.extId);
      starters.push({ slot, p: pick ?? null });
    }
  }
  const bench = roster.filter((p) => !used.has(p.extId)).sort((a, b) => score(b) - score(a));
  const total = starters.reduce((a, s) => a + (s.p ? score(s.p) : 0), 0);
  return { starters, bench, total };
}

export function startSitCall(p: NflPlayer, myStarters: Set<string>): "START" | "SIT" | "FLEX?" {
  if (OUT_STATUS.has(p.injury) || p.onBye) return "SIT";
  if (myStarters.has(p.extId)) return "START";
  return p.pos === "TE" || FLEX_POS.has(p.pos) ? "FLEX?" : "SIT";
}

// --- manager rosters (current) from ownership -------------------------------
export interface NflManager {
  teamId: number;
  name: string;
  isMine: boolean;
  players: NflPlayer[];
  byPos: Record<string, NflPlayer[]>;
  rosTotal: number;
}

export function groupTeams(players: NflPlayer[], myTeamId: number | null): NflManager[] {
  const m = new Map<number, NflManager>();
  for (const p of players) {
    if (p.ownerTeamId == null) continue;
    let mg = m.get(p.ownerTeamId);
    if (!mg) {
      mg = {
        teamId: p.ownerTeamId,
        name: p.ownerName || `Team ${p.ownerTeamId}`,
        isMine: p.ownerTeamId === myTeamId,
        players: [],
        byPos: { QB: [], RB: [], WR: [], TE: [], K: [], DST: [] },
        rosTotal: 0,
      };
      m.set(p.ownerTeamId, mg);
    }
    mg.players.push(p);
    (mg.byPos[p.pos] ?? (mg.byPos[p.pos] = [])).push(p);
  }
  for (const mg of m.values()) {
    for (const k of Object.keys(mg.byPos)) mg.byPos[k].sort((a, b) => b.rosProj - a.rosProj);
    mg.rosTotal = Math.round(mg.players.reduce((a, p) => a + p.rosProj, 0));
  }
  return [...m.values()].sort(
    (a, b) => (b.isMine ? 1 : 0) - (a.isMine ? 1 : 0) || b.rosTotal - a.rosTotal,
  );
}

export async function loadNfl(): Promise<{ players: NflPlayer[]; config: DraftConfig | null }> {
  const r = await fetch("/api/draft/board?sport=nfl", { cache: "no-store" });
  const d = await r.json();
  return { players: (d.players ?? []).map(toPlayer), config: d.config ?? null };
}
