/** Fixture-difficulty palette (1 easy … 5 hard). The ratings themselves come
 * from the API; this is only how they are coloured. */
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
export const BYE_BG = "rgba(148,163,184,0.25)";
