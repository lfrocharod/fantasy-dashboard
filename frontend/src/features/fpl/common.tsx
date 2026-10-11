import type { Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";

export type Player = Api["FplPlayer"];
export type Horizon = "short" | "medium" | "season";

const STATUS_LABEL: Record<string, string> = { d: "doubt", i: "injured", s: "susp", u: "unavail", n: "out" };

export const startPct = (p: number) => (p ? `${Math.round(p * 100)}%` : "–");

/** Set-piece duty, injury status and one-booking-from-a-ban, after a name. */
export function Flags({ p, value = false }: { p: Player; value?: boolean }) {
  return (
    <>
      {value && p.oppTag && (
        <span className="ml-1 text-[10px] font-semibold" style={{ color: p.oppTag === "value" ? "var(--good)" : "var(--warn)" }}
          title="season underlying stats (xGI/90, xGC/90) vs current output">
          {p.oppTag}
        </span>
      )}
      {p.setPiece && <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">{p.setPiece.replace("PK2", "PK²")}</span>}
      {STATUS_LABEL[p.status] && (
        <span className="ml-1 text-[10px] text-[var(--bad)]" title={p.news}>
          {STATUS_LABEL[p.status]}
        </span>
      )}
      {p.suspRisk && (
        <span className="ml-1 text-[var(--warn)]" title={`${p.ycToBan} booking from a ban`}>
          ⚑
        </span>
      )}
    </>
  );
}

/** One gameweek's fixture, coloured by (position-aware) difficulty. */
export function GwTd({ c, xpts = false }: { c: Api["GwCell"] | undefined; xpts?: boolean }) {
  if (!c || !c.opp) return <td className="num text-xs text-[var(--muted)]">–</td>;
  return (
    <td className="num text-xs tabular-nums" style={c.fdr ? { background: FDR_BG[c.fdr] } : undefined}
      title={`${c.opp} · difficulty ${c.fdr}/5${c.fdrAtt ? ` (goals/assists ${c.fdrAtt}/5, clean sheet ${c.fdrDef}/5)` : ""}`}>
      {xpts ? c.xpts.toFixed(1) : c.opp.replace(/\s*\(.\)$/, "")}
    </td>
  );
}

export const clamp5 = (n: number) => Math.max(1, Math.min(5, Math.round(n)));

export const HORIZON_LABEL: Record<Horizon, string> = {
  short: "next GW",
  medium: "next 6 GW",
  season: "rest of season",
};
export const HORIZONS = ["short", "medium", "season"] as const;
