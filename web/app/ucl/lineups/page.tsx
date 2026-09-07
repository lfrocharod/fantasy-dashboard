import { EmptyState, Legend, PosBadge, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { getCurrentMatchday, getProjectedLineups } from "@/lib/ucl/queries";

export const dynamic = "force-dynamic";

export default async function LineupsPage() {
  const md = await getCurrentMatchday();
  const groups = await getProjectedLineups(md);

  if (groups.length === 0) {
    return (
      <EmptyState
        title={`No projected lineups for matchday ${md}`}
        hint="Needs fixtures + the form data. Run ./run.sh (with sources) on your machine."
      />
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-[var(--muted)]">
        Start probability is data-driven from recent domestic minutes &amp; role (Understat),
        adjusted for injury flags — not a hand-typed predicted XI. Use it as a starting point
        and apply your own read. Players flagged as transferred are hidden.
      </p>

      {groups.map((g) => (
        <Section
          key={g.team}
          title={g.team}
          right={
            g.fixture && (
              <span className="text-sm text-[var(--muted)]">
                {g.fixture.home ? "vs" : "@"} {g.fixture.opp}
              </span>
            )
          }
        >
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Pos</th>
                  <th>Player</th>
                  <th className="num">Start%</th>
                  <th className="num">xMin</th>
                  <th className="num hide-sm">L4 G+A</th>
                  <th className="num">Hot</th>
                  <th className="num">xPts</th>
                  <th className="hide-sm">Note</th>
                </tr>
              </thead>
              <tbody>
                {g.players.map((p) => {
                  const sp = p.startProb ?? 0;
                  const leverage =
                    p.role && p.role !== p.position && ["FWD", "MID"].includes(p.role);
                  return (
                    <tr key={p.playerId} style={sp < 0.4 ? { opacity: 0.5 } : undefined}>
                      <td>
                        <PosBadge position={p.position} />
                        {leverage && (
                          <span
                            className="ml-1 text-[11px] font-semibold text-[var(--warn)]"
                            title={p.roleNote ?? ""}
                          >
                            →{p.role}
                          </span>
                        )}
                      </td>
                      <td className="font-medium">{p.name}</td>
                      <td
                        className="num font-semibold"
                        style={{
                          color:
                            sp >= 0.7 ? "var(--good)" : sp >= 0.4 ? "var(--warn)" : "var(--muted)",
                        }}
                      >
                        {sp ? `${Math.round(sp * 100)}%` : "–"}
                      </td>
                      <td className="num">{fmt(p.expMinutes, 0)}</td>
                      <td className="num hide-sm">
                        {p.recentMatches
                          ? `${fmt((p.recentGoals ?? 0) + (p.recentAssists ?? 0), 0)} / ${p.recentMatches}`
                          : "–"}
                      </td>
                      <td className="num">{p.hotScore ? fmt(p.hotScore, 2) : "–"}</td>
                      <td className="num font-semibold">{fmt(p.xpts)}</td>
                      <td className="hide-sm text-xs text-[var(--muted)]">{p.roleNote}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>
      ))}

      <Legend
        items={[
          ["Start%", "estimated chance of starting (Understat minutes + role, minus injury flags)"],
          ["L4 G+A", "goals + assists in the last 4 domestic matches / matches counted"],
          ["Hot", "recent goal involvement per 90 (form signal)"],
          ["→FWD / →MID", "UEFA lists them further back but they've been playing forward — cheaper price for the output"],
          ["dimmed row", "start% below 40% — rotation risk / fringe"],
        ]}
      />
    </div>
  );
}
