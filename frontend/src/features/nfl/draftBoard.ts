/** Draft-night board helpers: filtering, sorting, snake-draft pick math and
 * roster fill. Pure functions over the board the API returns. */
import type { Api } from "@/api/client";

export type BoardPlayer = Api["BoardPlayer"];
export type SortKey = "vbd" | "projPoints" | "adp" | "ecrRank";

export const POS_FILTERS = ["ALL", "QB", "RB", "WR", "TE", "FLEX", "K", "DST"] as const;
export type PosFilter = (typeof POS_FILTERS)[number];

const FLEX = new Set(["RB", "WR", "TE"]);

export function matchesPos(p: BoardPlayer, f: PosFilter): boolean {
  if (f === "ALL") return true;
  if (f === "FLEX") return FLEX.has(p.primaryPos);
  return p.primaryPos === f || p.positions.split(",").includes(f);
}

/** Best first: high VBD / projection, low ADP / expert rank; ties by expert rank. */
export function sortBoard(list: readonly BoardPlayer[], key: SortKey): BoardPlayer[] {
  const asc = key === "adp" || key === "ecrRank";
  const missing = asc ? 9999 : -9999;
  return [...list].sort((a, b) => {
    const av = a[key] ?? missing;
    const bv = b[key] ?? missing;
    if (av === bv) return (a.ecrRank ?? 9999) - (b.ecrRank ?? 9999);
    return asc ? av - bv : bv - av;
  });
}

/** Snake draft: the overall pick numbers that belong to `slot` (1-based). */
export function myPickNumbers(slot: number, teams: number, rounds = 18): number[] {
  const out: number[] = [];
  for (let r = 1; r <= rounds; r++) {
    const inRound = r % 2 === 1 ? slot : teams - slot + 1;
    out.push((r - 1) * teams + inRound);
  }
  return out;
}

export interface SlotFill {
  slot: string;
  players: BoardPlayer[];
  need: number;
}

const SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "K", "DST", "BE"];

/** Place my picks into the league's roster slots, in pick order. */
export function fillRoster(mine: readonly BoardPlayer[], roster: Record<string, number>): SlotFill[] {
  const used = new Set<string>();
  const fits = (slot: string, p: BoardPlayer) =>
    slot === "BE" ? true : slot === "FLEX" ? FLEX.has(p.primaryPos) : p.primaryPos === slot;
  return SLOT_ORDER.filter((s) => roster[s]).map((slot) => {
    const row: SlotFill = { slot, players: [], need: roster[slot] ?? 0 };
    for (const p of mine) {
      if (row.players.length >= row.need) break;
      if (!used.has(p.extId) && fits(slot, p)) {
        row.players.push(p);
        used.add(p.extId);
      }
    }
    return row;
  });
}

/** Starting slots still open (the bench doesn't count as a need). */
export function rosterNeeds(filled: readonly SlotFill[]): Record<string, number> {
  const needs: Record<string, number> = {};
  for (const r of filled) {
    const open = r.need - r.players.length;
    if (open > 0 && r.slot !== "BE") needs[r.slot] = open;
  }
  return needs;
}

/** Mark the rows where the expert tier steps down, for tier headers. */
export function withTierBreaks(list: readonly BoardPlayer[]): { p: BoardPlayer; tierBreak: boolean }[] {
  let last: number | null = null;
  return list.map((p) => {
    const tierBreak = p.ecrTier != null && p.ecrTier !== last;
    if (p.ecrTier != null) last = p.ecrTier;
    return { p, tierBreak };
  });
}
