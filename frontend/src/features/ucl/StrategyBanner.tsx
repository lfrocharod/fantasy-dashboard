import type { Api } from "@/api/client";

const TONE = { protect: "good", hold: "warn", chase: "accent", free: "muted" } as const;
const LABEL = { protect: "PROTECT", hold: "HOLD", chase: "CHASE", free: "FREE ROLL" } as const;

/** Where we stand in the mini-league, and what that means for risk. */
export function StrategyBanner({ s }: { s: Api["LeagueStrategy"] }) {
  const c = `var(--${TONE[s.mode]})`;
  return (
    <div className="card p-3 text-sm" style={{ borderLeft: `3px solid ${c}` }}>
      <b style={{ color: c }}>{LABEL[s.mode]}</b> {s.text}
    </div>
  );
}
