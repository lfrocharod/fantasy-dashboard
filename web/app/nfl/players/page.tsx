"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  OUT_STATUS,
  POS_COLOR,
  adjRos,
  loadNfl,
  oppFactor,
  oppTag,
  optimalLineup,
  usageTag,
  weekPoints,
  type NflPlayer,
} from "../lib";

function Usage({ p }: { p: NflPlayer }) {
  if (p.usageGames < 1) return <span className="text-[var(--muted)]">–</span>;
  const tag = usageTag(p);
  const parts: string[] = [];
  if (p.snapPct) parts.push(`${Math.round(p.snapPct * 100)}% snaps`);
  if (p.targetShare) parts.push(`${Math.round(p.targetShare * 100)}% tgt`);
  return (
    <span
      title={`${p.usageStale ? "last season · " : `last ${p.usageGames}g · `}${parts.join(" · ")} · wopr ${p.wopr.toFixed(2)} · ${p.touches.toFixed(0)} touches/g`}
      style={p.usageStale ? { opacity: 0.6 } : undefined}
    >
      {p.snapPct ? `${Math.round(p.snapPct * 100)}%` : p.targetShare ? `${Math.round(p.targetShare * 100)}%t` : "–"}
      {p.snapTrend >= 0.08 && <span className="text-[var(--good)]"> ▲</span>}
      {p.snapTrend <= -0.08 && <span className="text-[var(--bad)]"> ▼</span>}
      {tag === "workhorse" && (
        <span className="ml-1 rounded bg-[var(--good)] px-1 text-[9px] font-bold text-white">W</span>
      )}
      {tag === "rotational" && (
        <span className="ml-1 text-[9px] text-[var(--warn)]">rot</span>
      )}
    </span>
  );
}

const POS = ["ALL", "QB", "RB", "WR", "TE", "DST", "K"] as const;
type Pos = (typeof POS)[number];

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}

