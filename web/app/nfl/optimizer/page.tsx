"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  POS_COLOR,
  loadNfl,
  optimalLineup,
  startSitCall,
  usageTag,
  weekPoints,
  type NflPlayer,
} from "../lib";

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

  const mine = useMemo(() => optimalLineup(myRoster, slots, 0), [myRoster, slots]);
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Optimizer — week {week}</h1>
        <span className="text-sm text-[var(--muted)]">
          optimal lineup projects <b>{fmt(mine.total, 0)}</b>
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
          ["Call", "START = in your optimal XI · FLEX? = viable flex swing · SIT = leave it"],
        ]}
      />
    </div>
  );
}
