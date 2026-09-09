"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import { bestXI, groupByManager, loadBoard, type FplPlayer, type Manager } from "../lib";

interface Standing {
  name: string;
  entry_id: number | null;
  rank: number;
  total: number;
  points_for: number | null;
  w: number | null;
  d: number | null;
  l: number | null;
}
interface Match {
  event: number;
  home: string;
  away: string;
  home_entry: number | null;
  away_entry: number | null;
  finished: boolean;
}

function projGw(mg: Manager | undefined, gwIdx: number): number {
  if (!mg) return 0;
  const { xi } = bestXI(mg.players, (p) => p.gws[gwIdx]?.xpts ?? 0);
  return xi.reduce((a, p) => a + (p.gws[gwIdx]?.xpts ?? 0), 0);
}

function gauss(mean: number, sd: number): number {
  const u = 1 - Math.random();
  const v = Math.random();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

interface FinishOdds {
  firstPct: number;
  topHalfPct: number;
  meanRank: number;
}

/**
 * Monte-Carlo the rest of a total-points season: each team's remaining GWs are
 * drawn from their best-XI per-GW rate (ROS ÷ GWs left) with a ~32% spread —
 * a draft XI is far less boom/bust than one player. Turns the deterministic
 * "projected #3, 2 back" into real odds.
 */
function simulateSeason(
  entries: { id: string; now: number; ros: number }[],
  gwsLeft: number,
  iters = 4000,
): Map<string, FinishOdds> | null {
  if (gwsLeft < 1 || entries.length < 2 || entries.every((e) => e.ros <= 0)) return null;
  const half = Math.ceil(entries.length / 2);
  const first = new Map(entries.map((e) => [e.id, 0]));
  const topHalf = new Map(entries.map((e) => [e.id, 0]));
  const rankSum = new Map(entries.map((e) => [e.id, 0]));
  for (let it = 0; it < iters; it++) {
    const finals = entries
      .map((e) => {
        const perGw = e.ros / gwsLeft;
        let t = e.now;
        for (let g = 0; g < gwsLeft; g++) t += Math.max(0, gauss(perGw, 0.32 * perGw + 4));
        return { id: e.id, t };
      })
      .sort((a, b) => b.t - a.t);
    finals.forEach((f, idx) => {
      rankSum.set(f.id, (rankSum.get(f.id) ?? 0) + idx + 1);
      if (idx === 0) first.set(f.id, (first.get(f.id) ?? 0) + 1);
      if (idx < half) topHalf.set(f.id, (topHalf.get(f.id) ?? 0) + 1);
    });
  }
  return new Map(
    entries.map((e) => [
      e.id,
      {
        firstPct: (100 * (first.get(e.id) ?? 0)) / iters,
        topHalfPct: (100 * (topHalf.get(e.id) ?? 0)) / iters,
        meanRank: (rankSum.get(e.id) ?? 0) / iters,
      },
    ]),
  );
}

export default function StandingsPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [picks, setPicks] = useState<
    { playerExtId: string; teamId: number; teamName: string; isMine: boolean }[]
  >([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);


  useEffect(() => {
    loadBoard().then((d) => {
      setPlayers(d.players);
      setPicks(d.picks);
      setConfig(d.config);
    });
  }, []);

  const standings = useMemo(() => (config?.standings ?? []) as Standing[], [config]);
  const schedule = useMemo(() => (config?.schedule ?? []) as Match[], [config]);
  const fallbackNames = useMemo(
    () => Object.fromEntries(standings.map((s) => [String(s.entry_id), s.name])),
    [standings],
  );
  const managers = useMemo(
    () => groupByManager(players, picks, config?.entryId ?? null, fallbackNames),
    [players, picks, config, fallbackNames],
  );
  const byEntry = useMemo(() => new Map(managers.map((m) => [m.entryId, m])), [managers]);
  const isH2H = config?.fplMode === "h";
  const nextGw = players[0]?.gws[0]?.gw ?? 0;
  const gwsLeft = Math.max(1, 39 - (nextGw || 1));

  // current table stays in official rank order; project a final table alongside
  const rows = useMemo(() => {
    const withProj = standings.map((s) => {
      const mg = byEntry.get(String(s.entry_id));
      const ros = mg?.total.season ?? 0;
      return { ...s, ros, finalPts: s.total + ros };
    });
    const projOrder = [...withProj].sort((a, b) => b.finalPts - a.finalPts);
    const projRank = new Map(projOrder.map((r, i) => [r.entry_id, i + 1]));
    const leaderFinal = projOrder[0]?.finalPts ?? 0;
    return withProj
      .sort((a, b) => a.rank - b.rank)
      .map((r) => ({ ...r, projRank: projRank.get(r.entry_id) ?? r.rank, gap: leaderFinal - r.finalPts }));
  }, [standings, byEntry]);

  const odds = useMemo(
    () =>
      isH2H
        ? null
        : simulateSeason(
            rows.map((r) => ({ id: String(r.entry_id), now: r.total, ros: r.ros })),
            gwsLeft,
          ),
    [rows, gwsLeft, isH2H],
  );

  // "catch the leader" — where you sit, and the single best move to gain ground
  const path = useMemo(() => {
    const meRow = rows.find((r) => String(r.entry_id) === String(config?.entryId));
    if (!meRow) return null;
    const ahead = rows
      .filter((r) => r.finalPts > meRow.finalPts)
      .sort((a, b) => a.finalPts - b.finalPts)[0];
    const leader = rows.reduce((m, r) => (r.finalPts > m.finalPts ? r : m), rows[0]);
    const myMg = byEntry.get(String(config?.entryId));
    const myWorstStarter = myMg
      ? Math.min(...(bestXI(myMg.players).xi.map((p) => p.ros)))
      : 0;
    const mineIds = new Set(myMg?.players.map((p) => p.extId) ?? []);
    const bestFA = players
      .filter((p) => p.available && !mineIds.has(p.extId) && !p.unavailable)
      .sort((a, b) => b.ros - a.ros)[0];
    return {
      meRow,
      toNext: ahead ? Math.round(ahead.finalPts - meRow.finalPts) : 0,
      nextName: ahead?.name,
      toLeader: Math.round(leader.finalPts - meRow.finalPts),
      leaderName: leader.name,
      move: bestFA && bestFA.ros - myWorstStarter > 20 ? { name: bestFA.name, gain: Math.round(bestFA.ros - myWorstStarter) } : null,
    };
  }, [rows, config, byEntry, players]);

  if (!standings.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Run <code>./draft.sh --sport fpl --sync</code> to pull standings.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {path && (
        <div className="card p-3 text-sm">
          <b>Your path.</b> Projected to finish <b>#{path.meRow.projRank}</b>
          {path.nextName && path.toNext > 0 ? (
            <> — <b>{path.toNext}</b> pts behind {path.nextName}</>
          ) : path.meRow.projRank === 1 ? (
            <> — projected champion, hold your ground</>
          ) : null}
          {path.toLeader > 0 && (
            <span className="text-[var(--muted)]"> ({path.toLeader} behind {path.leaderName})</span>
          )}
          {path.move && (
            <div className="mt-1 text-[var(--good)]">
              Biggest single move: claim <b>{path.move.name}</b> (+{path.move.gain} rest-of-season).
            </div>
          )}
        </div>
      )}
      <section className="space-y-2">
        <h1 className="text-xl font-semibold">
          Standings <span className="text-sm font-normal text-[var(--muted)]">· {isH2H ? "head-to-head" : "total points"}</span>
        </h1>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Manager</th>
                <th className="num">{isH2H ? "H2H pts" : "Total"}</th>
                {isH2H && <th className="num hide-sm">W-D-L</th>}
                <th className="num">Squad ROS</th>
                <th className="num">Proj. final</th>
                {odds && <th className="num hide-sm">Win</th>}
                {odds && <th className="num hide-sm">Top½</th>}
                <th className="num hide-sm">Gap</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const mg = byEntry.get(String(s.entry_id));
                const move = s.rank - s.projRank; // + = climbing
                const o = odds?.get(String(s.entry_id));
                return (
                  <tr key={s.rank} style={mg?.isMine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                    <td className="num">{s.rank}</td>
                    <td className="font-medium">{s.name}</td>
                    <td className="num font-semibold">{s.total}</td>
                    {isH2H && (
                      <td className="num hide-sm">
                        {s.w ?? 0}-{s.d ?? 0}-{s.l ?? 0}
                      </td>
                    )}
                    <td className="num">{fmt(s.ros, 0)}</td>
                    <td className="num">
                      {fmt(s.finalPts, 0)}
                      {move !== 0 && (
                        <span
                          className="ml-1 text-[10px]"
                          style={{ color: move > 0 ? "var(--good)" : "var(--bad)" }}
                        >
                          →#{s.projRank}
                        </span>
                      )}
                    </td>
                    {odds && (
                      <td
                        className="num hide-sm"
                        style={{ color: (o?.firstPct ?? 0) >= 20 ? "var(--good)" : undefined }}
                      >
                        {o ? (o.firstPct < 1 ? "<1%" : `${Math.round(o.firstPct)}%`) : "–"}
                      </td>
                    )}
                    {odds && (
                      <td className="num hide-sm">{o ? `${Math.round(o.topHalfPct)}%` : "–"}</td>
                    )}
                    <td className="num hide-sm text-[var(--muted)]">
                      {s.gap <= 0.5 ? "—" : `-${fmt(s.gap, 0)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          Rows are the current table. <b>Proj. final</b> = current points + roster&apos;s projected
          rest-of-season output (best legal XI each GW); the <b>→#N</b> tag is where that projection
          puts them (green = climbing, red = slipping).
          {odds && (
            <>
              {" "}
              <b>Win / Top½</b> are from 4,000 simulations of the {gwsLeft} GW left — each squad&apos;s
              weekly score drawn from its projected rate with a ~32% spread.
            </>
          )}
        </p>
      </section>

      {isH2H && schedule.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">H2H SCHEDULE — projected</h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">GW</th>
                  <th>Home</th>
                  <th className="num">proj</th>
                  <th>Away</th>
                  <th className="num">proj</th>
                  <th>Lean</th>
                </tr>
              </thead>
              <tbody>
                {schedule
                  .filter((m) => !m.finished && m.event >= nextGw)
                  .sort((a, b) => a.event - b.event)
                  .slice(0, 10)
                  .map((m, i) => {
                    const gi = m.event - nextGw;
                    const hp = projGw(byEntry.get(String(m.home_entry)), gi);
                    const ap = projGw(byEntry.get(String(m.away_entry)), gi);
                    const mine =
                      byEntry.get(String(m.home_entry))?.isMine ||
                      byEntry.get(String(m.away_entry))?.isMine;
                    const lean = Math.abs(hp - ap) < 4 ? "toss-up" : hp > ap ? m.home : m.away;
                    return (
                      <tr key={i} style={mine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                        <td className="num">{m.event}</td>
                        <td>{m.home}</td>
                        <td className="num">{fmt(hp, 0)}</td>
                        <td>{m.away}</td>
                        <td className="num">{fmt(ap, 0)}</td>
                        <td className="text-xs text-[var(--muted)]">{lean}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["Total / H2H pts", isH2H ? "league H2H points (win 3 / draw 1)" : "cumulative fantasy points"],
          ["Squad ROS", "roster's total projected points for the rest of the season"],
          ["Proj. final", "current points + squad ROS — a naive end-of-season forecast"],
          ["Gap", "projected points behind the leader"],
        ]}
      />
    </div>
  );
}
