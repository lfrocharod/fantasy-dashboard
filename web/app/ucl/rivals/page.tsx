import { EmptyState, Legend, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { getCurrentMatchday, getRivals } from "@/lib/ucl/queries";

export const dynamic = "force-dynamic";

export default async function RivalsPage() {
  const md = await getCurrentMatchday();
  const r = await getRivals(md);

  if (!r.ready) {
    return (
      <EmptyState
        title="Rival tracking populates after matchday 1"
        hint="Once the mini-league has a completed matchday, ./run.sh pulls every rival's squad and this page projects their scores, differentials and template risk."
      />
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-[var(--muted)]">
        Projected matchday {md} scores for your {r.rivalCount} mini-league rival
        {r.rivalCount === 1 ? "" : "s"}, from their saved squads (top 11 by xPts + captain).
        Your projected score: <strong>{fmt(r.myProjectedPoints)}</strong>
        {r.myRank ? ` · currently rank ${r.myRank}` : ""}.
      </p>

      <Section title="Rivals — projected this matchday">
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Manager</th>
                <th className="num">Total</th>
                <th className="num">Proj MD</th>
                <th className="num">vs you</th>
                <th className="num hide-sm">Shared</th>
                <th className="hide-sm">Their differentials (they have, you don&apos;t)</th>
              </tr>
            </thead>
            <tbody>
              {r.rivals.map((v) => (
                <tr key={v.entryId}>
                  <td className="num">{v.rank}</td>
                  <td className="font-medium">
                    {v.managerName || v.teamName || v.entryId}
                    {v.teamName && v.managerName ? (
                      <span className="block text-xs text-[var(--muted)]">{v.teamName}</span>
                    ) : null}
                  </td>
                  <td className="num">{v.totalPoints}</td>
                  <td className="num font-semibold">{fmt(v.projectedPoints)}</td>
                  <td
                    className="num font-semibold"
                    style={{ color: v.gapVsMe > 0 ? "var(--bad, #ef4444)" : "var(--good)" }}
                  >
                    {v.gapVsMe > 0 ? "+" : ""}
                    {fmt(v.gapVsMe)}
                  </td>
                  <td className="num hide-sm">{v.overlap}/15</td>
                  <td className="hide-sm text-xs">
                    {v.theirDifferentials
                      .map((p) => `${p.name} (${fmt(p.xpts)})`)
                      .join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {r.commonThreats.length > 0 && (
        <Section title="Cover candidates — owned by most rivals, not by you">
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">Owned by</th>
                  <th className="num">xPts (MD{md})</th>
                </tr>
              </thead>
              <tbody>
                {r.commonThreats.map((p) => (
                  <tr key={p.playerId}>
                    <td className="font-medium">{p.name}</td>
                    <td className="num">
                      {p.ownedByRivals}/{r.rivalCount}
                    </td>
                    <td className="num font-semibold">{fmt(p.xpts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">
            If you&apos;re protecting a lead, owning these caps your downside. If you&apos;re chasing,
            fade them and attack with the differentials above instead.
          </p>
        </Section>
      )}

      {r.templateRisk.length > 0 && (
        <Section title="Your template picks — how exposed you are">
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">Rivals who also own</th>
                  <th className="num">xPts (MD{md})</th>
                </tr>
              </thead>
              <tbody>
                {r.templateRisk.map((p) => (
                  <tr key={p.playerId}>
                    <td className="font-medium">{p.name}</td>
                    <td className="num">
                      {p.ownedByRivals}/{r.rivalCount}
                    </td>
                    <td className="num">{fmt(p.xpts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <Legend
        items={[
          ["Proj MD", "top 11 by xPts from their 15 + captain (double the top starter)"],
          ["vs you", "their projection minus yours — red means they out-project you this matchday"],
          ["Shared", "players in common with your squad, out of 15"],
          ["Their differentials", "players they own that you don't — where they can gain on you"],
          ["Cover candidates", "widely-owned among rivals but missing from your squad — differential risk against you"],
          ["Template picks", "your players that rivals also hold — safe, but no edge"],
        ]}
      />
    </div>
  );
}
