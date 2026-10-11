import { Link } from "react-router";
import { $api, type Api } from "@/api/client";
import { fmt, lastName, relTime, timeUntil } from "@/shared/format";
import { EmptyState, Pill, QueryView, Section } from "@/shared/ui";

export default function HomePage() {
  const q = $api.useQuery("get", "/api/home");
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Command centre</h1>
      <QueryView query={q}>{(sum) => <Home sum={sum} />}</QueryView>
    </div>
  );
}

function Home({ sum }: { sum: Api["HomeSummary"] }) {
  const anyActive = sum.ucl.active || sum.fpl.active || sum.nfl.active;
  const { ucl, fpl, nfl } = sum;
  return (
    <>
      {sum.alerts.length > 0 && (
        <div className="card divide-y divide-[var(--border)]">
          {sum.alerts.map((a, i) => (
            <Link
              key={i}
              to={a.href}
              className="flex items-center gap-3 px-3 py-2.5 text-sm transition-colors hover:bg-[var(--surface-2)]"
            >
              <Pill tone={a.tone}>{a.league}</Pill>
              <span className="flex-1">{a.text}</span>
              <span className="text-[var(--muted)]">→</span>
            </Link>
          ))}
        </div>
      )}

      {!anyActive && (
        <EmptyState
          title="No league connected yet"
          hint={
            <>
              Set up a league in <Link to="/settings" className="text-[var(--accent)]">Settings</Link>, then let
              the scheduled sync run.
            </>
          }
        />
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <LeagueCard
          to="/ucl"
          title="Champions League"
          active={ucl.active}
          rows={
            ucl.live
              ? [
                  ["Matchday", `${ucl.matchday} · ${ucl.live.state === "finished" ? "FT" : "LIVE"}`],
                  ["Secured", fmt(ucl.live.secured, 0)],
                  ["Proj. finish", fmt(ucl.live.projectedFinish, 0)],
                  ["Played", `${ucl.live.played}/${ucl.live.starters}`],
                  ["Mini-league", ucl.rank ? `#${ucl.rank} of ${ucl.leagueSize}` : "after MD1"],
                ]
              : [
                  ["Matchday", String(ucl.matchday || "–")],
                  ["Deadline", timeUntil(ucl.deadlineIso)],
                  ["Proj. XI + captain", String(ucl.projected)],
                  ["Captain", ucl.captain ? lastName(ucl.captain) : "–"],
                  ["Mini-league", ucl.rank ? `#${ucl.rank} of ${ucl.leagueSize}` : "after MD1"],
                ]
          }
          foot={ucl.ingestAt ? `data ${relTime(ucl.ingestAt)} · ${ucl.ingestOk ? "ok" : "last run failed"}` : undefined}
        />
        <LeagueCard
          to="/fpl"
          title="FPL Draft"
          active={fpl.active}
          rows={[
            ["Gameweek", fpl.gw ? String(fpl.gw) : "–"],
            fpl.live
              ? ["Live GW pts", `${fmt(fpl.live.secured, 0)} (${fpl.live.played}/${fpl.live.starters})`]
              : ["Best XI proj", String(fpl.xiProj)],
            ["League rank", fpl.rank ? `#${fpl.rank}` : "–"],
            ["Injured in squad", fpl.injured ? String(fpl.injured) : "none"],
            ["Top waiver", fpl.topClaim ? `${fpl.topClaim.name} (+${fpl.topClaim.gain})` : "—"],
          ]}
        />
        <LeagueCard
          to="/nfl"
          title="NFL"
          active={nfl.active}
          rows={[
            ["Week", nfl.week ? String(nfl.week) : "–"],
            nfl.live
              ? [
                  nfl.live.final ? "Final" : "Live",
                  `${fmt(nfl.live.mine, 0)}–${fmt(nfl.live.opp, 0)} vs ${nfl.oppName ?? "opp"}`,
                ]
              : ["This week", nfl.oppName ? `${nfl.myProj} vs ${nfl.oppName} ${nfl.oppProj ?? ""}` : String(nfl.myProj)],
            ["Win prob", nfl.winPct != null ? `${nfl.winPct}%` : "–"],
            ["Lineup issues", nfl.lineupIssues ? String(nfl.lineupIssues) : "none"],
            ["Top waiver", nfl.topClaim ? `${nfl.topClaim.name} (+${nfl.topClaim.gain})` : "—"],
          ]}
        />
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-[var(--muted)]">
        {sum.freshness.map((f) => (
          <span key={f.league} style={f.stale ? { color: "var(--warn)" } : undefined}>
            {f.league} data {relTime(f.updatedAt)}
            {f.stale ? " ⚠" : ""}
          </span>
        ))}
      </div>

      <Section title="Jump to">
        <div className="flex flex-wrap gap-2 text-sm">
          {[
            ["/ucl/optimizer", "CL optimizer"],
            ["/ucl/rivals", "CL rivals"],
            ["/fpl/optimizer", "FPL optimizer"],
            ["/fpl/trade", "FPL trade lab"],
            ["/nfl/optimizer", "NFL optimizer"],
            ["/nfl/players", "NFL free agents"],
            ["/nfl/standings", "NFL league"],
          ].map(([to, label]) => (
            <Link key={to} to={to} className="btn">
              {label}
            </Link>
          ))}
        </div>
      </Section>
    </>
  );
}

function LeagueCard({
  to,
  title,
  active,
  rows,
  foot,
}: {
  to: string;
  title: string;
  active: boolean;
  rows: [string, string][];
  foot?: string;
}) {
  return (
    <Link to={to} className="card block p-4 transition-colors hover:border-[var(--accent)]">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">{title}</span>
        {active ? <Pill tone="good">connected</Pill> : <Pill tone="muted">not set up</Pill>}
      </div>
      <dl className="space-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3">
            <dt className="text-[var(--muted)]">{k}</dt>
            <dd className="text-right font-medium tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      {foot && <div className="mt-2 text-xs text-[var(--muted)]">{foot}</div>}
    </Link>
  );
}
