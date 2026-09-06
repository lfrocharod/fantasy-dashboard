import { EmptyState, PosBadge, StatCard, StatusDot, Section } from "@/components/ui";
import { fmt, money, timeUntil } from "@/lib/format";
import {
  getCurrentMatchday,
  getFixtures,
  getLeagueTable,
  getMySquad,
  type SquadRow,
} from "@/lib/ucl/queries";
import { getSettings, KEYS } from "@/lib/settings";
import { POSITIONS } from "@/lib/ucl/formation";

export const dynamic = "force-dynamic";

export default async function UclOverview() {
  const md = await getCurrentMatchday();
  const [squad, fixtures, table, cfg] = await Promise.all([
    getMySquad(md),
    getFixtures(md),
    getLeagueTable(md),
    getSettings([KEYS.deadline]),
  ]);

  if (squad.length === 0) {
    return (
      <EmptyState
        title={`No squad loaded for matchday ${md}`}
        hint="Connect your UEFA account in Settings, then run the ingestion job."
      />
    );
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

      <Section title="Your squad">
        <div className="card overflow-x-auto">
          <SquadTable rows={squad} captainId={captainPick?.playerId} />
        </div>
        <p className="text-xs text-[var(--muted)]">
          xPts is this model’s projection for the matchday. Captain shown is the raw max —
          see the Optimizer tab for the formation-constrained best XI and transfer ideas.
        </p>
      </Section>

      <Section title={`Matchday ${md} fixtures`}>
        {fixtures.length === 0 ? (
          <EmptyState title="No fixtures loaded for this matchday" />
        ) : (
          <div className="card overflow-x-auto">
            <table className="grid">
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
                    <td>{f.kickoff ? new Date(f.kickoff).toLocaleString() : "TBD"}</td>
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
      </Section>
    </div>
  );
}

function SquadTable({ rows, captainId }: { rows: SquadRow[]; captainId?: number }) {
  const ordered = POSITIONS.flatMap((pos) =>
    rows
      .filter((r) => r.position === pos)
      .sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)),
  );
  return (
    <table className="grid">
      <thead>
        <tr>
          <th>Pos</th>
          <th>Player</th>
          <th>Team</th>
          <th className="num">Price</th>
          <th className="num">Form</th>
          <th className="num">P(start)</th>
          <th className="num">xMin</th>
          <th className="num">xPts</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {ordered.map((r) => (
          <tr key={r.playerId}>
            <td>
              <PosBadge position={r.position} />
            </td>
            <td>
              {r.name} <StatusDot code={r.statusCode} detail={r.statusDetail} />
            </td>
            <td>{r.teamName}</td>
            <td className="num">{fmt(r.price)}</td>
            <td className="num">{fmt(r.uefaForm)}</td>
            <td className="num">{r.pStart != null ? `${Math.round(r.pStart * 100)}%` : "–"}</td>
            <td className="num">{fmt(r.expMinutes, 0)}</td>
            <td className="num font-semibold">{fmt(r.xpts)}</td>
            <td>{r.playerId === captainId ? "🅲" : r.isCaptain ? "(c)" : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
