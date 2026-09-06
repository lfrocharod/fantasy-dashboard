import Link from "next/link";
import { StatCard, EmptyState, Section } from "@/components/ui";
import { fmt, money, timeUntil, relTime } from "@/lib/format";
import { getDashboardSummary } from "@/lib/ucl/queries";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let summary: Awaited<ReturnType<typeof getDashboardSummary>> | null = null;
  let err: string | null = null;
  try {
    summary = await getDashboardSummary();
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  if (err) {
    return (
      <EmptyState
        title="Can't reach the database yet"
        hint={
          <>
            Set <code>DATABASE_URL</code> and run <code>npm run db:push</code>, then let the
            ingestion job populate data. <br />
            <span className="text-[var(--bad)]">{err}</span>
          </>
        }
      />
    );
  }

  const s = summary!;
  const noData = s.squadSize === 0 && s.leagueSize === 0;

  return (
    <div className="space-y-8">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <span className="text-sm text-[var(--muted)]">
          Ingestion:{" "}
          {s.ingest ? (
            <span style={{ color: s.ingest.ok ? "var(--good)" : "var(--bad)" }}>
              {s.ingest.ok ? "ok" : "failing"} · {relTime(s.ingest.at as unknown as string)}
            </span>
          ) : (
            "not run yet"
          )}
        </span>
      </div>

      {noData ? (
        <EmptyState
          title="No league data loaded"
          hint={
            <>
              Add your league ID and entry ID in <Link href="/settings" className="text-[var(--accent)]">Settings</Link>,
              then run the ingestion job (GitHub Actions → “ingest”, or <code>python -m fantasy_ingest.run</code> locally).
            </>
          }
        />
      ) : null}

      <Section
        title="Champions League"
        right={
          <Link href="/ucl" className="text-sm text-[var(--accent)]">
            Open →
          </Link>
        }
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard label="Matchday" value={s.matchday} />
          <StatCard label="Deadline" value={timeUntil(s.deadlineIso)} />
          <StatCard
            label="League rank"
            value={s.myRank ?? "–"}
            sub={s.leagueSize ? `of ${s.leagueSize}` : undefined}
          />
          <StatCard label="Last MD pts" value={s.myPointsLast ?? "–"} />
          <StatCard label="Proj. XI pts" value={fmt(s.projectedPoints, 0)} sub="incl. captain" />
          <StatCard label="Squad value" value={money(s.squadValue)} />
        </div>
        {s.authState !== "authed" && (
          <div className="text-sm text-[var(--warn)]">
            UEFA connection: <b>{s.authState}</b> — your squad & mini-league won’t update until a
            valid session cookie is saved in{" "}
            <Link href="/settings" className="text-[var(--accent)]">Settings</Link>.
          </div>
        )}
      </Section>

      <Section title="Other leagues">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {["ESPN NFL", "ESPN NBA", "FPL Draft"].map((name) => (
            <div key={name} className="card p-4 opacity-60">
              <div className="font-medium">{name}</div>
              <div className="mt-1 text-sm text-[var(--muted)]">Module planned — not wired yet.</div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
