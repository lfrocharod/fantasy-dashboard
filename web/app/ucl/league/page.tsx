import { EmptyState, Legend, StatCard, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { getCurrentMatchday, getLeagueHistory, getLeagueTable } from "@/lib/ucl/queries";

export const dynamic = "force-dynamic";

interface EntryAgg {
  entryId: string;
  name: string;
  team: string;
  total: number;
  perMd: number[];
  avg: number;
  best: number;
  worst: number;
  stdev: number;
  form3: number;
  lastRank: number;
}

export default async function LeaguePage() {
  const md = await getCurrentMatchday();
  const [table, history] = await Promise.all([getLeagueTable(md), getLeagueHistory()]);

  if (!table.leagueId) {
    return (
      <EmptyState
        title="No mini-league configured"
        hint="Set your league code / ID in Settings and connect your UEFA account, then run ingestion."
      />
    );
  }
  if (table.rows.length === 0) {
    return (
      <EmptyState
        title={`Mini-league ${table.leagueId} — no standings yet`}
        hint="UEFA only publishes league standings once the first matchday has been played. This fills in automatically after MD1."
      />
    );
  }

  const byEntry = new Map<string, EntryAgg>();
  for (const r of history.rows) {
    let e = byEntry.get(r.entryId);
    if (!e) {
      e = {
        entryId: r.entryId,
        name: r.managerName,
        team: r.teamName,
        total: 0,
        perMd: [],
        avg: 0,
        best: 0,
        worst: Number.POSITIVE_INFINITY,
        stdev: 0,
        form3: 0,
        lastRank: 0,
      };
      byEntry.set(r.entryId, e);
    }
    e.perMd.push(r.points);
    e.total = r.totalPoints;
    e.lastRank = r.rank;
    e.best = Math.max(e.best, r.points);
    e.worst = Math.min(e.worst, r.points);
  }

  const aggs = [...byEntry.values()].map((e) => {
    const n = e.perMd.length || 1;
    e.avg = e.perMd.reduce((a, b) => a + b, 0) / n;
    e.stdev = Math.sqrt(e.perMd.reduce((a, b) => a + (b - e.avg) ** 2, 0) / n);
    e.form3 = e.perMd.slice(-3).reduce((a, b) => a + b, 0);
    if (!Number.isFinite(e.worst)) e.worst = 0;
    return e;
  });

  const powerRanked = [...aggs].sort((a, b) => b.form3 - a.form3);
  const leader = Math.max(...table.rows.map((r) => r.totalPoints), 0);
  const myRow = table.rows.find((r) => r.entryId === table.myEntryId);
  const myAgg = aggs.find((a) => a.entryId === table.myEntryId);

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="My rank" value={myRow?.rank ?? "–"} sub={`of ${table.rows.length}`} />
        <StatCard label="Points behind leader" value={myRow ? leader - myRow.totalPoints : "–"} />
        <StatCard label="My avg / MD" value={fmt(myAgg?.avg ?? 0)} />
        <StatCard
          label="My consistency (σ)"
          value={fmt(myAgg?.stdev ?? 0)}
          sub="lower = steadier"
        />
      </div>

      <Section title={`Standings — after matchday ${md}`}>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>#</th>
                <th>Manager</th>
                <th>Team</th>
                <th className="num">MD pts</th>
                <th className="num">Total</th>
                <th className="num">Move</th>
              </tr>
            </thead>
            <tbody>
              {table.rows.map((r) => {
                const move = r.prevRank ? r.prevRank - r.rank : 0;
                return (
                  <tr
                    key={r.entryId}
                    style={r.entryId === table.myEntryId ? { background: "var(--surface-2)" } : undefined}
                  >
                    <td>{r.rank}</td>
                    <td>{r.managerName}</td>
                    <td>{r.teamName}</td>
                    <td className="num">{r.points}</td>
                    <td className="num font-semibold">{r.totalPoints}</td>
                    <td className="num" style={{ color: move > 0 ? "var(--good)" : move < 0 ? "var(--bad)" : "var(--muted)" }}>
                      {move > 0 ? `▲${move}` : move < 0 ? `▼${-move}` : "–"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Power ranking (last 3 matchdays)">
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>#</th>
                <th>Manager</th>
                <th className="num">Last 3</th>
                <th className="num">Avg/MD</th>
                <th className="num">Best</th>
                <th className="num">Worst</th>
                <th className="num">σ</th>
                <th className="num">Table rank</th>
              </tr>
            </thead>
            <tbody>
              {powerRanked.map((e, i) => (
                <tr
                  key={e.entryId}
                  style={e.entryId === table.myEntryId ? { background: "var(--surface-2)" } : undefined}
                >
                  <td>{i + 1}</td>
                  <td>{e.name}</td>
                  <td className="num font-semibold">{e.form3}</td>
                  <td className="num">{fmt(e.avg)}</td>
                  <td className="num">{e.best}</td>
                  <td className="num">{e.worst}</td>
                  <td className="num">{fmt(e.stdev)}</td>
                  <td className="num">{e.lastRank}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Legend
          items={[
            ["MD pts", "points scored in the latest matchday"],
            ["Move", "rank change vs the previous matchday"],
            ["Last 3", "total points over the last three matchdays"],
            ["Avg/MD", "average points per matchday"],
            ["σ", "standard deviation of matchday points — lower = more consistent"],
          ]}
        />
        <p className="text-xs text-[var(--muted)]">
          Power ranking sorts by recent scoring, not cumulative total — it shows who’s hot
          regardless of the table.
        </p>
      </Section>
    </div>
  );
}
