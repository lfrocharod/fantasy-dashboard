import type { Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";

export type Player = Api["NflPlayer"];

const INJ_SHORT: Record<string, string> = { QUESTIONABLE: "Q", DOUBTFUL: "D", OUT: "O", IR: "IR", SUSPENSION: "SUS" };

export function InjTag({ s }: { s: string }) {
  if (!s || s === "ACTIVE") return null;
  return <span className="ml-1 text-[10px] font-semibold text-[var(--bad)]">{INJ_SHORT[s] ?? s[0]}</span>;
}

/** This week's opponent as a difficulty-coloured chip. */
export function MatchupChip({ p }: { p: Player }) {
  const m = p.matchups[0];
  return (
    <span className="rounded px-1 text-xs font-medium" style={m?.fdr ? { background: FDR_BG[m.fdr] } : undefined}
      title={m?.fdr ? `matchup ${m.fdr}/5` : ""}>
      {p.onBye ? "BYE" : m?.opp || "—"}
    </span>
  );
}

/** Recent snap / target share with trend and role tags (nflverse). */
export function Usage({ p }: { p: Player }) {
  if (p.usageGames < 1) return <span className="text-[var(--muted)]">–</span>;
  const parts: string[] = [];
  if (p.snapPct) parts.push(`${Math.round(p.snapPct * 100)}% snaps`);
  if (p.targetShare) parts.push(`${Math.round(p.targetShare * 100)}% tgt`);
  return (
    <span style={p.usageStale ? { opacity: 0.6 } : undefined}
      title={`${p.usageStale ? "last season · " : `last ${p.usageGames}g · `}${parts.join(" · ")} · wopr ${p.wopr.toFixed(2)} · ${p.touches.toFixed(0)} touches/g`}>
      {p.snapPct ? `${Math.round(p.snapPct * 100)}%` : p.targetShare ? `${Math.round(p.targetShare * 100)}%t` : "–"}
      {p.snapTrend >= 0.08 && <span className="text-[var(--good)]"> ▲</span>}
      {p.snapTrend <= -0.08 && <span className="text-[var(--bad)]"> ▼</span>}
      {p.usageTag === "workhorse" && <span className="ml-1 rounded bg-[var(--good)] px-1 text-[9px] font-bold text-white">W</span>}
      {p.usageTag === "rotational" && <span className="ml-1 text-[9px] text-[var(--warn)]">rot</span>}
    </span>
  );
}

export function OppTag({ p }: { p: Player }) {
  if (!p.oppTag) return null;
  return (
    <span className="ml-1 text-[10px] font-semibold" style={{ color: p.oppTag === "buy-low" ? "var(--good)" : "var(--warn)" }}>
      {p.oppTag}
    </span>
  );
}
