import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { Checklist, EmptyState, Legend, PosBadge, QueryView, Range, SubHeading } from "@/shared/ui";
import { InjTag, MatchupChip } from "./common";

export default function NflOverviewPage() {
  const q = $api.useQuery("get", "/api/nfl/overview");
  return <QueryView query={q}>{(o) => <Overview o={o} />}</QueryView>;
}

function Overview({ o }: { o: Api["NflOverview"] }) {
  if (!o.hasRoster) {
    return (
      <EmptyState
        title="No roster yet"
        hint="Set your ESPN league ID (and cookies for a private league) in the Draft board's Setup — the next scheduled sync pulls your roster."
      />
    );
  }
  const margin = o.oppProj != null ? o.myProj - o.oppProj : 0;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Week {o.week} overview</h1>
        <span className="text-sm text-[var(--muted)]">
          {o.live && (
            <>
              <b style={{ color: o.live.mine >= o.live.opp ? "var(--good)" : "var(--bad)" }}>
                {o.live.final ? "final" : "live"} {fmt(o.live.mine)}–{fmt(o.live.opp)}
              </b>
              {" · "}
            </>
          )}
          projected <b>{fmt(o.myProj, 0)}</b>
          {o.oppProj != null && (
            <>
              {" "}
              vs {o.oppName} <b>{fmt(o.oppProj, 0)}</b> —{" "}
              <span style={{ color: margin >= 0 ? "var(--good)" : "var(--bad)" }}>{o.winPct}% win</span>
            </>
          )}
        </span>
      </div>

      <section className="space-y-2">
        <SubHeading>This week — checklist</SubHeading>
        <Checklist items={o.checklist} />
      </section>

      <section className="space-y-2">
        <SubHeading>Your roster</SubHeading>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num">Wk proj</th>
                <th className="num hide-sm">Range</th>
                <th className="num hide-sm">ROS</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {o.roster.map(({ player: p, starting }) => (
                <tr key={p.extId} style={starting ? undefined : { opacity: 0.55 }}>
                  <td className="font-medium">
                    <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    <InjTag s={p.injury} />
                    {p.onBye && <span className="ml-1 text-[10px] text-[var(--warn)]">BYE</span>}
                  </td>
                  <td>
                    <MatchupChip p={p} />
                  </td>
                  <td className="num font-semibold">{fmt(p.weekPoints)}</td>
                  <td className="num hide-sm">
                    <Range lo={p.lo} hi={p.hi} />
                  </td>
                  <td className="num hide-sm">{fmt(p.rosProj, 0)}</td>
                  <td className="text-[10px] text-[var(--muted)]">{starting ? "start" : "bench"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Legend
        items={[
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Wk proj / ROS", "projected PPR points this week / rest of season"],
          ["Range", "~15th–85th percentile week (floor–ceiling) — the Optimizer uses it to field a floor or ceiling lineup based on your win odds"],
          ["dimmed row", "not in your optimal lineup this week"],
          ["Win %", "from the projected margin vs this week's opponent"],
        ]}
      />
    </div>
  );
}
