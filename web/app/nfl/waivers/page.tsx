"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  OUT_STATUS,
  POS_COLOR,
  loadNfl,
  optimalLineup,
  weekPoints,
  type NflPlayer,
} from "../lib";

const POS = ["ALL", "QB", "RB", "WR", "TE", "DST", "K"] as const;
type Pos = (typeof POS)[number];

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}

export default function WaiversPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [pos, setPos] = useState<Pos>("ALL");
  const [horizon, setHorizon] = useState<"week" | "ros">("ros");

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const slots = useMemo(
    () => config?.nflSlots ?? { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 },
    [config],
  );
  const myIds = useMemo(() => new Set(config?.nflMyRoster ?? []), [config]);
  const myRoster = useMemo(() => players.filter((p) => myIds.has(p.extId)), [players, myIds]);
  const mineLineup = useMemo(() => optimalLineup(myRoster, slots, 0), [myRoster, slots]);
  // your worst starter per position — the bar a pickup must clear
  const worstStarter = useMemo(() => {
    const w: Record<string, number> = {};
    for (const s of mineLineup.starters) {
      if (!s.p) continue;
      const key = s.slot === "FLEX" ? "FLEX" : s.p.pos;
      const v = horizon === "week" ? weekPoints(s.p, 0) : s.p.rosProj;
      w[key] = Math.min(w[key] ?? Infinity, v);
      w[s.p.pos] = Math.min(w[s.p.pos] ?? Infinity, v);
    }
    return w;
  }, [mineLineup, horizon]);

  const list = useMemo(() => {
    let l = players.filter((p) => p.available && !myIds.has(p.extId) && !OUT_STATUS.has(p.injury));
    if (pos !== "ALL") l = l.filter((p) => p.pos === pos);
    return l
      .map((p) => {
        const val = horizon === "week" ? weekPoints(p, 0) : p.rosProj;
        const bar = worstStarter[p.pos] ?? worstStarter.FLEX ?? 0;
        return { p, val, upgrade: val - bar };
      })
      .sort((a, b) => (horizon === "week" ? b.val - a.val : b.p.vor - a.p.vor) || b.upgrade - a.upgrade)
      .slice(0, 40);
  }, [players, myIds, pos, horizon, worstStarter]);

  if (players.length === 0) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Waivers &amp; free agents</h1>
        <div className="ml-auto flex gap-1 text-xs">
          {(["week", "ros"] as const).map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`rounded px-2 py-1 ${horizon === h ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
            >
              {h === "week" ? "this week" : "rest of season"}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {POS.map((p) => (
          <button
            key={p}
            onClick={() => setPos(p)}
            className={`rounded px-2 py-1 text-xs ${pos === p ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Player</th>
              <th>Wk</th>
              <th className="num">Wk proj</th>
              <th className="num">ROS</th>
              <th className="num hide-sm">VOR</th>
              <th className="num">vs your worst</th>
              <th className="num hide-sm">% rost</th>
            </tr>
          </thead>
          <tbody>
            {list.map(({ p, upgrade }) => (
              <tr key={p.extId}>
                <td className="font-medium">
                  <Tag pos={p.pos} /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                  {p.injury === "QUESTIONABLE" && (
                    <span className="ml-1 text-[10px] text-[var(--warn)]">Q</span>
                  )}
                </td>
                <td>
                  <span
                    className="rounded px-1 text-xs"
                    style={p.matchups[0]?.fdr ? { background: FDR_BG[p.matchups[0].fdr] } : undefined}
                  >
                    {p.matchups[0]?.opp || "—"}
                  </span>
                </td>
                <td className="num">{fmt(weekPoints(p, 0))}</td>
                <td className="num font-semibold">{fmt(p.rosProj, 0)}</td>
                <td className="num hide-sm">{fmt(p.vor, 0)}</td>
                <td
                  className="num font-semibold"
                  style={{ color: upgrade > 0 ? "var(--good)" : "var(--muted)" }}
                >
                  {upgrade > 0 ? "+" : ""}
                  {fmt(upgrade, horizon === "week" ? 1 : 0)}
                </td>
                <td className="num hide-sm">{fmt(p.pctOwned, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend
        items={[
          ["Wk proj / ROS", "projected points this week / rest of season"],
          ["VOR", "value over replacement — points above the last startable player at the position"],
          ["vs your worst", "how much better than your weakest starter at that position (a real upgrade if green)"],
          ["% rost", "rostered across ESPN leagues — a rough 'how contested on waivers' signal"],
          ["hidden", "players marked OUT / IR / SUSP are excluded"],
        ]}
      />
    </div>
  );
}
