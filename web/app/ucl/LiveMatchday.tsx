import { Pill, PosBadge, Section, StatCard } from "@/components/ui";
import { dateTime, fmt, relTime } from "@/lib/format";
import type {
  LiveRivals,
  LiveSnapshotPoint,
  LiveSquadRow,
  LiveState,
} from "@/lib/ucl/queries";
import { POSITIONS } from "@/lib/ucl/formation";
import { LiveRefresher } from "@/components/LiveRefresher";

/**
 * Champions-League-only live view. Once a matchday game kicks off, the ingest job
 * (`./run.sh --live`) writes the actual points banked so far plus the manual-sub
 * and armband (keep / change) calls still worth making; this renders it. It
 * re-fetches itself every minute while the state is "live".
 */

function MatchCell({ row }: { row: LiveSquadRow }) {
  if (row.matchState === "finished")
    return <span className="text-[var(--muted)]">✓ FT</span>;
  if (row.matchState === "live")
    return (
      <span className="font-semibold text-[var(--bad)]">
        🔴 {row.minute ? `${row.minute}'` : "LIVE"}
      </span>
    );
  if (row.matchState === "upcoming")
    return (
      <span className="text-[var(--muted)]" title={row.kickoff ? dateTime(row.kickoff) : ""}>
        ⏳ {row.kickoff ? dateTime(row.kickoff) : "TBD"}
      </span>
    );
  return <span className="text-[var(--muted)]">–</span>;
}

function RoleTag({ role }: { role: LiveSquadRow["effRole"] }) {
  if (role === "auto-in") return <Pill tone="good">auto-sub in</Pill>;
  if (role === "auto-out") return <Pill tone="bad">auto-sub out</Pill>;
  return null;
}

/** Tiny inline SVG: projected finish + secured over the matchday, with the
 * pre-match projection as a dashed baseline. */
