/**
 * Position-aware fixture difficulty.
 *
 * Two underlying axes per fixture:
 *   attack difficulty  — how hard to get goals / assists, from how solid the
 *     opponent is defensively (a stingy back line = red for your attackers).
 *   defence difficulty — how hard to keep a clean sheet, from the opponent's
 *     attacking threat.
 *
 * The blend that matters depends on position AND the league's scoring:
 *   GK   — pure clean-sheet.
 *   DEF  — mostly clean-sheet, but defenders DO score/assist (set-pieces,
 *          overlaps), so a real but smaller attacking component.
 *   MID  — mostly attacking, with a little clean-sheet / DefCon weight.
 *   FWD  — pure attacking.
 *
 * Rating convention (matches the ingest): attack > 1 = scores more than average;
 * defence > 1 = concedes MORE than average (leakier). Home teams get a small
 * ease bonus.
 */

export type League = "ucl" | "fpl";
export type Pos = "GK" | "GKP" | "DEF" | "MID" | "FWD";

const scale = (raw: number) => Math.max(1, Math.min(5, Math.round(3 + 2.2 * raw)));

// per-league DEF / MID attacking weight — tuned to scoring:
//  UCL: DEF goal = 6 (= GK, > MID's 5), CS = 4  -> defenders' attacking upside
//       is worth relatively more; MID clean sheet is only 1pt.
//  FPL: DEF goal = 6, CS = 4, DefCon +2 (defenders hit it often) -> clean sheet
//       is the more reliable route; def-mids get DefCon too.
const WEIGHTS: Record<League, { def: [number, number]; mid: [number, number] }> = {
  ucl: { def: [0.58, 0.42], mid: [0.82, 0.18] },
  fpl: { def: [0.66, 0.34], mid: [0.76, 0.24] },
};

export interface PosFdr {
  att: number; // 1..5 difficulty of attacking returns
  def: number; // 1..5 difficulty of a clean sheet
  pos: number; // 1..5 the number to colour by for this position
}

export function posFdr(
  oppAttack: number,
  oppDefence: number,
  isHome: boolean,
  pos: Pos,
  league: League,
): PosFdr {
  const ha = isHome ? -0.32 : 0.32;
  const rawAtt = 1.05 * (1 - oppDefence) + ha;
  const rawDef = 1.05 * (oppAttack - 1) + ha;
  const w = WEIGHTS[league];
  let blend: number;
  if (pos === "GK" || pos === "GKP") blend = rawDef;
  else if (pos === "DEF") blend = w.def[0] * rawDef + w.def[1] * rawAtt;
  else if (pos === "MID") blend = w.mid[0] * rawAtt + w.mid[1] * rawDef;
  else blend = rawAtt; // FWD
  return { att: scale(rawAtt), def: scale(rawDef), pos: scale(blend) };
}

// 1 (easy) … 5 (hard)
export const FDR_TEXT: Record<number, string> = {
  1: "#1a7f37", 2: "#4b9e2f", 3: "var(--muted)", 4: "#d1741f", 5: "#cf222e",
};
export const FDR_BG: Record<number, string> = {
  1: "rgba(34,197,94,0.30)",
  2: "rgba(132,204,22,0.20)",
  3: "rgba(148,163,184,0.14)",
  4: "rgba(249,115,22,0.22)",
  5: "rgba(239,68,68,0.28)",
};
