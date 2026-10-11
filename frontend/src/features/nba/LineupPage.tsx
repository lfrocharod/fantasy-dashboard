import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, QueryView, StatCard } from "@/shared/ui";
import { ESPN_SETUP_HINT, InjTag, dayLabel } from "./common";

export default function NbaLineupPage() {
  const q = $api.useQuery("get", "/api/nba/lineup");
  return <QueryView query={q}>{(l) => <Lineup l={l} />}</QueryView>;
}

function Lineup({ l }: { l: Api["NbaLineup"] }) {
  if (!l.hasRoster) return <EmptyState title="No roster yet" hint={ESPN_SETUP_HINT} />;
  if (l.days.length === 0) return <EmptyState title="No game days left in this matchup" />;
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Daily lineups · matchup {l.period}</h1>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Projected" value={fmt(l.total, 0)} sub="over the days left" />
        <StatCard label="Starts" value={l.games} />
        <StatCard label="Games on the bench" value={l.lost} sub={l.lost ? "slots full those days" : "none lost"} />
        <StatCard label="Empty slot-days" value={l.openSlots} sub="no eligible player with a game" />
      </div>

      {(l.todayStart.length > 0 || l.todayBench.length > 0) && (
        <div className="card space-y-1 border-[var(--warn)] p-3 text-sm">
          <div className="font-semibold">Fix on ESPN for the next game day</div>
          {l.todayStart.length > 0 && (
            <div>
              <span className="font-semibold text-[var(--good)]">Start</span> {l.todayStart.map((p) => p.name).join(", ")}
            </div>
          )}
          {l.todayBench.length > 0 && (
            <div>
              <span className="font-semibold text-[var(--warn)]">Bench</span> {l.todayBench.map((p) => p.name).join(", ")}
            </div>
          )}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {l.days.map((d) => (
          <div key={d.day} className="card p-3 text-sm">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="font-semibold">{dayLabel(d.date)}</span>
              <span className="text-xs text-[var(--muted)]">
                {fmt(d.points, 0)} pts
                {d.openSlots > 0 && ` · ${d.openSlots} empty`}
              </span>
            </div>
            <table className="dtable">
              <tbody>
                {d.seats.map((s, i) => (
                  <tr key={`${s.slot}-${i}`} style={s.player ? undefined : { opacity: 0.45 }}>
                    <td className="w-10 text-xs text-[var(--muted)]">{s.slot}</td>
                    <td>
                      {s.player ? (
                        <>
                          {s.player.name}
                          <InjTag s={s.player.injury} />
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="text-xs text-[var(--muted)]">{s.opp}</td>
                    <td className="num">{s.player ? fmt(s.player.fppg) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.benched.length > 0 && (
              <div className="mt-2 text-xs text-[var(--warn)]">
                On the bench with a game: {d.benched.map((p) => p.name).join(", ")}
              </div>
            )}
            {d.idle.length > 0 && (
              <div className="mt-1 text-xs text-[var(--muted)]">No game: {d.idle.map((p) => p.name).join(", ")}</div>
            )}
          </div>
        ))}
      </div>
      <p className="text-xs text-[var(--muted)]">
        Each day is the highest-scoring legal lineup from the players with a game: slots are filled exactly (a player
        only goes where ESPN lets him), injury tags weigh less the further ahead the day is, and IR players don't
        start. Set it on ESPN each day — lineups lock game by game.
      </p>
    </div>
  );
}
