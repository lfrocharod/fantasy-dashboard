import type { Api } from "@/api/client";
import { fmt, lastName } from "@/shared/format";
import { Pill, Section } from "@/shared/ui";

/** The armband as a KEEP / CHANGE / SET call — the pick suits the league
 * position (floor when protecting a lead, ceiling when chasing). */
export function CaptaincyCard({ v }: { v: Api["CaptaincyVerdict"] }) {
  const { recommendation: rec, pick, current, why, differential } = v;
  return (
    <Section title="Captaincy">
      <div className="card space-y-2 p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={rec === "change" ? "warn" : rec === "keep" ? "good" : "accent"}>
            {rec === "change" ? "CHANGE (C)" : rec === "keep" ? "KEEP (C)" : "SET (C)"}
          </Pill>
          <span>
            {rec === "change" && current ? (
              <>
                <b>{current.name}</b> → <b>{pick.name}</b>
              </>
            ) : (
              <b>{pick.name}</b>
            )}{" "}
            <span className="text-[var(--muted)]">
              {fmt(pick.ev, 1)} proj (×2) · floor {fmt(pick.floor, 0)} / ceiling {fmt(pick.ceiling, 0)}
            </span>
          </span>
          <span className="text-xs text-[var(--muted)]">— {why}</span>
        </div>
        {differential && (
          <div className="text-xs text-[var(--muted)]">
            Differential option: <b>{lastName(differential.name)}</b> (ceiling {fmt(differential.ceiling, 0)}
            {differential.owned ? `, ${fmt(differential.owned, 0)}% owned` : ""})
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
              {v.rows.map((c) => (
                <tr key={c.playerId} className={c.playerId === pick.playerId ? "font-semibold" : undefined}>
                  <td>
                    {c.name} <span className="text-[var(--muted)]">{c.team}</span>
                    {current && c.playerId === current.playerId && (
                      <span className="ml-1 text-[10px] text-[var(--accent)]">set</span>
                    )}
                  </td>
                  <td className="num">{fmt(c.ev, 1)}</td>
                  <td className="num text-[var(--muted)]">{fmt(c.floor, 0)}</td>
                  <td className="num">{fmt(c.ceiling, 0)}</td>
                  <td className="num hide-sm text-[var(--muted)]">{c.owned ? `${fmt(c.owned, 0)}%` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}
