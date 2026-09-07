import Link from "next/link";
import { EmptyState, Pill, Section } from "@/components/ui";
import { fmt, relTime, timeUntil } from "@/lib/format";
import { getHomeSummary, type HomeSummary } from "@/lib/home";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let sum: HomeSummary | null = null;
  let err: string | null = null;
  try {
    sum = await getHomeSummary();
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  if (err || !sum) {
    return (
      <EmptyState
        title="Can't reach the database yet"
        hint={<span className="text-[var(--bad)]">{err}</span>}
      />
    );
  }

  const anyActive = sum.ucl.active || sum.fpl.active || sum.nfl.active;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Command centre</h1>

      {sum.alerts.length > 0 && (
        <div className="card divide-y divide-[var(--border)]">
          {sum.alerts.map((a, i) => (
            <Link
              key={i}
              href={a.href}
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
              Set up a league in <Link href="/settings" className="text-[var(--accent)]">Settings</Link>{" "}
              (or the Draft board&apos;s Setup for NFL), then run the ingest from your machine.
            </>
          }
        />
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <LeagueCard
          href="/ucl"
          title="Champions League"
          active={sum.ucl.active}
          rows={[
            ["Matchday", String(sum.ucl.matchday || "–")],
            ["Deadline", timeUntil(sum.ucl.deadlineIso)],
            ["Proj. XI + captain", fmt(sum.ucl.projected, 0)],
            ["Captain", sum.ucl.captain?.split(" ").slice(-1)[0] ?? "–"],
            ["Mini-league", sum.ucl.rank ? `#${sum.ucl.rank} of ${sum.ucl.leagueSize}` : "after MD1"],
          ]}
          foot={
            sum.ucl.ingestAt
              ? `data ${relTime(sum.ucl.ingestAt)} · ${sum.ucl.ingestOk ? "ok" : "last run failed"}`
              : undefined
          }
        />
        <LeagueCard
          href="/fpl"
          title="FPL Draft"
          active={sum.fpl.active}
          rows={[
            ["Gameweek", sum.fpl.gw ? String(sum.fpl.gw) : "–"],
            ["Best XI proj", fmt(sum.fpl.xiProj, 0)],
            ["Injured in squad", sum.fpl.injured ? String(sum.fpl.injured) : "none"],
            [
              "Top waiver",
              sum.fpl.topClaim ? `${sum.fpl.topClaim.name} (+${sum.fpl.topClaim.gain})` : "—",
            ],
          ]}
        />
        <LeagueCard
          href="/nfl"
          title="NFL"
          active={sum.nfl.active}
          rows={[
            ["Week", sum.nfl.week ? String(sum.nfl.week) : "–"],
            [
              "This week",
              sum.nfl.oppName
                ? `${fmt(sum.nfl.myProj, 0)} vs ${sum.nfl.oppName} ${fmt(sum.nfl.oppProj ?? 0, 0)}`
                : fmt(sum.nfl.myProj, 0),
            ],
            ["Win prob", sum.nfl.winPct != null ? `${sum.nfl.winPct}%` : "–"],
            ["Lineup issues", sum.nfl.lineupIssues ? String(sum.nfl.lineupIssues) : "none"],
            [
              "Top waiver",
              sum.nfl.topClaim ? `${sum.nfl.topClaim.name} (+${sum.nfl.topClaim.gain})` : "—",
            ],
          ]}
        />
      </div>

      <Section title="Jump to">
        <div className="flex flex-wrap gap-2 text-sm">
          {[
            ["/ucl/optimizer", "CL optimizer"],
            ["/ucl/rivals", "CL rivals"],
            ["/fpl", "FPL planner"],
            ["/fpl/trade", "FPL trade lab"],
            ["/nfl", "NFL lineup"],
            ["/nfl/waivers", "NFL waivers"],
            ["/nfl/planner", "NFL bye / playoffs"],
          ].map(([href, label]) => (
            <Link key={href} href={href} className="btn">
              {label}
            </Link>
          ))}
        </div>
      </Section>
    </div>
  );
}

function LeagueCard({
  href,
  title,
  active,
  rows,
  foot,
}: {
  href: string;
  title: string;
  active: boolean;
  rows: [string, string][];
  foot?: string;
}) {
  return (
    <Link
      href={href}
      className="card block p-4 transition-colors hover:border-[var(--accent)]"
    >
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
