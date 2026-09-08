/**
 * Build a plausible starting XI from a pool of players + a "chance of starting"
 * score, shaped to the team's likely formation.
 *
 * We try every legal outfield shape (3-5 DEF / 2-5 MID / 1-3 FWD, summing to 10)
 * and pick the one whose ten highest-scoring players add up to the most
 * start-probability — with a small nudge toward a back four (the most common
 * shape). This keeps a nailed striker in even when a club fields lots of
 * wide midfielders, and drops to a back four when the fifth defender is a
 * rotation body rather than a starter.
 */

export interface FormationXI<T> {
  xi: T[];
  bench: T[];
  formation: string; // e.g. "4-3-3"
}

interface Opts<T> {
  isGK: (p: T) => boolean;
  isDEF: (p: T) => boolean;
  isMID: (p: T) => boolean;
  isFWD: (p: T) => boolean;
  score: (p: T) => number; // 0..1 chance of starting
  benchN?: number;
}

export function pickFormationXI<T>(pool: T[], o: Opts<T>): FormationXI<T> {
  const byScore = (a: T, b: T) => o.score(b) - o.score(a);
  const gk = [...pool].filter(o.isGK).sort(byScore).slice(0, 1);
  const def = [...pool].filter((p) => !o.isGK(p) && o.isDEF(p)).sort(byScore);
  const mid = [...pool].filter((p) => !o.isGK(p) && o.isMID(p)).sort(byScore);
  const fwd = [...pool].filter((p) => !o.isGK(p) && o.isFWD(p)).sort(byScore);

  const sum = (arr: T[], n: number) =>
    arr.slice(0, n).reduce((s, p) => s + Math.max(0, o.score(p)), 0);

  let best = { d: 4, m: 3, f: 3, total: -Infinity };
  for (let d = 3; d <= 5; d++) {
    for (let f = 1; f <= 3; f++) {
      const m = 10 - d - f;
      if (m < 2 || m > 5) continue;
      if (def.length < d || mid.length < m || fwd.length < f) continue;
      // tiny structural prior: 4 at the back, then 3
      const prior = d === 4 ? 0.03 : d === 3 ? 0.01 : 0;
      const total = sum(def, d) + sum(mid, m) + sum(fwd, f) + prior;
      if (total > best.total) best = { d, m, f, total };
    }
  }
  // data-poor fallback (a line can't be filled): just take the top 10 outfield
  if (best.total === -Infinity) {
    const xi = [...gk, ...[...def, ...mid, ...fwd].sort(byScore).slice(0, 10)];
    const inXi = new Set(xi);
    return {
      xi,
      bench: [...pool].sort(byScore).filter((p) => !inXi.has(p)).slice(0, o.benchN ?? 6),
      formation: "—",
    };
  }

  const xi = [
    ...gk,
    ...def.slice(0, best.d),
    ...mid.slice(0, best.m),
    ...fwd.slice(0, best.f),
  ];
  const inXi = new Set(xi);
  const bench = [...pool].sort(byScore).filter((p) => !inXi.has(p)).slice(0, o.benchN ?? 6);
  return { xi, bench, formation: `${best.d}-${best.m}-${best.f}` };
}
