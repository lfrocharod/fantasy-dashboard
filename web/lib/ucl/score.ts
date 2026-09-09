/**
 * One place for "what will this squad score this matchday" so the overview, the
 * home command-centre card and the rival projection can't drift apart. Mirrors
 * the pre-match total in `ingest/fantasy_ingest/model/live.py` (best XI by xPts +
 * captain doubled).
 */

export interface ScorableRow {
  xpts: number | null;
  isCaptain?: boolean;
}

/**
 * Best 11 by xPts out of a 15-man squad, plus the captain's xPts doubled — the
 * captain if one is flagged and made the XI, otherwise the top scorer.
 */
export function bestXiPlusCaptain<T extends ScorableRow>(
  rows: T[],
): { total: number; xi: T[] } {
  const xi = [...rows].sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)).slice(0, 11);
  const base = xi.reduce((a, r) => a + (r.xpts ?? 0), 0);
  const capRow = xi.find((r) => r.isCaptain);
  const capBonus =
    capRow?.xpts ?? xi.reduce((m, r) => Math.max(m, r.xpts ?? 0), 0);
  return { total: Math.round((base + capBonus) * 10) / 10, xi };
}
