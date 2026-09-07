import { EmptyState, Legend } from "@/components/ui";
import { getCurrentMatchday, getFixtureTicker } from "@/lib/ucl/queries";

export const dynamic = "force-dynamic";

const AHEAD = 5;

const DIFF_BG: Record<number, string> = {
  1: "rgba(34,197,94,0.32)",
  2: "rgba(132,204,22,0.24)",
  3: "rgba(148,163,184,0.20)",
  4: "rgba(249,115,22,0.26)",
  5: "rgba(239,68,68,0.34)",
};

export default async function FixtureTickerPage() {
  const md = await getCurrentMatchday();
  const rows = await getFixtureTicker(md, AHEAD);

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No upcoming fixtures"
        hint="Needs the fixtures table populated. Run ./run.sh on your machine."
      />
    );
  }

  const mds = Array.from({ length: AHEAD }, (_, i) => md + i).filter(
    (m) => m <= 8, // league phase only
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--muted)]">
        Fixture difficulty for the next {mds.length} matchday{mds.length === 1 ? "" : "s"}, per club.
        Score blends the opponent&apos;s attacking threat (clean-sheet risk) and how hard they are to
        score against, adjusted for home/away. Teams are sorted easiest run first — good windows to
        target that team&apos;s attackers or buy a defender.
      </p>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Team</th>
              {mds.map((m) => (
                <th key={m} className="num">
                  MD{m}
                </th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.teamId}>
                <td className="font-medium whitespace-nowrap">{r.team}</td>
                {mds.map((m) => {
                  const c = r.cells.find((x) => x.matchday === m);
                  if (!c) {
                    return (
                      <td key={m} className="num text-[var(--muted)]">
                        –
                      </td>
                    );
                  }
                  return (
                    <td
                      key={m}
                      className="num"
                      style={{ background: DIFF_BG[c.difficulty] }}
                      title={`${c.home ? "vs" : "@"} ${c.opp} — difficulty ${c.difficulty}/5`}
                    >
                      <span className="font-semibold">{c.oppCode || c.opp.slice(0, 3).toUpperCase()}</span>
                      <span className="ml-1 text-[10px] text-[var(--muted)]">{c.home ? "H" : "A"}</span>
                    </td>
                  );
                })}
                <td className="num font-semibold">{r.avgDifficulty.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend
        items={[
          ["Green (1–2)", "easy fixture — favour this team's attackers / captaincy, good time to bring in a defender"],
          ["Grey (3)", "neutral"],
          ["Orange / Red (4–5)", "tough fixture — fade attackers, clean sheets unlikely"],
          ["H / A", "home or away"],
          ["Avg", "mean difficulty over the shown matchdays — lower is a better run"],
        ]}
      />
    </div>
  );
}
