import { $api, type Api } from "@/api/client";
import { EmptyState, QueryView, SubHeading } from "@/shared/ui";
import { dayLabel } from "./common";

export default function NbaSchedulePage() {
  const q = $api.useQuery("get", "/api/nba/schedule");
  return <QueryView query={q}>{(s) => <Schedule s={s} />}</QueryView>;
}

// games in a matchup: more is better in a points league
function shade(n: number, max: number): string | undefined {
  if (!max) return undefined;
  const t = n / max;
  if (t >= 0.9) return "color-mix(in srgb, var(--good) 30%, transparent)";
  if (t >= 0.7) return "color-mix(in srgb, var(--good) 14%, transparent)";
  if (t <= 0.45) return "color-mix(in srgb, var(--bad) 18%, transparent)";
  return undefined;
}

function Schedule({ s }: { s: Api["NbaScheduleResponse"] }) {
  if (s.periods.length === 0) return <EmptyState title="No NBA schedule yet" hint="Waiting for the first NBA sync." />;
  const max = s.periods.map((_, i) => Math.max(0, ...s.teams.map((t) => t.games[i] ?? 0)));
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">NBA schedule</h1>

      <section className="space-y-2">
        <SubHeading>Game days — this matchup and next</SubHeading>
        <div className="flex flex-wrap gap-1.5">
          {s.days.map((d) => (
            <div key={d.day} className="card min-w-[4.5rem] px-2 py-1.5 text-center text-xs"
              style={d.light ? { borderColor: "var(--accent)" } : undefined}
              title={`${d.games} NBA games · ${d.myGames} of your players play`}>
              <div className="text-[var(--muted)]">{dayLabel(d.date)}</div>
              <div className="text-base font-semibold tabular-nums">{d.games}</div>
              <div className="text-[var(--muted)]">you {d.myGames}</div>
              {d.light && <div className="font-semibold text-[var(--accent)]">light</div>}
            </div>
          ))}
        </div>
        <p className="text-xs text-[var(--muted)]">
          NBA games that day and how many of your players have one. On <b>light</b> days few teams play, so the free
          agents who do are the easiest streams — your slots are emptiest then too.
        </p>
      </section>

      <section className="space-y-2">
        <SubHeading>Games per matchup, by NBA team</SubHeading>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Team</th>
                {s.periods.map((p) => (
                  <th key={p.period} className="num" title={`${dayLabel(p.firstDate)} – ${dayLabel(p.lastDate)}`}>
                    {p.playoffs ? "PO " : "M"}
                    {p.period}
                  </th>
                ))}
                <th className="num">Yours</th>
              </tr>
            </thead>
            <tbody>
              {s.teams.map((t) => (
                <tr key={t.team}>
                  <td className="font-medium" title={t.name}>
                    {t.team}
                  </td>
                  {t.games.map((n, i) => (
                    <td key={s.periods[i].period} className="num tabular-nums" style={{ background: shade(n, max[i]) }}>
                      {n}
                    </td>
                  ))}
                  <td className="num text-[var(--muted)]">{t.mine || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          The current matchup counts from today. PO columns are the fantasy playoff rounds (two weeks each) — games then
          decide titles, so they're worth a look before the trade deadline.
        </p>
      </section>
    </div>
  );
}
