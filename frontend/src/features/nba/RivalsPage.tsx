import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, Pill, QueryView } from "@/shared/ui";
import { InjTag } from "./common";

export default function NbaRivalsPage() {
  const q = $api.useQuery("get", "/api/nba/rivals");
  return <QueryView query={q}>{(r) => <Rivals r={r} />}</QueryView>;
}

function Rivals({ r }: { r: Api["NbaRivalsResponse"] }) {
  if (r.teams.length === 0) return <EmptyState title="No teams yet" hint="Waiting for the first NBA sync." />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Rosters · matchup {r.period}</h1>
      <div className="grid gap-3 md:grid-cols-2">
        {r.teams.map((t) => (
          <div key={t.teamId} className="card p-3 text-sm" style={t.isMine ? { borderColor: "var(--accent)" } : undefined}>
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="font-semibold">
                {t.name} {t.isMine && <Pill tone="accent">you</Pill>}
              </span>
              <span className="text-xs text-[var(--muted)]">
                {t.wins}-{t.losses}
                {t.ties ? `-${t.ties}` : ""} · {fmt(t.pf, 0)} PF · {fmt(t.weekProj, 0)} to come this matchup
              </span>
            </div>
            <table className="dtable">
              <tbody>
                {t.players.map((p) => (
                  <tr key={p.extId} style={p.slot === "IR" ? { opacity: 0.5 } : undefined}>
                    <td>
                      {p.name}
                      <span className="ml-1 text-[10px] text-[var(--muted)]">{p.positions.join("/")}</span>
                      <InjTag s={p.injury} />
                    </td>
                    <td className="text-xs text-[var(--muted)]">{p.team}</td>
                    <td className="num">{fmt(p.fppg)}</td>
                    <td className="num text-xs text-[var(--muted)]" title="games left this matchup">{p.gamesLeft}g</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}
