"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  POS_COLOR,
  groupTeams,
  loadNfl,
  simPlayoffs,
  type NflPlayer,
  type SchedRow,
  type Standing,
} from "../lib";

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}

export default function PlannerPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const week = config?.nflWeek ?? 1;
  const regWeeks = 15;
  const playoffWeeks = useMemo(
    () => (config?.nflPlayoffWeeks?.length ? config.nflPlayoffWeeks : [16, 17]) as number[],
    [config],
  );
  const myIds = useMemo(() => new Set(config?.nflMyRoster ?? []), [config]);
  const roster = useMemo(
    () => players.filter((p) => myIds.has(p.extId)).sort((a, b) => b.rosProj - a.rosProj),
    [players, myIds],
  );

  const odds = useMemo(() => {
    const managers = groupTeams(players, config?.myTeamId ?? null);
    const standings = (config?.standings ?? []) as Standing[];
    const schedule = (config?.schedule ?? []) as SchedRow[];
    const slots = config?.nflSlots ?? { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 };
    if (!managers.length || !schedule.length) return [];
    return simPlayoffs(
      managers, standings, schedule, slots, week, regWeeks, 4, config?.myTeamId ?? null,
    );
  }, [players, config, week]);

  // upcoming weeks we have matchup data for
  const weeks = useMemo(() => {
    const s = new Set<number>();
    for (const p of roster) for (const m of p.matchups) if (m.week >= week) s.add(m.week);
    return [...s].sort((a, b) => a - b).slice(0, 6);
  }, [roster, week]);

  // bye gaps: for each upcoming week, which starters are off
  const byes = useMemo(() => {
    const out: { week: number; players: NflPlayer[] }[] = [];
    for (let w = week; w <= week + 8 && w <= regWeeks; w++) {
      const off = roster.filter((p) => p.bye === w && ["QB", "RB", "WR", "TE", "K", "DST"].includes(p.pos));
      if (off.length) out.push({ week: w, players: off });
    }
    return out;
  }, [roster, week]);

  // playoff SOS: average matchup difficulty for weeks 16-17 (from ROS matchups
  // we may not have; fall back to the last few weeks we do have)
  const playoffSos = useMemo(() => {
    return roster
      .map((p) => {
        const pw = p.matchups.filter((m) => playoffWeeks.includes(m.week) && m.fdr);
        const src = pw.length ? pw : p.matchups.filter((m) => m.fdr);
        const avg = src.length ? src.reduce((a, m) => a + m.fdr, 0) / src.length : 3;
        return { p, avg };
      })
      .sort((a, b) => a.avg - b.avg);
  }, [roster, playoffWeeks]);

  if (roster.length === 0) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Bye weeks &amp; playoff schedule</h1>

      {/* ---- PLAYOFF ODDS ---- */}
      {odds.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            PLAYOFF ODDS — 3,000 sims of the rest of the regular season
          </h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Team</th>
                  <th className="num">Proj. wins</th>
                  <th className="num">Playoffs</th>
                  <th className="num hide-sm">Top-2 seed</th>
                </tr>
              </thead>
              <tbody>
                {odds.map((o) => (
                  <tr key={o.teamId} style={o.isMine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                    <td className="font-medium">{o.name}</td>
                    <td className="num">{fmt(o.projWins, 1)}</td>
                    <td
                      className="num font-semibold"
                      style={{
                        color: o.playoffPct >= 60 ? "var(--good)" : o.playoffPct <= 25 ? "var(--bad)" : undefined,
                      }}
                    >
                      {fmt(o.playoffPct, 0)}%
                    </td>
                    <td className="num hide-sm">{fmt(o.byePct, 0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--muted)]">
            Each remaining matchup is simulated as two Normal(projected score, 24) draws; seeding
            uses wins then points-for (your league&apos;s tiebreak). Use it to decide whether to play
            for this week or the long game.
          </p>
        </section>
      )}

      {/* ---- FIXTURE GRID ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">MATCHUP GRID — your roster</h2>
        <div className="card table-wrap">
          <table className="dtable text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 bg-[var(--surface)]">Player</th>
                {weeks.map((w) => (
                  <th key={w} className="num">
                    W{w}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {roster.map((p) => (
                <tr key={p.extId}>
                  <td className="sticky left-0 whitespace-nowrap bg-[var(--surface)] font-medium">
                    <Tag pos={p.pos} /> {p.name}
                  </td>
                  {weeks.map((w) => {
                    const m = p.matchups.find((x) => x.week === w);
                    const bye = p.bye === w;
                    return (
                      <td
                        key={w}
                        className="num"
                        style={{ background: bye ? "rgba(148,163,184,0.25)" : m?.fdr ? FDR_BG[m.fdr] : undefined }}
                      >
                        {bye ? "BYE" : m?.opp || "–"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- BYE GAPS ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">BYE-WEEK GAPS</h2>
        {byes.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">No roster players on bye in the next 8 weeks.</p>
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">Week</th>
                  <th>Off (fill these slots)</th>
                </tr>
              </thead>
              <tbody>
                {byes.map((b) => (
                  <tr key={b.week}>
                    <td className="num font-semibold">{b.week}</td>
                    <td>
                      {b.players.map((p) => (
                        <span key={p.extId} className="mr-2">
                          <Tag pos={p.pos} /> {p.name}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ---- PLAYOFF SOS ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">
          PLAYOFF SCHEDULE (weeks {playoffWeeks.join("–")}) — easiest run first
        </h2>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th className="num">Avg difficulty</th>
                <th>Playoff opponents</th>
              </tr>
            </thead>
            <tbody>
              {playoffSos.map(({ p, avg }) => {
                const pw = p.matchups.filter((m) => playoffWeeks.includes(m.week));
                return (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      <Tag pos={p.pos} /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td
                      className="num font-semibold"
                      style={{ color: avg <= 2.5 ? "var(--good)" : avg >= 3.6 ? "var(--bad)" : undefined }}
                    >
                      {fmt(avg, 1)}
                    </td>
                    <td className="text-xs">
                      {pw.length
                        ? pw.map((m) => `W${m.week} ${m.opp}`).join(", ")
                        : "schedule not out yet — shown from recent form"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          If the Week {playoffWeeks[0]}–{playoffWeeks.at(-1)} schedule isn&apos;t published yet, the
          difficulty is estimated from each player&apos;s nearer-term matchups — treat it as
          directional. Target trade acquisitions with a green playoff run.
        </p>
      </section>

      <Legend
        items={[
          ["Cell colour", "matchup difficulty 1 (green) … 5 (red); grey = bye"],
          ["Bye gaps", "weeks you'll be short a starter — line up a streamer or bench stash"],
          ["Playoff avg", "mean matchup difficulty across your fantasy playoff weeks"],
        ]}
      />
    </div>
  );
}