export default function NflPlayersPage() {
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
      const v = horizon === "week" ? weekPoints(s.p, 0) : adjRos(s.p);
      w[key] = Math.min(w[key] ?? Infinity, v);
      w[s.p.pos] = Math.min(w[s.p.pos] ?? Infinity, v);
    }
    return w;
  }, [mineLineup, horizon]);

  const freeAgents = useMemo(
    () => players.filter((p) => p.available && !myIds.has(p.extId) && (p.team || p.pos === "DST")),
    [players, myIds],
  );
  const bestAt = useMemo(() => {
    const fn = (position: string, week = false) =>
      freeAgents
        .filter((p) => p.pos === position && !OUT_STATUS.has(p.injury))
        .sort((a, b) => (week ? weekPoints(b, 0) - weekPoints(a, 0) : adjRos(b) - adjRos(a)))[0];
    return fn;
  }, [freeAgents]);

  // roster holes this week — a starter who's out or on bye — and the best
  // available body at that spot right now
  const holes = useMemo(() => {
    const out: { gap: NflPlayer; fill: NflPlayer | undefined; reason: string }[] = [];
    for (const s of mineLineup.starters) {
      if (!s.p) continue;
      const reason = s.p.onBye ? "BYE" : OUT_STATUS.has(s.p.injury) ? s.p.injury : "";
      if (!reason) continue;
      const posKey = s.slot === "FLEX" ? "RB" : s.p.pos;
      out.push({ gap: s.p, reason, fill: bestAt(posKey, true) });
    }
    return out;
  }, [mineLineup, bestAt]);

  // week streamers: best available DST + K by this week's matchup
  const streamers = useMemo(
    () => ({ DST: bestAt("DST", true), K: bestAt("K", true) }),
    [bestAt],
  );

  const list = useMemo(() => {
    let l = freeAgents.filter((p) => !OUT_STATUS.has(p.injury));
    if (pos !== "ALL") l = l.filter((p) => p.pos === pos);
    return l
      .map((p) => {
        const val = horizon === "week" ? weekPoints(p, 0) : adjRos(p);
        const bar = worstStarter[p.pos] ?? worstStarter.FLEX ?? 0;
        return { p, val, upgrade: val - bar };
      })
      // positional value first (VOR) so the list isn't all QBs, nudged by the
      // opportunity factor; then by how much they beat your worst starter
      .sort(
        (a, b) =>
          (horizon === "week"
            ? b.val - a.val
            : b.p.vor * oppFactor(b.p) - a.p.vor * oppFactor(a.p)) || b.upgrade - a.upgrade,
      )
      .slice(0, 40);
  }, [freeAgents, pos, horizon, worstStarter]);

  if (players.length === 0) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Players &amp; free agents</h1>
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
      {(holes.length > 0 || streamers.DST || streamers.K) && (
        <div className="card space-y-2 p-3 text-sm">
          {holes.map(({ gap, fill, reason }) => (
            <div key={gap.extId}>
              <span className="text-[var(--bad)]">●</span> <b>{gap.name}</b> ({gap.pos}, {reason}){" "}
              {fill ? (
                <>
                  → best available:{" "}
                  <b>{fill.name}</b> <span className="text-[var(--muted)]">{fill.team}</span> (
                  {fmt(weekPoints(fill, 0))} proj{fill.matchups[0]?.opp ? `, ${fill.matchups[0].opp}` : ""})
                </>
              ) : (
                <span className="text-[var(--muted)]">→ nothing worthwhile on waivers</span>
              )}
            </div>
          ))}
          {(streamers.DST || streamers.K) && (
            <div className="text-[var(--muted)]">
              <b className="text-[var(--text)]">Streamers:</b>{" "}
              {streamers.DST && (
                <>
                  DST <b>{streamers.DST.name}</b> ({fmt(weekPoints(streamers.DST, 0))}
                  {streamers.DST.matchups[0]?.opp ? `, ${streamers.DST.matchups[0].opp}` : ""})
                </>
              )}
              {streamers.DST && streamers.K ? " · " : ""}
              {streamers.K && (
                <>
                  K <b>{streamers.K.name}</b> ({fmt(weekPoints(streamers.K, 0))}
                  {streamers.K.matchups[0]?.opp ? `, ${streamers.K.matchups[0].opp}` : ""})
                </>
              )}
            </div>
          )}
        </div>
      )}

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
              <th className="num hide-sm">Usage</th>
              <th className="num">Wk proj</th>
              <th className="num hide-sm" title="expected fantasy points per game from the ffopportunity opportunity model (last ~4 games)">
                xFP/g
              </th>
              <th className="num hide-sm" title="expected total touchdowns per game (ffopportunity)">
                xTD
              </th>
              <th className="num hide-sm" title="fantasy points per game over (+) or under (−) what their opportunity expects — persistent + = TD-luck regression risk, − = buy-low">
                +/− exp
              </th>
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
                  {oppTag(p) && (
                    <span
                      className="ml-1 text-[10px] font-semibold"
                      style={{ color: oppTag(p) === "buy-low" ? "var(--good)" : "var(--warn)" }}
                    >
                      {oppTag(p)}
                    </span>
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
                <td className="num hide-sm text-xs">
                  <Usage p={p} />
                </td>
                <td className="num">{fmt(weekPoints(p, 0))}</td>
                <td className="num hide-sm">{p.expGames ? fmt(p.xfpG, 1) : "–"}</td>
                <td className="num hide-sm">{p.expGames ? fmt(p.xtdG, 2) : "–"}</td>
                <td
                  className="num hide-sm"
                  style={{
                    color: !p.expGames
                      ? undefined
                      : p.fpOE >= 2
                        ? "var(--bad)"
                        : p.fpOE <= -2
                          ? "var(--good)"
                          : "var(--muted)",
                  }}
                >
                  {p.expGames ? `${p.fpOE >= 0 ? "+" : ""}${fmt(p.fpOE, 1)}` : "–"}
                </td>
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
          ["Usage", "recent snap share (or target share) — ▲/▼ = rising/falling snaps, W = workhorse, rot = rotational. From nflverse; blank until the season has games played"],
          ["xFP/g · xTD", "expected fantasy points and expected touchdowns per game from the ffopportunity opportunity model (last ~4 games) — what the volume/quality of touches is worth, before finishing luck"],
          ["+/− exp", "points per game over (red) or under (green) that expectation — a persistent gap flags TD-luck regression (fade) or a buy-low"],
          ["VOR", "value over replacement — points above the last startable player at the position"],
          ["vs your worst", "how much better than your weakest starter at that position, on opportunity-adjusted ROS (docks TD/finishing-luck overperformers, credits the unlucky) — a real upgrade if green"],
          ["buy-low / sell-high", "scoring well under / over what their touches & targets expect — the ROS number and ranking already fold this in"],
          ["% rost", "rostered across ESPN leagues — a rough 'how contested on waivers' signal"],
          ["hidden", "players marked OUT / IR / SUSP are excluded"],
        ]}
      />
    </div>
  );
}
