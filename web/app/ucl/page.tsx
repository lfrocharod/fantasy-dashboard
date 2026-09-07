import { EmptyState, Legend, Pill, PosBadge, StatCard, StatusDot, Section } from "@/components/ui";
import { fmt, money, timeUntil, dateTime } from "@/lib/format";
import {
  getCurrentMatchday,
  getFixtures,
  getLeagueTable,
  getMySquad,
  type SquadRow,
} from "@/lib/ucl/queries";
import { getSetting, getSettings, KEYS } from "@/lib/settings";
import { POSITIONS } from "@/lib/ucl/formation";

interface Check {
  ok: boolean;
  text: string;
}

function buildChecklist(squad: SquadRow[], opt: Record<string, unknown>): Check[] {
  const checks: Check[] = [];
  const cap = squad.find((r) => r.isCaptain);
  const safe = (opt.captains as { safePick?: { playerId?: number; name?: string } } | undefined)?.safePick;
  checks.push({
    ok: !!cap && (!safe || cap.playerId === safe.playerId),
    text: cap
      ? safe && cap.playerId !== safe.playerId
        ? `Captain is ${cap.name} — model prefers ${safe.name}`
        : `Captain set (${cap.name})`
      : "No captain set",
  });
  const starters = squad.filter((r) => r.isStarter);
  const flagged = starters.filter((r) => (r.statusCode ?? 0) >= 1 || (r.startProb ?? 1) < 0.5);
  checks.push({
    ok: flagged.length === 0,
    text: flagged.length
      ? `${flagged.length} starter(s) injured / rotation risk: ${flagged.map((r) => r.name).join(", ")}`
      : "No injury or rotation flags in your XI",
  });
  const benched = starters.length < 11;
  checks.push({ ok: !benched, text: benched ? `Only ${starters.length} starters set` : "Full XI selected" });
  const timing = opt.matchdayTiming as { days?: number; liveOptions?: string[] } | undefined;
  if (timing?.days && timing.days > 1 && timing.liveOptions?.length) {
    checks.push({
      ok: true,
      text: `Bench your day-${timing.days} players as live options: ${timing.liveOptions.slice(0, 3).join(", ")}`,
    });
  }
  const transfers = opt.transfers as unknown[] | undefined;
  if (transfers?.length) {
    checks.push({ ok: false, text: `${transfers.length} transfer(s) suggested — see Optimizer` });
  }
  return checks;
}

export const dynamic = "force-dynamic";

