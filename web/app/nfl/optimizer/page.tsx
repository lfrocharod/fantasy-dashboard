"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend, Range } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  POS_COLOR,
  groupTeams,
  lineupMode,
  loadNfl,
  modeScore,
  optimalLineup,
  startSitCall,
  usageTag,
  weekPoints,
  weekRange,
  winProbFromMargin,
  type LineupMode,
  type NflPlayer,
} from "../lib";

interface SchedRow {
  week: number;
  home: number;
  away: number;
}

const MODE_COPY: Record<LineupMode, { label: string; tone: string; why: string }> = {
  ceiling: {
    label: "CEILING",
    tone: "var(--accent)",
    why: "you need variance — start the higher-upside options, not the safe floor",
  },
  floor: {
    label: "FLOOR",
    tone: "var(--good)",
    why: "you're a solid favourite — start the safe floor and don't hand back the edge",
  },
  mean: {
    label: "BALANCED",
    tone: "var(--muted)",
    why: "close matchup — start your best straight projection",
  },
};

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}
function InjTag({ s }: { s: string }) {
  if (s === "ACTIVE") return null;
  const short = { QUESTIONABLE: "Q", DOUBTFUL: "D", OUT: "O", IR: "IR", SUSPENSION: "SUS" }[s] ?? s[0];
  return <span className="ml-1 text-[10px] font-semibold text-[var(--bad)]">{short}</span>;
}
function Opp({ opp, fdr }: { opp: string; fdr: number }) {
  return (
    <span className="rounded px-1 text-xs" style={fdr ? { background: FDR_BG[fdr] } : undefined} title={fdr ? `matchup ${fdr}/5` : ""}>
      {opp || "—"}
    </span>
  );
}

