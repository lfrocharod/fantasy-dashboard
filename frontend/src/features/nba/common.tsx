import type { ReactNode } from "react";
import type { Api } from "@/api/client";
import { PosBadge } from "@/shared/ui";

export type Player = Api["NbaPlayer"];

const INJ_SHORT: Record<string, string> = {
  DAY_TO_DAY: "DTD", QUESTIONABLE: "Q", DOUBTFUL: "D", OUT: "OUT", SUSPENSION: "SUS", INJURY_RESERVE: "IR",
};

export function InjTag({ s }: { s: string }) {
  if (!s || s === "ACTIVE") return null;
  const bad = s === "OUT" || s === "SUSPENSION" || s === "INJURY_RESERVE";
  return (
    <span className="ml-1 text-[10px] font-semibold" style={{ color: bad ? "var(--bad)" : "var(--warn)" }} title={s}>
      {INJ_SHORT[s] ?? s}
    </span>
  );
}

/** Name, NBA team, eligible positions and injury tag. */
export function Who({ p, children }: { p: Player; children?: ReactNode }) {
  return (
    <span className="font-medium">
      <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
      {p.positions.length > 1 && <span className="ml-1 text-[10px] text-[var(--muted)]">{p.positions.join("/")}</span>}
      <InjTag s={p.injury} />
      {children}
    </span>
  );
}

/** "2026-10-20" → "Tue Oct 20" (a calendar date: no time zone shifting). */
export function dayLabel(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

/** League, team and season from an ESPN fantasy basketball team-page URL, e.g.
 * fantasy.espn.com/basketball/team?leagueId=1&teamId=2&seasonId=2027. */
export function parseEspnTeamUrl(url: string): { leagueId?: string; teamId?: string; seasonId?: string } {
  const m = (key: string) => url.match(new RegExp(`[?&]${key}=(\\d+)`))?.[1];
  return { leagueId: m("leagueId"), teamId: m("teamId"), seasonId: m("seasonId") };
}

export const ESPN_SETUP_HINT =
  "Set your ESPN league in Setup above — the next scheduled sync pulls your roster, the league and the NBA schedule.";
