import type { Api } from "@/api/client";
import { dateTime, fmt, lastName, relTime, signed } from "@/shared/format";
import { Pill, PosBadge, Section, StatCard } from "@/shared/ui";

type Live = Api["LiveState"];
type Row = Api["LiveSquadRow"];
const POSITIONS = ["GK", "DEF", "MID", "FWD"];

function MatchCell({ row }: { row: Row }) {
  if (row.matchState === "finished") return <span className="text-[var(--muted)]">✓ FT</span>;
  if (row.matchState === "live")
    return <span className="font-semibold text-[var(--bad)]">🔴 {row.minute ? `${row.minute}'` : "LIVE"}</span>;
  if (row.matchState === "upcoming")
    return <span className="text-[var(--muted)]">⏳ {row.kickoff ? dateTime(row.kickoff) : "TBD"}</span>;
  return <span className="text-[var(--muted)]">–</span>;
}

/** Projected finish + secured over the matchday; pre-match as a dashed line. */
function Sparkline({ points }: { points: Api["LiveSnapshotPoint"][] }) {
  if (points.length < 2) return null;
  const W = 320, H = 64, pad = 4;
  const ys = points.flatMap((p) => [p.projected, p.secured, p.preMatch]);
  const lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - lo) / span) * (H - 2 * pad);
  const path = (sel: (p: Api["LiveSnapshotPoint"]) => number) =>
    points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(sel(p)).toFixed(1)}`).join(" ");
  const base = y(points[points.length - 1].preMatch);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-16 w-full max-w-sm" preserveAspectRatio="none" role="img"
      aria-label="projected and secured points over the matchday">
      <line x1={pad} x2={W - pad} y1={base} y2={base} stroke="var(--muted)" strokeDasharray="3 3" strokeWidth={1} />
      <path d={path((p) => p.projected)} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      <path d={path((p) => p.secured)} fill="none" stroke="var(--good)" strokeWidth={1.5} />
    </svg>
  );
}

export function LiveRivalTable({ rivals }: { rivals: Api["LiveRivals"] }) {
  // once every game is over, secured and projected are the same number
  const final = rivals.state === "finished";
  return (
    <div className="card table-wrap">
      <table className="dtable">
        <thead>
          <tr>
            <th>#</th>
            <th>Manager</th>
            <th className="num">Played</th>
            {final ? (
              <th className="num">Points</th>
            ) : (
              <>
                <th className="num">Secured</th>
                <th className="num">Proj. finish</th>
              </>
            )}
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
              </td>
              <td className="num">{r.played}</td>
              {!final && <td className="num">{fmt(r.secured, 0)}</td>}
              <td className="num">{fmt(r.projected, 0)}</td>
              <td className="num" style={{
                color: r.mine ? "var(--muted)" : (r.liveGapVsMe ?? 0) > 0 ? "var(--bad)" : "var(--good)",
              }}>
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
  history,
  rivals,
}: {
  live: Live;
  history: Api["LiveSnapshotPoint"][];
  rivals: Api["LiveRivals"] | null | undefined;
}) {
  const final = live.state === "finished";
  const delta = live.projectedFinish - live.preMatchProjection;
  const cap = live.captain;
  const rank = (r: Row) => (r.effRole === "auto-out" ? 2 : r.isStarter ? 0 : 1) * 100 + r.benchOrder;
  const ordered = POSITIONS.flatMap((pos) =>
    live.squad.filter((r) => r.position === pos).sort((a, b) => rank(a) - rank(b) || b.xpts - a.xpts),
  );
  const captainSub =
    cap?.recommendation === "switch" && cap.switch
      ? `CHANGE → ${lastName(cap.switch.toName)} (+${fmt(cap.switch.gain, 1)})`
      : cap?.recommendation === "keep"
        ? "KEEP the armband"
        : cap && cap.effectiveName === null
          ? `no ×2 — ${lastName(cap.name)} blanked`
          : cap?.matchState === "finished"
            ? `${(cap.actual ?? 0) * 2} pts (×2)`
            : cap?.locked
              ? "locked in"
              : "not started";

  return (
    <Section
      title={final ? `Matchday ${live.matchday} — final` : `Live — matchday ${live.matchday}`}
      right={
        <span className="text-xs text-[var(--muted)]">
          {final ? "all games finished" : "in progress · refreshes every minute"} · data{" "}
          {relTime(live.generatedAt)}
        </span>
      }
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {final ? (
          <>
            <StatCard label="Final score" value={fmt(live.securedPoints, 0)} sub="incl. captain and auto-subs" />
            <StatCard
              label="vs pre-match"
              value={signed(delta, 0)}
              sub={`projected ${fmt(live.preMatchProjection, 0)} before kickoff`}
            />
          </>
        ) : (
          <>
            <StatCard label="Secured" value={fmt(live.securedPoints, 0)} sub="banked so far (incl. captain)" />
            <StatCard
              label="Projected finish"
              value={fmt(live.projectedFinish, 0)}
              sub={`${signed(delta, 0)} vs pre-match ${fmt(live.preMatchProjection, 0)}`}
            />
          </>
        )}
        <StatCard
          label="Played"
          value={`${live.played}/${live.starters}`}
          sub={final ? `${live.autoSubs.length} auto-sub${live.autoSubs.length === 1 ? "" : "s"}` : `${live.toPlay} still to play`}
        />
        <StatCard label="Captain" value={lastName(cap?.name)} sub={captainSub} />
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
              <span key={f.matchId} className="rounded border border-[var(--border)] px-2 py-1">
                <span className="text-[var(--muted)]">{f.home}</span>{" "}
                <span className="font-semibold tabular-nums">{done ? `${f.homeGoals ?? 0}–${f.awayGoals ?? 0}` : "v"}</span>{" "}
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
              <Pill tone={cap.recommendation === "switch" ? "warn" : cap.recommendation === "keep" ? "good" : "accent"}>
                {cap.recommendation === "switch" ? "CHANGE (C)" : cap.recommendation === "keep" ? "KEEP (C)" : "CAPTAIN"}
              </Pill>{" "}
              {cap.note}
            </div>
          )}
          {live.autoSubs.map((s, i) => (
            <div key={i}>
              <Pill tone="good">AUTO-SUB</Pill> {s.outName} ({s.outPos}) → <b>{s.inName}</b> ({s.inPos})
              {s.reason ? ` — ${s.reason}` : ""}
            </div>
          ))}
        </div>
      )}

      {!live.inPlayOpen && (
        <div className="card p-3 text-sm text-[var(--muted)]">
          Every game this matchday kicks off together — no in-play subs and the armband can't be moved once it's
          under way.
        </div>
      )}

      {live.manualSubs.length > 0 && (
        <div className="card space-y-1 border-[var(--warn)] p-3 text-sm">
          <div className="font-semibold">
            Manual sub{live.manualSubs.length > 1 ? "s" : ""} still worth making
            <span className="ml-1 font-normal text-[var(--muted)]">
              (their team hasn't kicked off · up to {live.maxManualSubs} sub-outs per matchday, a subbed-out player
              scores 0)
            </span>
          </div>
          {live.manualSubs.map((s, i) => (
            <div key={i}>
              <Pill tone="warn">SUB {i + 1}</Pill> out {s.outName} ({s.outPos},{" "}
              {s.outActual != null ? `${fmt(s.outActual, 0)} pts` : `proj ${fmt(s.outXpts, 1)}`}) → in <b>{s.inName}</b> (
              {s.inPos}, proj {fmt(s.inXpts, 1)}) <span className="text-[var(--good)]">+{fmt(s.gain, 1)}</span>
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
              const isCap = r.playerId === cap?.effectivePlayerId;
              const mult = isCap ? 2 : 1;
              return (
                <tr key={r.playerId} style={r.effRole === "auto-out" ? { opacity: 0.5 } : undefined}>
                  <td>
                    <PosBadge position={r.position} />
                  </td>
                  <td>
                    {r.name}
                    {(isCap || r.isCaptain) && <span title={isCap ? "captain (points doubled)" : "captain — no double"}> (C)</span>}
                    {!r.isStarter && r.effRole === "bench" && (
                      <span className="ml-1 text-xs text-[var(--muted)]">bench {r.benchOrder}</span>
                    )}{" "}
                    {r.effRole === "auto-in" && <Pill tone="good">auto-sub in</Pill>}
                    {r.effRole === "auto-out" && <Pill tone="bad">auto-sub out</Pill>}
                    <span className="ml-1 text-xs text-[var(--muted)]">{r.opp ? `${r.home ? "v" : "@"} ${r.opp}` : ""}</span>
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
                    {r.matchState === "finished" ? "–" : `${fmt(r.xpts * mult, 1)}${isCap ? " ×2" : ""}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {rivals && rivals.rows.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--muted)]">Mini-league — {final ? "final" : "live"}</h3>
          <LiveRivalTable rivals={rivals} />
        </div>
      )}
    </Section>
  );
}
