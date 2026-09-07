import type { DraftConfig } from "@/lib/draft/queries";

export interface BoardPlayer {
  extId: string;
  name: string;
  team: string;
  positions: string;
  primaryPos: string;
  projPoints: number;
  adp: number;
  providerRank: number | null;
  ecrRank: number | null;
  ecrTier: number | null;
  ecrPosRank: string;
  ecrStd: number;
  vbd: number;
  byeWeek: number | null;
  injuryStatus: string;
  outlook: string;
}

export interface BoardPick {
  overall: number;
  teamId: number;
  teamName: string;
  playerExtId: string;
  isMine: boolean;
  source: string;
}

export type SortKey = "vbd" | "projPoints" | "adp" | "ecrRank";

export const POS_FILTERS = ["ALL", "QB", "RB", "WR", "TE", "FLEX", "K", "DST"] as const;
export type PosFilter = (typeof POS_FILTERS)[number];

const FLEX = new Set(["RB", "WR", "TE"]);

export function matchesPos(p: BoardPlayer, f: PosFilter): boolean {
  if (f === "ALL") return true;
  if (f === "FLEX") return FLEX.has(p.primaryPos);
  return p.primaryPos === f || p.positions.split(",").includes(f);
}

export function sortPlayers(list: BoardPlayer[], key: SortKey): BoardPlayer[] {
  const dir = key === "adp" || key === "ecrRank" ? 1 : -1;
  return [...list].sort((a, b) => {
    const av = a[key] ?? (dir === 1 ? 9999 : -9999);
    const bv = b[key] ?? (dir === 1 ? 9999 : -9999);
    if (av === bv) return (a.ecrRank ?? 9999) - (b.ecrRank ?? 9999);
    return (Number(av) - Number(bv)) * dir;
  });
}

/** Snake draft: overall pick numbers that belong to `slot` (1-based) in an
 * `teams`-team league, up to `rounds`. */
export function myPickNumbers(slot: number, teams: number, rounds = 18): number[] {
  const out: number[] = [];
  for (let r = 1; r <= rounds; r++) {
    const pickInRound = r % 2 === 1 ? slot : teams - slot + 1;
    out.push((r - 1) * teams + pickInRound);
  }
  return out;
}

/** Fill my roster into slots given the configured counts. */
export function fillRoster(
  mine: BoardPlayer[],
  roster: Record<string, number>,
): { slot: string; players: BoardPlayer[]; need: number }[] {
  const order = ["QB", "RB", "WR", "TE", "FLEX", "K", "DST", "BE"];
  const slots = order.filter((s) => roster[s]);
  const used = new Set<string>();
  const result = slots.map((slot) => ({ slot, players: [] as BoardPlayer[], need: roster[slot] }));

  const bySlot = (slot: string, p: BoardPlayer) =>
    slot === "BE" ? true : slot === "FLEX" ? FLEX.has(p.primaryPos) : p.primaryPos === slot;

  for (const row of result) {
    for (const p of mine) {
      if (used.has(p.extId) || row.players.length >= row.need) continue;
      if (bySlot(row.slot, p)) {
        row.players.push(p);
        used.add(p.extId);
      }
    }
  }
  return result;
}

export function rosterNeeds(
  filled: ReturnType<typeof fillRoster>,
): Record<string, number> {
  const needs: Record<string, number> = {};
  for (const r of filled) {
    const open = r.need - r.players.length;
    if (open > 0 && r.slot !== "BE") needs[r.slot] = open;
  }
  return needs;
}

export type { DraftConfig };
