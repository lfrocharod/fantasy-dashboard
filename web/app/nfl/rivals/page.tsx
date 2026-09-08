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
  optimalLineup,
  weekPoints,
  type NflManager,
  type NflPlayer,
} from "../lib";

interface Match {
  week: number;
  home: number;
  away: number;
}

const POS_SORT = ["QB", "RB", "WR", "TE", "K", "DST"];

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}

export default function NflRivalsPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const week = config?.nflWeek ?? 1;
  const byPoints = (config?.nflSeedingRule ?? "H2H_RECORD") === "TOTAL_POINTS_SCORED";
  const slots = useMemo(
    () => config?.nflSlots ?? { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 },
    [config],
  );
  const teams = useMemo(() => groupTeams(players, config?.myTeamId ?? null), [players, config]);
  const schedule = (config?.schedule ?? []) as Match[];

  const myRoster = useMemo(() => {
    const ids = new Set(config?.nflMyRoster ?? []);
    return players.filter((p) => ids.has(p.extId));
  }, [players, config]);
  const myProj = useMemo(() => optimalLineup(myRoster, slots, 0).total, [myRoster, slots]);

  const myMatch = schedule.find(
    (m) => m.week === week && (m.home === config?.myTeamId || m.away === config?.myTeamId),
  );
  const oppId = myMatch ? (myMatch.home === config?.myTeamId ? myMatch.away : myMatch.home) : null;
  const oppTeam = teams.find((t) => t.teamId === oppId);
  const theirLineup = useMemo(
    () => (oppTeam ? optimalLineup(oppTeam.players, slots, 0) : null),
    [oppTeam, slots],
  );

  if (!teams.length) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  const margin = theirLineup ? myProj - theirLineup.total : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Rivals</h1>

      {/* ---- THIS WEEK'S OPPONENT ---- */}
      {theirLineup && oppTeam && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            WEEK {week} — {oppTeam.name}
          </h2>
          <p className="text-sm text-[var(--muted)]">
            Projected <b>{fmt(myProj, 0)}</b> – <b>{fmt(theirLineup.total, 0)}</b>.{" "}
            {byPoints
              ? "This league seeds by total points, so play your highest‑ceiling lineup regardless of this matchup — the W/L doesn't affect seeding."
              : margin >= 4
                ? "You're a clear favourite — play your safe floor."
                : margin <= -4
                  ? "You're the underdog — play ceiling / make a differential move."
                  : "Coin-flip — every start/sit call matters."}
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Player</th>
                  <th>Matchup</th>
                  <th className="num">Proj</th>
                </tr>
              </thead>
              <tbody>
                {theirLineup.starters.map((s, i) => (
                  <tr key={i}>
                    <td className="text-xs text-[var(--muted)]">{s.slot}</td>
                    <td className="font-medium">
                      {s.p ? (
                        <>
                          <Tag pos={s.p.pos} /> {s.p.name}{" "}
                          <span className="text-[var(--muted)]">{s.p.team}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {s.p && (
                        <span
                          className="rounded px-1 text-xs"
                          style={s.p.matchups[0]?.fdr ? { background: FDR_BG[s.p.matchups[0].fdr] } : undefined}
                        >
                          {s.p.matchups[0]?.opp || "—"}
                        </span>
                      )}
                    </td>
                    <td className="num">{s.p ? fmt(weekPoints(s.p, 0)) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ---- ALL ROSTERS ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">EVERY ROSTER</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {teams.map((mg) => (
            <RosterCard key={mg.teamId} mg={mg} />
          ))}
        </div>
      </section>

      <Legend
        items={[
          ["Proj", "projected PPR points this week"],
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Σ ROS", "roster's total projected points for the rest of the season"],
        ]}
      />
    </div>
  );
}

function RosterCard({ mg }: { mg: NflManager }) {
  return (
    <div className={`card p-3 ${mg.isMine ? "ring-1 ring-[var(--accent)]" : ""}`}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-semibold">
          {mg.name} {mg.isMine && <span className="text-xs text-[var(--accent)]">(you)</span>}
        </span>
        <span className="text-sm text-[var(--muted)]">Σ ROS {fmt(mg.rosTotal, 0)}</span>
      </div>
      <div className="table-wrap">
        <table className="dtable text-xs">
          <tbody>
            {POS_SORT.map((pos) => {
              const list = mg.byPos[pos] ?? [];
              return list.map((p, i) => (
                <tr key={p.extId}>
                  {i === 0 && (
                    <td rowSpan={list.length} className="align-top font-bold text-white">
                      <span className="rounded px-1" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
                        {pos}
                      </span>
                    </td>
                  )}
                  <td className="font-medium">
                    {p.name}
                    {p.injury !== "ACTIVE" && (
                      <span className="ml-1 text-[10px] text-[var(--bad)]">{p.injury[0]}</span>
                    )}
                  </td>
                  <td className="text-[var(--muted)]">
                    {p.team}
                    {p.matchups[0]?.opp ? <span className="ml-1 opacity-70">· {p.matchups[0].opp}</span> : null}
                  </td>
                  <td className="num font-semibold">{fmt(p.rosProj, 0)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
