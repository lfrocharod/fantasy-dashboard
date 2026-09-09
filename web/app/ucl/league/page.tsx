import { EmptyState, Legend, StatCard, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { getCurrentMatchday, getLeagueHistory, getLeagueTable } from "@/lib/ucl/queries";
import { getSetting, KEYS } from "@/lib/settings";

export const dynamic = "force-dynamic";

interface CalStat {
  n: number;
  mae?: number;
  me?: number;
  rmse?: number;
  r?: number;
  mean_pred?: number;
  mean_act?: number;
  band?: number;
}
interface Calibration {
  generatedAt: string;
  matchdays: number[];
  playerMatchdays: number;
  overall: CalStat;
  byPosition: Record<string, CalStat>;
  byMatchday: Record<string, CalStat>;
  verdict: string;
}

function CalRow({ label, s }: { label: string; s: CalStat | undefined }) {
  if (!s?.n)
    return (
      <tr>
        <td>{label}</td>
        <td className="num text-[var(--muted)]" colSpan={5}>
          —
        </td>
      </tr>
    );
  return (
    <tr>
      <td>{label}</td>
      <td className="num">{s.n}</td>
      <td className="num font-semibold">{fmt(s.mae, 2)}</td>
      <td className="num" style={{ color: Math.abs(s.me ?? 0) > 0.3 ? "var(--warn)" : undefined }}>
        {(s.me ?? 0) >= 0 ? "+" : ""}
        {fmt(s.me, 2)}
      </td>
      <td className="num hide-sm">{fmt(s.r, 2)}</td>
      <td className="num">{Math.round((s.band ?? 0) * 100)}%</td>
    </tr>
  );
}

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

const LAST_LEAGUE_MD = 8;

function gauss(mean: number, sd: number): number {
  const u = 1 - Math.random();
  const v = Math.random();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

interface FinishOdds {
  projPoints: number;
  meanRank: number;
  firstPct: number;
  topHalfPct: number;
}

/**
 * Monte-Carlo the rest of the league phase: each entry's remaining matchdays are
 * drawn from their per-MD mean (nudged toward recent form) with an observed
 * spread, floored so a 1–2 MD sample doesn't look certain. Returns projected
 * final points, expected finishing rank, and P(win) / P(top half).
 */
function projectFinish(
  aggs: EntryAgg[],
  currentMd: number,
  iters = 4000,
): Map<string, FinishOdds> | null {
  const remaining = Math.max(0, LAST_LEAGUE_MD - currentMd);
  if (remaining === 0 || aggs.length < 2) return null;
  const rate = (e: EntryAgg) =>
    0.65 * e.avg + 0.35 * (e.form3 / Math.min(3, e.perMd.length || 1));
  const sd = (e: EntryAgg) => Math.max(6, e.stdev);
  const half = Math.ceil(aggs.length / 2);
  const first = new Map(aggs.map((e) => [e.entryId, 0]));
  const topHalf = new Map(aggs.map((e) => [e.entryId, 0]));
  const rankSum = new Map(aggs.map((e) => [e.entryId, 0]));
  for (let it = 0; it < iters; it++) {
    const finals = aggs
      .map((e) => {
        let t = e.total;
        for (let r = 0; r < remaining; r++) t += Math.max(0, gauss(rate(e), sd(e)));
        return { id: e.entryId, t };
      })
      .sort((a, b) => b.t - a.t);
    finals.forEach((f, idx) => {
      rankSum.set(f.id, (rankSum.get(f.id) ?? 0) + idx + 1);
      if (idx === 0) first.set(f.id, (first.get(f.id) ?? 0) + 1);
      if (idx < half) topHalf.set(f.id, (topHalf.get(f.id) ?? 0) + 1);
    });
  }
  return new Map(
    aggs.map((e) => [
      e.entryId,
      {
        projPoints: Math.round(e.total + remaining * rate(e)),
        meanRank: (rankSum.get(e.entryId) ?? 0) / iters,
        firstPct: (100 * (first.get(e.entryId) ?? 0)) / iters,
        topHalfPct: (100 * (topHalf.get(e.entryId) ?? 0)) / iters,
      },
    ]),
  );
}

export default async function LeaguePage() {
  const md = await getCurrentMatchday();
  const [table, history, calRaw] = await Promise.all([
    getLeagueTable(md),
    getLeagueHistory(),
    getSetting(KEYS.calibration),
  ]);
  let cal: Calibration | null = null;
  try {
    cal = calRaw ? (JSON.parse(calRaw) as Calibration) : null;
  } catch {
    cal = null;
  }

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

  const playedMd = Math.max(0, ...history.rows.map((r) => r.matchday));
  const finish = projectFinish(aggs, playedMd);
  const projRows = finish
    ? [...aggs]
        .map((e) => ({ e, o: finish.get(e.entryId)! }))
        .sort((a, b) => a.o.meanRank - b.o.meanRank)
    : [];
  const myFinish = finish?.get(table.myEntryId ?? "");

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="My rank" value={myRow?.rank ?? "–"} sub={`of ${table.rows.length}`} />
        <StatCard label="Points behind leader" value={myRow ? leader - myRow.totalPoints : "–"} />
        <StatCard label="My avg / MD" value={fmt(myAgg?.avg ?? 0)} />
        {myFinish ? (
          <StatCard
            label="Projected finish"
            value={`#${myFinish.meanRank.toFixed(1)}`}
            sub={`${Math.round(myFinish.firstPct)}% win · ${Math.round(myFinish.topHalfPct)}% top half`}
          />
        ) : (
          <StatCard
            label="My consistency (σ)"
            value={fmt(myAgg?.stdev ?? 0)}
            sub="lower = steadier"
          />
        )}
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

      {projRows.length > 0 && (
        <Section title={`Projected final standings — ${LAST_LEAGUE_MD - playedMd} MD left`}>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Proj #</th>
                  <th>Manager</th>
                  <th className="num">Now</th>
                  <th className="num">Proj total</th>
                  <th className="num">Exp. rank</th>
                  <th className="num">Win</th>
                  <th className="num">Top half</th>
                </tr>
              </thead>
              <tbody>
                {projRows.map(({ e, o }, i) => (
                  <tr
                    key={e.entryId}
                    style={
                      e.entryId === table.myEntryId ? { background: "var(--surface-2)" } : undefined
                    }
                  >
                    <td>{i + 1}</td>
                    <td>{e.name}</td>
                    <td className="num text-[var(--muted)]">{e.total}</td>
                    <td className="num font-semibold">{o.projPoints}</td>
                    <td className="num">{o.meanRank.toFixed(1)}</td>
                    <td
                      className="num"
                      style={{ color: o.firstPct >= 20 ? "var(--good)" : undefined }}
                    >
                      {o.firstPct < 1 ? "<1%" : `${Math.round(o.firstPct)}%`}
                    </td>
                    <td className="num">{Math.round(o.topHalfPct)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">
            4,000 simulations of the remaining matchdays — each entry&apos;s per-MD scoring drawn
            from their season average (nudged toward the last 3 MDs) with their observed spread.
          </p>
        </Section>
      )}

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

      {cal && cal.overall.n > 0 && (
        <Section title="Model calibration">
          <div className="card p-3 text-sm">
            <p className="text-[var(--muted)]">
              How the xPts model has graded against real matchday points over MD{" "}
              {cal.matchdays.join(", ")} ({cal.playerMatchdays} player-matchdays).{" "}
              <b className="text-[var(--text)]">{cal.verdict}.</b>
            </p>
            <div className="mt-2 table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th></th>
                    <th className="num">n</th>
                    <th className="num">MAE</th>
                    <th className="num">Bias</th>
                    <th className="num hide-sm">r</th>
                    <th className="num">Band</th>
                  </tr>
                </thead>
                <tbody>
                  <CalRow label="All" s={cal.overall} />
                  {(["GK", "DEF", "MID", "FWD"] as const).map((p) => (
                    <CalRow key={p} label={p} s={cal.byPosition[p]} />
                  ))}
                  {Object.keys(cal.byMatchday).length > 1 &&
                    Object.entries(cal.byMatchday).map(([m, s]) => (
                      <CalRow key={m} label={`MD${m}`} s={s} />
                    ))}
                </tbody>
              </table>
            </div>
          </div>
          <Legend
            items={[
              ["MAE", "mean absolute error — average |actual − projected| points per player"],
              ["Bias", "mean (actual − projected): + = model runs cold, − = runs hot"],
              ["r", "correlation between projected and actual"],
              ["Band", "% of actuals that landed inside the projected floor–ceiling range (target ~70%)"],
            ]}
          />
        </Section>
      )}
    </div>
  );
}
