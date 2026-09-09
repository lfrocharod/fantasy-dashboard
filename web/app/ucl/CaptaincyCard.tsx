import { Pill, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { LeagueStrategy } from "@/lib/ucl/queries";

interface CaptainCand {
  playerId: number;
  name: string;
  team: string;
  position: string;
  ev: number; // 2 × xPts
  ceiling: number; // 2 × p85
  floor: number; // 2 × p15
  owned: number; // selected %
}
export interface CaptainsBlob {
  candidates?: CaptainCand[];
  safePick?: CaptainCand | null;
  differentialPick?: CaptainCand | null;
}

const short = (n: string) => n.split(" ").slice(-1)[0];

/**
 * The armband decision as a widget, not a checklist line. Pulls the model's
 * safe / differential picks (2×EV, floor, ceiling) and headlines whichever one
 * your league position calls for — floor when protecting a lead, ceiling when
 * chasing — with a KEEP / CHANGE verdict against the captain you've set.
 */
export function CaptaincyCard({
  captains,
  squadIds,
  currentCaptainId,
  strategy,
}: {
  captains: CaptainsBlob;
  squadIds: Set<number>;
  currentCaptainId: number | null;
  strategy: LeagueStrategy | null;
}) {
  const cands = (captains.candidates ?? []).filter((c) => squadIds.has(c.playerId));
  if (cands.length === 0) return null;

  const inSquad = (c?: CaptainCand | null) => (c && squadIds.has(c.playerId) ? c : null);
  const safe =
    inSquad(captains.safePick) ??
    [...cands].sort((a, b) => 0.6 * b.ev + 0.4 * b.floor - (0.6 * a.ev + 0.4 * a.floor))[0];
  const diff = inSquad(captains.differentialPick);
  const best = [...cands].sort((a, b) => b.ev - a.ev)[0];

  const mode = strategy?.captain ?? "best";
  const pick = mode === "differential" && diff ? diff : mode === "safe" ? safe : best;
  const why =
    mode === "differential" && diff
      ? "you're chasing — take the higher ceiling"
      : mode === "safe"
        ? "protecting a lead — take the higher floor"
        : mode === "match"
          ? "narrow lead — match the field, but this is the model's pick"
          : "highest expected points";

  const current = cands.find((c) => c.playerId === currentCaptainId) ?? null;
  const change = current && pick.playerId !== current.playerId && pick.ev - current.ev >= 0.6;
  const rec: "keep" | "change" | "set" = !current ? "set" : change ? "change" : "keep";

  const rows = [...cands]
    .sort((a, b) => b.ev - a.ev)
    .slice(0, 4);

  return (
    <Section title="Captaincy">
      <div className="card space-y-2 p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={rec === "change" ? "warn" : rec === "keep" ? "good" : "accent"}>
            {rec === "change" ? "CHANGE (C)" : rec === "keep" ? "KEEP (C)" : "SET (C)"}
          </Pill>
          <span>
            {rec === "change" ? (
              <>
                <b>{current!.name}</b> → <b>{pick.name}</b>
              </>
            ) : (
              <b>{pick.name}</b>
            )}{" "}
            <span className="text-[var(--muted)]">
              {pick.ev}×2 proj · floor {fmt(pick.floor, 0)} / ceiling {fmt(pick.ceiling, 0)}
            </span>
          </span>
          <span className="text-xs text-[var(--muted)]">— {why}</span>
        </div>
        {diff && diff.playerId !== pick.playerId && (
          <div className="text-xs text-[var(--muted)]">
            Differential option: <b>{short(diff.name)}</b> (ceiling {fmt(diff.ceiling, 0)}
            {diff.owned ? `, ${fmt(diff.owned, 0)}% owned` : ""})
          </div>
        )}
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Candidate</th>
                <th className="num">×2 proj</th>
                <th className="num">Floor</th>
                <th className="num">Ceiling</th>
                <th className="num hide-sm">Owned</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr
                  key={c.playerId}
                  className={c.playerId === pick.playerId ? "font-semibold" : undefined}
                >
                  <td>
                    {c.name} <span className="text-[var(--muted)]">{c.team}</span>
                    {c.playerId === currentCaptainId && (
                      <span className="ml-1 text-[10px] text-[var(--accent)]">set</span>
                    )}
                  </td>
                  <td className="num">{c.ev}</td>
                  <td className="num text-[var(--muted)]">{fmt(c.floor, 0)}</td>
                  <td className="num">{fmt(c.ceiling, 0)}</td>
                  <td className="num hide-sm text-[var(--muted)]">
                    {c.owned ? `${fmt(c.owned, 0)}%` : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}
