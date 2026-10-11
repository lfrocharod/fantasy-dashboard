import { $api, type Api } from "@/api/client";
import { dateTime, fmt } from "@/shared/format";
import { EmptyState, Legend, QueryView, SubHeading } from "@/shared/ui";
import { Who } from "./common";

export default function NbaStandingsPage() {
  const q = $api.useQuery("get", "/api/nba/standings");
  return <QueryView query={q}>{(s) => <Standings s={s} />}</QueryView>;
}

function Standings({ s }: { s: Api["NbaStandingsResponse"] }) {
  if (s.rows.length === 0) return <EmptyState title="No league table yet" hint="Waiting for the first NBA sync." />;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">League</h1>
        <span className="text-sm text-[var(--muted)]">
          top {s.playoffTeams} make the playoffs · {s.regPeriods} regular matchups
          {s.tradeDeadline && ` · trade deadline ${dateTime(s.tradeDeadline)}`}
        </span>
      </div>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Team</th>
              <th className="num">W-L</th>
              <th className="num">PF</th>
              <th className="num hide-sm">PA</th>
              <th className="num">Proj W</th>
              <th className="num">Playoffs</th>
              <th className="num hide-sm">#1 seed</th>
            </tr>
          </thead>
          <tbody>
            {s.rows.map((r, i) => (
              <tr key={r.teamId} style={r.mine ? { background: "color-mix(in srgb, var(--accent) 10%, transparent)" } : undefined}>
                <td className="num">
                  {i + 1}
                  {i === s.playoffTeams - 1 && <span className="ml-1 text-[10px] text-[var(--muted)]">cut</span>}
                </td>
                <td className={r.mine ? "font-semibold" : undefined}>{r.name}</td>
                <td className="num">
                  {r.wins}-{r.losses}
                  {r.ties ? `-${r.ties}` : ""}
                </td>
                <td className="num">{fmt(r.pf, 0)}</td>
                <td className="num hide-sm">{fmt(r.pa, 0)}</td>
                <td className="num">{fmt(r.projWins)}</td>
                <td className="num font-semibold"
                  style={{ color: r.playoffPct == null ? undefined : r.playoffPct >= 60 ? "var(--good)" : r.playoffPct < 25 ? "var(--bad)" : undefined }}>
                  {r.playoffPct != null ? `${fmt(r.playoffPct, 0)}%` : "–"}
                </td>
                <td className="num hide-sm">{r.topSeedPct != null ? `${fmt(r.topSeedPct, 0)}%` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {s.upcoming.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Your next matchups</SubHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {s.upcoming.map((u) => (
              <div key={u.period} className="card p-3 text-sm">
                <div className="text-xs text-[var(--muted)]">Matchup {u.period}</div>
                <div className="font-semibold">vs {u.oppName}</div>
                <div className="tabular-nums">
                  {fmt(u.myProj, 0)} – {fmt(u.oppProj, 0)}
                  {u.winPct != null && (
                    <span className="ml-2" style={{ color: u.winPct >= 50 ? "var(--good)" : "var(--bad)" }}>{u.winPct}%</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {s.playoffGames.length > 0 && s.playoffPeriods.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Your games in the fantasy playoffs</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  {s.playoffPeriods.map((p) => (
                    <th key={p} className="num">Round {p}</th>
                  ))}
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {s.playoffGames.map((g) => (
                  <tr key={g.player.extId}>
                    <td>
                      <Who p={g.player} />
                    </td>
                    {g.byPeriod.map((n, i) => (
                      <td key={s.playoffPeriods[i]} className="num">{n}</td>
                    ))}
                    <td className="num font-semibold">{g.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["Proj W / Playoffs / #1 seed", "a Monte Carlo of the matchups left: each team's lineup-aware projection, weekly spread, and a season-long doubt about every projection that shrinks as matchups are played"],
          ["Your next matchups", "both teams' projected points for that matchup and your chance to win it"],
          ["Fantasy playoffs", "each round is two weeks; a player with more NBA games then is worth more in a title run"],
        ]}
      />
    </div>
  );
}