export default async function UclOverview() {
  const md = await getCurrentMatchday();
  const [squad, fixtures, table, cfg, optRaw] = await Promise.all([
    getMySquad(md),
    getFixtures(md),
    getLeagueTable(md),
    getSettings([KEYS.deadline]),
    getSetting(KEYS.optimizerOutput),
  ]);
  let opt: Record<string, unknown> = {};
  try {
    opt = optRaw ? JSON.parse(optRaw) : {};
  } catch {
    /* ignore */
  }

  if (squad.length === 0) {
    return (
      <EmptyState
        title={`No squad loaded for matchday ${md}`}
        hint="Connect your UEFA account in Settings, then run the ingestion job."
      />
    );
  }

  const oppByTeam: Record<string, { opp: string; home: boolean }> = {};
  for (const f of fixtures) {
    oppByTeam[f.homeTeam] = { opp: f.awayTeam, home: true };
    oppByTeam[f.awayTeam] = { opp: f.homeTeam, home: false };
  }

  const captainPick = [...squad].sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0))[0];
  const projXI = [...squad].sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)).slice(0, 11);
  const projTotal =
    projXI.reduce((a, r) => a + (r.xpts ?? 0), 0) + (captainPick?.xpts ?? 0);
  const myRow = table.rows.find((r) => r.entryId === table.myEntryId);

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Matchday" value={md} />
        <StatCard label="Deadline" value={timeUntil(cfg[KEYS.deadline] ?? null)} />
        <StatCard label="Proj. total" value={fmt(projTotal, 0)} sub="best XI + captain" />
        <StatCard
          label="Captain pick"
          value={captainPick?.name.split(" ").slice(-1)[0] ?? "–"}
          sub={`${fmt(captainPick?.xpts)} xPts`}
        />
        <StatCard label="Squad value" value={money(squad.reduce((a, r) => a + r.price, 0))} />
        <StatCard
          label="League rank"
          value={myRow?.rank ?? "–"}
          sub={table.rows.length ? `of ${table.rows.length}` : undefined}
        />
      </div>

      <Section title="Pre-deadline checklist">
        <div className="card divide-y divide-[var(--border)]">
          {buildChecklist(squad, opt).map((c, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-2 text-sm">
              <Pill tone={c.ok ? "good" : "warn"}>{c.ok ? "OK" : "DO"}</Pill>
              <span>{c.text}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Your squad">
        <div className="card table-wrap">
          <SquadTable rows={squad} captainId={captainPick?.playerId} oppByTeam={oppByTeam} />
        </div>
        <Legend
          items={[
            ["Opp", "this matchday's opponent — (H) home, (A) away; blank = no fixture"],
            ["xPts", "expected points this matchday (our model)"],
            ["xMin", "expected minutes played"],
            ["P(start)", "chance of starting"],
            ["Form", "UEFA points per game this season"],
            ["🅲", "recommended captain (raw max — see Optimizer for the constrained pick)"],
          ]}
        />
      </Section>

      <Section title={`Matchday ${md} fixtures`}>
        {fixtures.length === 0 ? (
          <EmptyState title="No fixtures loaded for this matchday" />
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Kickoff</th>
                  <th>Home</th>
                  <th>Away</th>
                  <th className="num">xG (H)</th>
                  <th className="num">xG (A)</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fixtures.map((f) => (
                  <tr key={String(f.matchId)}>
                    <td>{f.kickoff ? dateTime(f.kickoff) : "TBD"}</td>
                    <td>{f.homeTeam}</td>
                    <td>{f.awayTeam}</td>
                    <td className="num">{fmt(f.homeXg)}</td>
                    <td className="num">{fmt(f.awayXg)}</td>
                    <td>{f.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Legend items={[["xG (H/A)", "expected goals for the home / away team (fixture difficulty)"]]} />
      </Section>
    </div>
  );
}

function SquadTable({
  rows,
  captainId,
  oppByTeam,
}: {
  rows: SquadRow[];
  captainId?: number;
  oppByTeam: Record<string, { opp: string; home: boolean }>;
}) {
  const ordered = POSITIONS.flatMap((pos) =>
    rows
      .filter((r) => r.position === pos)
      .sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)),
  );
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Pos</th>
          <th>Player</th>
          <th>Team</th>
          <th>Opp</th>
          <th className="num">Price</th>
          <th className="num">Form</th>
          <th className="num">P(start)</th>
          <th className="num">xMin</th>
          <th className="num">xPts</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {ordered.map((r) => {
          const fx = oppByTeam[r.teamName];
          return (
          <tr key={r.playerId}>
            <td>
              <PosBadge position={r.position} />
            </td>
            <td>
              {r.name} <StatusDot code={r.statusCode} detail={r.statusDetail} />
            </td>
            <td>{r.teamName}</td>
            <td className="text-[var(--muted)]">
              {fx ? `${fx.opp} (${fx.home ? "H" : "A"})` : "–"}
            </td>
            <td className="num">{fmt(r.price)}</td>
            <td className="num">{fmt(r.uefaForm)}</td>
            <td className="num">{r.pStart != null ? `${Math.round(r.pStart * 100)}%` : "–"}</td>
            <td className="num">{fmt(r.expMinutes, 0)}</td>
            <td className="num font-semibold">{fmt(r.xpts)}</td>
            <td>{r.playerId === captainId ? "🅲" : r.isCaptain ? "(c)" : ""}</td>
          </tr>
          );
        })}
      </tbody>
    </table>
  );
}
