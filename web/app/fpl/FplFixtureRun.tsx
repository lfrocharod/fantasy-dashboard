import { FDR_BG } from "@/lib/fdr";
import { fmt } from "@/lib/format";
import type { FplPlayer } from "./lib";

const clamp5 = (n: number) => Math.max(1, Math.min(5, Math.round(n)));

/**
 * Your squad's schedule swing over the next few GWs: a squad-average difficulty
 * strip on top (which GWs are a wall), then each player's own run, easiest first
 * — so you can see who to bench for a rough patch and who's about to get a green
 * run worth holding.
 */
export function FplFixtureRun({ squad, n = 6 }: { squad: FplPlayer[]; n?: number }) {
  const cols = squad[0]?.gws.slice(0, n) ?? [];
  if (cols.length === 0) return null;
  const gwNums = cols.map((g) => g.gw);

  const colMean = gwNums.map((_g, i) => {
    const v = squad.map((p) => p.gws[i]?.fdrAtt ?? p.gws[i]?.fdr ?? 0).filter((x) => x > 0);
    return v.length ? v.reduce((a, x) => a + x, 0) / v.length : 0;
  });

  const rows = squad
    .map((p) => {
      const cells = p.gws.slice(0, n);
      const v = cells.map((c) => c.fdr).filter((x) => x > 0);
      return { p, cells, mean: v.length ? v.reduce((a, x) => a + x, 0) / v.length : 3 };
    })
    .sort((a, b) => a.mean - b.mean);

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-[var(--muted)]">
        YOUR FIXTURE RUN — next {cols.length} GW
      </h2>
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Player</th>
              {gwNums.map((g) => (
                <th key={g} className="num">
                  GW{g}
                </th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            <tr className="font-semibold">
              <td className="text-[var(--muted)]">Squad avg</td>
              {colMean.map((m, i) => (
                <td
                  key={i}
                  className="num tabular-nums"
                  style={m ? { background: FDR_BG[clamp5(m)] } : undefined}
                >
                  {m ? fmt(m, 1) : "–"}
                </td>
              ))}
              <td className="num">
                {fmt(colMean.filter(Boolean).reduce((a, m) => a + m, 0) / (colMean.filter(Boolean).length || 1), 1)}
              </td>
            </tr>
            {rows.map(({ p, cells, mean }) => (
              <tr key={p.extId}>
                <td className="font-medium">
                  {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                </td>
                {cells.map((c, i) => (
                  <td
                    key={i}
                    className="num text-xs tabular-nums"
                    style={c.fdr ? { background: FDR_BG[c.fdr] } : undefined}
                    title={c.opp ? `${c.opp}${c.home === false ? " (A)" : c.home ? " (H)" : ""} · ${c.fdr}/5` : "blank / no fixture"}
                  >
                    {c.opp ? c.opp.replace(/\s*\(.\)$/, "") : "–"}
                  </td>
                ))}
                <td
                  className="num font-semibold"
                  style={{ background: FDR_BG[clamp5(mean)] }}
                >
                  {fmt(mean, 1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--muted)]">
        Difficulty is position-aware (a defender&apos;s number weighs clean-sheet risk, an
        attacker&apos;s the opponent&apos;s defence). Green = easy run, red = wall.
      </p>
    </section>
  );
}