export default function NflOptimizerPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const week = config?.nflWeek ?? 1;
  const slots = useMemo(
    () => config?.nflSlots ?? { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 },
    [config],
  );
  const myRoster = useMemo(() => {
    const ids = new Set(config?.nflMyRoster ?? []);
    return players.filter((p) => ids.has(p.extId));
  }, [players, config]);

  // this week's opponent → projected margin → win% → which lineup to field
  const teams = useMemo(() => groupTeams(players, config?.myTeamId ?? null), [players, config]);
  const seedByPoints = (config?.nflSeedingRule ?? "H2H_RECORD") === "TOTAL_POINTS_SCORED";
  const { mode, winPct } = useMemo(() => {
    const sched = (config?.schedule ?? []) as SchedRow[];
    const g = sched.find(
      (m) => m.week === week && (m.home === config?.myTeamId || m.away === config?.myTeamId),
    );
    const oppId = g ? (g.home === config?.myTeamId ? g.away : g.home) : null;
    const oppTeam = teams.find((t) => t.teamId === oppId);
    const meanMine = optimalLineup(myRoster, slots, 0).total;
    const meanOpp = oppTeam ? optimalLineup(oppTeam.players, slots, 0).total : null;
    const wp = meanOpp != null ? winProbFromMargin(meanMine - meanOpp) : 50;
    return { mode: lineupMode(wp, seedByPoints), winPct: wp };
  }, [config, week, teams, myRoster, slots, seedByPoints]);

  const mine = useMemo(
    () => optimalLineup(myRoster, slots, 0, modeScore(mode)),
    [myRoster, slots, mode],
  );
  const starterIds = useMemo(
    () => new Set(mine.starters.map((s) => s.p?.extId).filter(Boolean) as string[]),
    [mine],
  );

  if (myRoster.length === 0) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  const optIds = new Set(mine.starters.map((s) => s.p?.extId).filter(Boolean) as string[]);
  const toStart = mine.starters
    .filter((s) => s.p && (s.p.slot === "BE" || s.p.slot === "IR" || !s.p.slot))
    .map((s) => s.p!);
  const toBench = myRoster.filter(
    (p) => !optIds.has(p.extId) && p.slot && p.slot !== "BE" && p.slot !== "IR",
  );

  // honest mean + range of the chosen lineup (mine.total is the mode-weighted
  // score used only for ordering)
  const starters = mine.starters.map((s) => s.p).filter(Boolean) as NflPlayer[];
  const meanTotal = starters.reduce((a, p) => a + weekPoints(p, 0), 0);
  const loTotal = starters.reduce((a, p) => a + weekRange(p, 0).lo, 0);
  const hiTotal = starters.reduce((a, p) => a + weekRange(p, 0).hi, 0);
  const mc = MODE_COPY[mode];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Optimizer — week {week}</h1>
        <span className="text-sm text-[var(--muted)]">
          projects <b>{fmt(meanTotal, 0)}</b>{" "}
          <span className="text-xs">
            ({fmt(loTotal, 0)}–{fmt(hiTotal, 0)})
          </span>
        </span>
      </div>

      <div className="card p-3 text-sm" style={{ borderLeft: `3px solid ${mc.tone}` }}>
        <b style={{ color: mc.tone }}>{mc.label} LINEUP</b>{" "}
        <span className="text-[var(--muted)]">
          — {seedByPoints ? "league seeds on total points, so always chase upside" : `${winPct}% to win this week`}: {mc.why}.
        </span>
      </div>

      {toStart.length > 0 || toBench.length > 0 ? (
        <div className="card p-3 text-sm">
          <b className="text-[var(--warn)]">Lineup changes to make in ESPN:</b>
          <ul className="mt-1 space-y-0.5">
            {toStart.map((p) => (
              <li key={p.extId}>
                ▲ Start <b>{p.name}</b> ({p.pos}, {fmt(weekPoints(p, 0))} proj)
              </li>
            ))}
            {toBench.map((p) => (
              <li key={p.extId} className="text-[var(--muted)]">
                ▼ Bench {p.name} ({p.slot}, {fmt(weekPoints(p, 0))} proj)
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="card p-3 text-sm text-[var(--good)]">
          Your ESPN lineup already matches the optimal one.
        </p>
      )}

      {/* ---- OPTIMAL LINEUP ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">OPTIMAL LINEUP</h2>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Slot</th>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num">Proj</th>
                <th className="num hide-sm">Range</th>
              </tr>
            </thead>
            <tbody>
              {mine.starters.map((s, i) => (
                <tr key={i}>
                  <td className="text-xs text-[var(--muted)]">{s.slot}</td>
                  <td className="font-medium">
                    {s.p ? (
                      <>
                        <Tag pos={s.p.pos} /> {s.p.name}{" "}
                        <span className="text-[var(--muted)]">{s.p.team}</span>
                        <InjTag s={s.p.injury} />
                      </>
                    ) : (
                      <span className="text-[var(--bad)]">— empty —</span>
                    )}
                  </td>
                  <td>{s.p && <Opp opp={s.p.matchups[0]?.opp ?? ""} fdr={s.p.matchups[0]?.fdr ?? 0} />}</td>
                  <td className="num font-semibold">{s.p ? fmt(weekPoints(s.p, 0)) : "–"}</td>
                  <td className="num hide-sm">
                    {s.p ? (
                      <Range
                        lo={weekRange(s.p, 0).lo}
                        mean={weekPoints(s.p, 0)}
                        hi={weekRange(s.p, 0).hi}
                      />
                    ) : (
                      "–"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- START / SIT ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">START / SIT — every rostered player</h2>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num hide-sm">Usage</th>
                <th className="num">Wk proj</th>
                <th className="num hide-sm">Range</th>
                <th className="num hide-sm">ROS</th>
                <th>Call</th>
              </tr>
            </thead>
            <tbody>
              {[...myRoster]
                .sort((a, b) => weekPoints(b, 0) - weekPoints(a, 0))
                .map((p) => {
                  const call = startSitCall(p, starterIds);
                  return (
                    <tr key={p.extId}>
                      <td className="font-medium">
                        <Tag pos={p.pos} /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                        <InjTag s={p.injury} />
                        {p.onBye && <span className="ml-1 text-[10px] text-[var(--warn)]">BYE</span>}
                      </td>
                      <td>
                        <Opp opp={p.matchups[0]?.opp ?? ""} fdr={p.matchups[0]?.fdr ?? 0} />
                      </td>
                      <td className="num hide-sm text-xs">
                        {p.usageGames >= 1 ? (
                          <span
                            title={`last ${p.usageGames}g · ${Math.round(p.snapPct * 100)}% snaps · wopr ${p.wopr.toFixed(2)}`}
                            style={{
                              color:
                                usageTag(p) === "workhorse"
                                  ? "var(--good)"
                                  : usageTag(p) === "rotational"
                                    ? "var(--warn)"
                                    : undefined,
                            }}
                          >
                            {p.snapPct ? `${Math.round(p.snapPct * 100)}%` : "–"}
                            {p.snapTrend >= 0.08 ? " ▲" : p.snapTrend <= -0.08 ? " ▼" : ""}
                          </span>
                        ) : (
                          <span className="text-[var(--muted)]">–</span>
                        )}
                      </td>
                      <td className="num font-semibold">{fmt(weekPoints(p, 0))}</td>
                      <td className="num hide-sm">
                        <Range lo={weekRange(p, 0).lo} hi={weekRange(p, 0).hi} />
                      </td>
                      <td className="num hide-sm">{fmt(p.rosProj, 0)}</td>
                      <td
                        className="text-xs font-semibold"
                        style={{
                          color:
                            call === "START"
                              ? "var(--good)"
                              : call === "FLEX?"
                                ? "var(--warn)"
                                : "var(--muted)",
                        }}
                      >
                        {call}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      <Legend
        items={[
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Proj / ROS", "projected PPR points this week / rest of season"],
          ["Range", "~15th–85th percentile week (floor–ceiling): wider for boom/bust spots (WR/TE/DST, committee backs), tighter for a locked-in workhorse"],
          ["FLOOR / CEILING / BALANCED lineup", "which side of the range to optimise: chase ceiling as an underdog or in a points-seeded league, protect the floor as a favourite"],
          ["Call", "START = in your optimal XI · FLEX? = viable flex swing · SIT = leave it"],
        ]}
      />
    </div>
  );
}