function Sparkline({ points }: { points: LiveSnapshotPoint[] }) {
  if (points.length < 2) return null;
  const W = 320;
  const H = 64;
  const pad = 4;
  const ys = points.flatMap((p) => [p.projected, p.secured, p.preMatch]);
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - lo) / span) * (H - 2 * pad);
  const path = (sel: (p: LiveSnapshotPoint) => number) =>
    points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(sel(p)).toFixed(1)}`).join(" ");
  const base = y(points[points.length - 1].preMatch);
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-16 w-full max-w-sm"
      preserveAspectRatio="none"
      role="img"
      aria-label="projected and secured points over the matchday"
    >
      <line
        x1={pad}
        x2={W - pad}
        y1={base}
        y2={base}
        stroke="var(--muted)"
        strokeDasharray="3 3"
        strokeWidth={1}
      />
      <path d={path((p) => p.projected)} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      <path d={path((p) => p.secured)} fill="none" stroke="var(--good)" strokeWidth={1.5} />
    </svg>
  );
}

function RivalTable({ rivals }: { rivals: LiveRivals }) {
  return (
    <div className="card table-wrap">
      <table className="dtable">
        <thead>
          <tr>
            <th>#</th>
            <th>Manager</th>
            <th className="num">Secured</th>
            <th className="num">Proj. finish</th>
            <th className="num">vs you</th>
          </tr>
        </thead>
        <tbody>
          {rivals.rows.map((r) => (
            <tr key={r.entryId} className={r.mine ? "font-semibold" : undefined}>
              <td>{r.rank || "–"}</td>
              <td>
                {r.managerName || r.teamName}
                {r.mine && <span className="ml-1 text-[var(--accent)]">(you)</span>}
                <span className="ml-1 text-xs text-[var(--muted)]">{r.played} played</span>
              </td>
              <td className="num">{fmt(r.secured, 0)}</td>
              <td className="num">{fmt(r.projected, 0)}</td>
              <td
                className="num"
                style={{
                  color: r.mine
                    ? "var(--muted)"
                    : (r.liveGapVsMe ?? 0) > 0
                      ? "var(--bad)"
                      : "var(--good)",
                }}
              >
                {r.mine ? "–" : `${(r.liveGapVsMe ?? 0) >= 0 ? "+" : ""}${fmt(r.liveGapVsMe, 0)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LiveMatchday({
  live,
  history = [],
  rivals = null,
}: {
  live: LiveState;
  history?: LiveSnapshotPoint[];
  rivals?: LiveRivals | null;
}) {
  const delta = live.projectedFinish - live.preMatchProjection;
  const cap = live.captain;

  const ordered = POSITIONS.flatMap((pos) => {
    const inPos = live.squad.filter((r) => r.position === pos);
    const rank = (r: LiveSquadRow) =>
      (r.effRole === "auto-out" ? 2 : r.isStarter ? 0 : 1) * 100 + r.benchOrder;
    return inPos.sort((a, b) => rank(a) - rank(b) || b.xpts - a.xpts);
  });

  return (
    <Section
      title={`Live — matchday ${live.matchday}`}
      right={
        <span className="text-xs text-[var(--muted)]">
          {live.state === "finished" ? "all games finished" : "in progress"} · as of{" "}
          {relTime(live.generatedAt)} · re-run <code>./run.sh --live</code> to refresh
        </span>
      }
    >
      <LiveRefresher active={live.state === "live"} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Secured"
          value={fmt(live.securedPoints, 0)}
          sub="banked so far (incl. captain)"
        />
        <StatCard
          label="Projected finish"
          value={fmt(live.projectedFinish, 0)}
          sub={`${delta >= 0 ? "+" : ""}${fmt(delta, 0)} vs pre-match ${fmt(
            live.preMatchProjection,
            0,
          )}`}
        />
        <StatCard
          label="Played"
          value={`${live.played}/${live.starters}`}
          sub={`${live.toPlay} still to play`}
        />
        <StatCard
          label="Captain"
          value={(cap?.name ?? "–").split(" ").slice(-1)[0]}
          sub={
            cap?.recommendation === "switch" && cap.switch
              ? `CHANGE → ${cap.switch.toName.split(" ").slice(-1)[0]} (+${fmt(cap.switch.gain, 1)})`
              : cap?.recommendation === "keep"
                ? "KEEP — top projection"
                : cap?.effectiveName === null
                  ? `no ×2 — ${cap.name.split(" ").slice(-1)[0]} blanked`
                  : cap?.matchState === "finished"
                    ? `${(cap?.actual ?? 0) * 2} pts (×2)`
                    : cap?.locked
                      ? "locked in"
                      : "not started"
          }
        />
      </div>

      {history.length >= 2 && (
        <div className="card p-3">
          <div className="mb-1 flex items-center justify-between text-xs text-[var(--muted)]">
            <span>
              <span style={{ color: "var(--accent)" }}>●</span> projected finish{" "}
              <span style={{ color: "var(--good)" }}>●</span> secured · dashed = pre-match
            </span>
            <span>{history.length} snapshots</span>
          </div>
          <Sparkline points={history} />
        </div>
      )}

      {live.fixtures.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          {live.fixtures.map((f) => {
            const done = f.status === "finished" || f.status === "live";
            return (
              <span
                key={f.matchId}
                className="rounded border border-[var(--border)] px-2 py-1"
                title={f.kickoff ? dateTime(f.kickoff) : ""}
              >
                <span className="text-[var(--muted)]">{f.home}</span>{" "}
                <span className="font-semibold tabular-nums">
                  {done ? `${f.homeGoals ?? 0}–${f.awayGoals ?? 0}` : "v"}
                </span>{" "}
                <span className="text-[var(--muted)]">{f.away}</span>
                {f.status === "live" && <span className="ml-1 text-[var(--bad)]">●</span>}
                {f.status === "upcoming" && f.kickoff && (
                  <span className="ml-1 text-xs text-[var(--muted)]">{dateTime(f.kickoff)}</span>
                )}
              </span>
            );
          })}
        </div>
      )}

      {(live.autoSubs.length > 0 || cap?.note) && (
        <div className="card space-y-1 p-3 text-sm">
          {cap?.note && (
            <div>
              <Pill
                tone={
                  cap.recommendation === "switch"
                    ? "warn"
                    : cap.recommendation === "keep"
                      ? "good"
                      : "accent"
                }
              >
                {cap.recommendation === "switch"
                  ? "CHANGE (C)"
                  : cap.recommendation === "keep"
                    ? "KEEP (C)"
                    : "CAPTAIN"}
              </Pill>{" "}
              {cap.note}
              {cap.recommendation === "switch" && cap.switch && (
                <span className="text-[var(--good)]"> (+{fmt(cap.switch.gain, 1)} proj)</span>
              )}
            </div>
          )}
          {live.autoSubs.map((s, i) => (
            <div key={i}>
              <Pill tone="good">AUTO-SUB</Pill> {s.outName} ({s.outPos}) →{" "}
              <b>{s.inName}</b> ({s.inPos}){s.reason ? ` — ${s.reason}` : ""}
            </div>
          ))}
        </div>
      )}

      {!live.inPlayOpen && (
        <div className="card p-3 text-sm text-[var(--muted)]">
          Every game this matchday kicks off together — no in-play subs and the
          armband can&apos;t be moved once it&apos;s under way.
        </div>
      )}

      {live.manualSubs.length > 0 && (
        <div className="card space-y-1 border-[var(--warn)] p-3 text-sm">
          <div className="font-semibold">
            Manual sub{live.manualSubs.length > 1 ? "s" : ""} still worth making
            <span className="ml-1 font-normal text-[var(--muted)]">
              (their team hasn&apos;t kicked off · up to {live.maxManualSubs} sub-outs
              per matchday, a subbed-out player scores 0)
            </span>
          </div>
          {live.manualSubs.map((s, i) => (
            <div key={i}>
              <Pill tone="warn">SUB {i + 1}</Pill> out {s.outName} ({s.outPos},{" "}
              {s.outActual != null ? `${fmt(s.outActual, 0)} pts` : `proj ${fmt(s.outXpts, 1)}`}) → in{" "}
              <b>{s.inName}</b> ({s.inPos}, proj {fmt(s.inXpts, 1)}){" "}
              <span className="text-[var(--good)]">+{fmt(s.gain, 1)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th>Match</th>
              <th className="num">Actual</th>
              <th className="num">xPts</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((r) => {
              const isCap = r.playerId === live.captain?.effectivePlayerId;
              const mult = isCap ? 2 : 1;
              return (
              <tr
                key={r.playerId}
                style={r.effRole === "auto-out" ? { opacity: 0.5 } : undefined}
              >
                <td>
                  <PosBadge position={r.position} />
                </td>
                <td>
                  {r.name}
                  {isCap && <span title="captain (points doubled)"> (C)</span>}
                  {!isCap && r.isCaptain && (
                    <span title="captain — no double (didn't feature / not moved)"> (C)</span>
                  )}
                  {!r.isStarter && r.effRole === "bench" && (
                    <span className="ml-1 text-xs text-[var(--muted)]">bench {r.benchOrder}</span>
                  )}{" "}
                  <RoleTag role={r.effRole} />
                  <span className="ml-1 text-xs text-[var(--muted)]">
                    {r.opp ? `${r.home ? "v" : "@"} ${r.opp}` : ""}
                  </span>
                </td>
                <td>
                  <MatchCell row={r} />
                </td>
                <td className="num font-semibold">
                  {r.actual != null ? (
                    <>
                      {r.actual * mult}
                      {isCap && <span className="ml-0.5 text-[10px] text-[var(--muted)]">×2</span>}
                    </>
                  ) : r.dnp ? (
                    "0"
                  ) : (
                    "–"
                  )}
                </td>
                <td className="num text-[var(--muted)]">
                  {r.matchState === "finished"
                    ? "–"
                    : `${fmt(r.xpts * mult, 1)}${isCap ? " ×2" : ""}`}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {rivals && rivals.rows.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--muted)]">Mini-league — live</h3>
          <RivalTable rivals={rivals} />
        </div>
      )}
    </Section>
  );
}
