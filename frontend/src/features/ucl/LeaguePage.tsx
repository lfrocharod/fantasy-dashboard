import { $api, type Api } from "@/api/client";
import { fmt, signed } from "@/shared/format";
import { EmptyState, Legend, QueryView, Section, StatCard } from "@/shared/ui";

const MINE = { background: "var(--surface-2)" };

export default function LeaguePage() {
  const q = $api.useQuery("get", "/api/ucl/league");
  return <QueryView query={q}>{(d) => <League d={d} />}</QueryView>;
}

function League({ d }: { d: Api["LeagueResponse"] }) {
  if (!d.leagueId) {
    return (
      <EmptyState
        title="No mini-league configured"
        hint="Set your league code / ID in Settings and connect your UEFA account; the next sync fills this in."
      />
    );
  }
  if (d.standings.length === 0) {
    return (
      <EmptyState
        title={`Mini-league ${d.leagueId} — no standings yet`}
        hint="UEFA only publishes league standings once the first matchday has been played. This fills in automatically after MD1."
      />
    );
  }
  const me = d.standings.find((r) => r.mine);
  const myAgg = d.powerRanking.find((a) => a.mine);
  const myFinish = d.finish.find((f) => f.mine);
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="My rank" value={me?.rank ?? "–"} sub={`of ${d.standings.length}`} />
        <StatCard label="Points behind leader" value={me ? d.leaderPoints - me.totalPoints : "–"} />
        <StatCard label="My avg / MD" value={fmt(myAgg?.avg ?? 0)} />
        {myFinish ? (
          <StatCard
            label="Projected finish"
            value={`#${myFinish.meanRank.toFixed(1)}`}
            sub={`${Math.round(myFinish.firstPct)}% win · ${Math.round(myFinish.topHalfPct)}% top half`}
          />
        ) : (
          <StatCard label="My consistency (σ)" value={fmt(myAgg?.stdev ?? 0)} sub="lower = steadier" />
        )}
      </div>

      <Section title={`Standings — after matchday ${d.matchday}`}>
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
              {d.standings.map((r) => {
                const move = r.prevRank ? r.prevRank - r.rank : 0;
                return (
                  <tr key={r.entryId} style={r.mine ? MINE : undefined}>
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

      {d.finish.length > 0 && (
        <Section title={`Projected final standings — ${d.mdsLeft} MD left`}>
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
                {d.finish.map((o, i) => (
                  <tr key={o.entryId} style={o.mine ? MINE : undefined}>
                    <td>{i + 1}</td>
                    <td>{o.name}</td>
                    <td className="num text-[var(--muted)]">{o.now}</td>
                    <td className="num font-semibold">{o.projPoints}</td>
                    <td className="num">{o.meanRank.toFixed(1)}</td>
                    <td className="num" style={{ color: o.firstPct >= 20 ? "var(--good)" : undefined }}>
                      {o.firstPct < 1 ? "<1%" : `${Math.round(o.firstPct)}%`}
                    </td>
                    <td className="num">{Math.round(o.topHalfPct)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">
            4,000 simulations of the remaining matchdays — each entry's per-MD scoring drawn from their season average
            (nudged toward the last 3 MDs) with their observed spread.
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
              {d.powerRanking.map((e, i) => (
                <tr key={e.entryId} style={e.mine ? MINE : undefined}>
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
          Power ranking sorts by recent scoring, not cumulative total — it shows who's hot regardless of the table.
        </p>
      </Section>

      {d.calibration && d.calibration.overall.n > 0 && <CalibrationSection cal={d.calibration} />}
    </div>
  );
}

function CalRow({ label, s }: { label: string; s: Api["CalStat"] | undefined }) {
  if (!s?.n) {
    return (
      <tr>
        <td>{label}</td>
        <td className="num text-[var(--muted)]" colSpan={5}>
          —
        </td>
      </tr>
    );
  }
  return (
    <tr>
      <td>{label}</td>
      <td className="num">{s.n}</td>
      <td className="num font-semibold">{fmt(s.mae, 2)}</td>
      <td className="num" style={{ color: Math.abs(s.me ?? 0) > 0.3 ? "var(--warn)" : undefined }}>
        {signed(s.me, 2)}
      </td>
      <td className="num hide-sm">{fmt(s.r, 2)}</td>
      <td className="num">{Math.round((s.band ?? 0) * 100)}%</td>
    </tr>
  );
}

function CalibrationSection({ cal }: { cal: Api["Calibration"] }) {
  const byMd = Object.entries(cal.byMatchday);
  return (
    <Section title="Model calibration">
      <div className="card p-3 text-sm">
        <p className="text-[var(--muted)]">
          How the xPts model has graded against real matchday points over MD {cal.matchdays.join(", ")} (
          {cal.playerMatchdays} player-matchdays). <b className="text-[var(--text)]">{cal.verdict}.</b>
        </p>
        <div className="table-wrap mt-2">
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
              {["GK", "DEF", "MID", "FWD"].map((p) => (
                <CalRow key={p} label={p} s={cal.byPosition[p]} />
              ))}
              {byMd.length > 1 && byMd.map(([m, s]) => <CalRow key={m} label={`MD${m}`} s={s} />)}
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
  );
}
