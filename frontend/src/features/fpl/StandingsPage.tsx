import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, QueryView, SubHeading } from "@/shared/ui";

const MINE = { background: "rgba(31,111,235,0.08)" };

export default function FplStandingsPage() {
  const q = $api.useQuery("get", "/api/fpl/standings");
  return <QueryView query={q}>{(d) => <Standings d={d} />}</QueryView>;
}

function Standings({ d }: { d: Api["FplStandingsResponse"] }) {
  if (d.rows.length === 0) return <EmptyState title="No standings yet" hint="The next FPL sync pulls the league table." />;
  const p = d.path;
  return (
    <div className="space-y-6">
      {p && (
        <div className="card p-3 text-sm">
          <b>Your path.</b> Projected to finish <b>#{p.projRank}</b>
          {p.nextName && p.toNext > 0 ? (
            <>
              {" "}
              — <b>{p.toNext}</b> pts behind {p.nextName}
            </>
          ) : p.projRank === 1 ? (
            <> — projected champion, hold your ground</>
          ) : null}
          {p.toLeader > 0 && (
            <span className="text-[var(--muted)]">
              {" "}
              ({p.toLeader} behind {p.leaderName})
            </span>
          )}
          {p.moveName && (
            <div className="mt-1 text-[var(--good)]">
              Biggest single move: claim <b>{p.moveName}</b> (+{p.moveGain} rest-of-season).
            </div>
          )}
        </div>
      )}
      <section className="space-y-2">
        <h1 className="text-xl font-semibold">
          Standings <span className="text-sm font-normal text-[var(--muted)]">· {d.isH2H ? "head-to-head" : "total points"}</span>
        </h1>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Manager</th>
                <th className="num">{d.isH2H ? "H2H pts" : "Total"}</th>
                {d.isH2H && <th className="num hide-sm">W-D-L</th>}
                <th className="num">Squad ROS</th>
                <th className="num">Proj. final</th>
                {d.simulated && <th className="num hide-sm">Win</th>}
                {d.simulated && <th className="num hide-sm">Top½</th>}
                <th className="num hide-sm">Gap</th>
              </tr>
            </thead>
            <tbody>
              {d.rows.map((s) => {
                const move = s.rank - s.projRank; // + = climbing
                return (
                  <tr key={s.entryId} style={s.mine ? MINE : undefined}>
                    <td className="num">{s.rank}</td>
                    <td className="font-medium">{s.name}</td>
                    <td className="num font-semibold">{s.total}</td>
                    {d.isH2H && (
                      <td className="num hide-sm">
                        {s.wins ?? 0}-{s.draws ?? 0}-{s.losses ?? 0}
                      </td>
                    )}
                    <td className="num">{fmt(s.ros, 0)}</td>
                    <td className="num">
                      {fmt(s.finalPts, 0)}
                      {move !== 0 && (
                        <span className="ml-1 text-[10px]" style={{ color: move > 0 ? "var(--good)" : "var(--bad)" }}>
                          →#{s.projRank}
                        </span>
                      )}
                    </td>
                    {d.simulated && (
                      <td className="num hide-sm" style={{ color: (s.firstPct ?? 0) >= 20 ? "var(--good)" : undefined }}>
                        {s.firstPct == null ? "–" : s.firstPct < 1 ? "<1%" : `${Math.round(s.firstPct)}%`}
                      </td>
                    )}
                    {d.simulated && <td className="num hide-sm">{s.topHalfPct == null ? "–" : `${Math.round(s.topHalfPct)}%`}</td>}
                    <td className="num hide-sm text-[var(--muted)]">{s.gap <= 0.5 ? "—" : `-${fmt(s.gap, 0)}`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          Rows are the current table. <b>Proj. final</b> = current points + roster's projected rest-of-season output
          (best legal XI each GW); the <b>→#N</b> tag is where that projection puts them (green = climbing, red =
          slipping).
          {d.simulated && (
            <>
              {" "}
              <b>Win / Top½</b> are from 4,000 simulations of the {d.gwsLeft} GW left — each squad's weekly score drawn
              from its projected rate with a ~32% spread.
            </>
          )}
        </p>
      </section>

      {d.isH2H && d.schedule.length > 0 && (
        <section className="space-y-2">
          <SubHeading>H2H schedule — projected</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">GW</th>
                  <th>Home</th>
                  <th className="num">proj</th>
                  <th>Away</th>
                  <th className="num">proj</th>
                  <th>Lean</th>
                </tr>
              </thead>
              <tbody>
                {d.schedule.map((m) => (
                  <tr key={`${m.gw}-${m.home}-${m.away}`} style={m.mine ? MINE : undefined}>
                    <td className="num">{m.gw}</td>
                    <td>{m.home}</td>
                    <td className="num">{fmt(m.homeProj, 0)}</td>
                    <td>{m.away}</td>
                    <td className="num">{fmt(m.awayProj, 0)}</td>
                    <td className="text-xs text-[var(--muted)]">{m.lean}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["Total / H2H pts", d.isH2H ? "league H2H points (win 3 / draw 1)" : "cumulative fantasy points"],
          ["Squad ROS", "roster's total projected points for the rest of the season"],
          ["Proj. final", "current points + squad ROS — a naive end-of-season forecast"],
          ["Gap", "projected points behind the leader"],
        ]}
      />
    </div>
  );
}
