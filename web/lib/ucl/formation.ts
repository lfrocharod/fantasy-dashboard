/**
 * UEFA Champions League Fantasy squad / formation rules, shared by the UI and
 * used to sanity-check what the Python optimizer returns.
 *
 * Squad: 15 players — 2 GK, 5 DEF, 5 MID, 3 FWD, max 3 from one club, €100m budget.
 * Starting XI: exactly 11, always 1 GK, then DEF 3-5, MID 2-5, FWD 1-3.
 */

export type Position = "GK" | "DEF" | "MID" | "FWD";

export const POSITIONS: Position[] = ["GK", "DEF", "MID", "FWD"];

export const SQUAD_QUOTA: Record<Position, number> = {
  GK: 2,
  DEF: 5,
  MID: 5,
  FWD: 3,
};

export const XI_MIN: Record<Position, number> = { GK: 1, DEF: 3, MID: 2, FWD: 1 };
export const XI_MAX: Record<Position, number> = { GK: 1, DEF: 5, MID: 5, FWD: 3 };

export const SQUAD_SIZE = 15;
export const XI_SIZE = 11;
export const MAX_PER_CLUB = 3;
export const BUDGET = 100;

export interface Slot {
  position: Position;
  teamId: number;
}

export function countByPosition<T extends { position: Position }>(
  players: T[],
): Record<Position, number> {
  const c: Record<Position, number> = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const p of players) c[p.position] += 1;
  return c;
}

/** Is this set of 11 a legal starting XI? */
export function isValidXI(xi: Slot[]): { ok: boolean; reason?: string } {
  if (xi.length !== XI_SIZE) return { ok: false, reason: `need ${XI_SIZE}, got ${xi.length}` };
  const c = countByPosition(xi);
  for (const pos of POSITIONS) {
    if (c[pos] < XI_MIN[pos]) return { ok: false, reason: `too few ${pos}` };
    if (c[pos] > XI_MAX[pos]) return { ok: false, reason: `too many ${pos}` };
  }
  return { ok: true };
}

/** All formations UEFA allows, as "DEF-MID-FWD" once the keeper is fixed. */
export function legalFormations(): string[] {
  const out: string[] = [];
  for (let d = XI_MIN.DEF; d <= XI_MAX.DEF; d++) {
    for (let m = XI_MIN.MID; m <= XI_MAX.MID; m++) {
      for (let f = XI_MIN.FWD; f <= XI_MAX.FWD; f++) {
        if (1 + d + m + f === XI_SIZE) out.push(`${d}-${m}-${f}`);
      }
    }
  }
  return out;
}
