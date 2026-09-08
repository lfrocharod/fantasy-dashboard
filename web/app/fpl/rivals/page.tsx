"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  bestXI,
  groupByManager,
  loadBoard,
  predictClaims,
  type FplPlayer,
  type Manager,
} from "../lib";

const POS_ORDER = ["GKP", "DEF", "MID", "FWD"];
const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};

export default function FplRivalsPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [picks, setPicks] = useState<
    { playerExtId: string; teamId: number; teamName: string; isMine: boolean }[]
  >([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [metric, setMetric] = useState<"medium" | "season">("season");

  useEffect(() => {
    loadBoard().then((d) => {
      setPlayers(d.players);
      setPicks(d.picks);
      setConfig(d.config);
    });
  }, []);

  const fallbackNames = useMemo(
    () =>
      Object.fromEntries(
        ((config?.standings ?? []) as { name: string; entry_id: number | null }[]).map((s) => [
          String(s.entry_id),
          s.name,
        ]),
      ),
    [config],
  );
  const managers = useMemo(
    () => groupByManager(players, picks, config?.entryId ?? null, fallbackNames),
    [players, picks, config, fallbackNames],
  );

  const me = managers.find((m) => m.isMine);
  const mineIds = useMemo(() => new Set(me?.players.map((p) => p.extId) ?? []), [me]);

  // effective ownership: how many of the N managers hold each player
  const effOwn = useMemo(() => {
    if (managers.length < 2) return [];
    const own = new Map<string, { p: FplPlayer; n: number; mine: boolean }>();
    for (const mg of managers)
      for (const p of mg.players) {
        const e = own.get(p.extId) ?? { p, n: 0, mine: mineIds.has(p.extId) };
        e.n += 1;
        own.set(p.extId, e);
      }
    return [...own.values()]
      .map((e) => ({ ...e, pct: Math.round((100 * e.n) / managers.length) }))
      .sort((a, b) => b.p.ros - a.p.ros)
      .slice(0, 30);
  }, [managers, mineIds]);

  // per-rival: projected next GW + their differentials vs you
  const rivalRows = useMemo(() => {
    if (!me) return [];
    return managers
      .filter((m) => !m.isMine)
      .map((m) => {
        const proj = bestXI(m.players, (p) => p.gws[0]?.xpts ?? p.proj).xi.reduce(
          (a, p) => a + (p.gws[0]?.xpts ?? p.proj),
          0,
        );
        const diffs = m.players
          .filter((p) => !mineIds.has(p.extId))
          .sort((a, b) => b.ros - a.ros)
          .slice(0, 4);
        return { m, proj, diffs };
      })
      .sort((a, b) => b.proj - a.proj);
  }, [managers, me, mineIds]);

  const myProj = useMemo(
    () =>
      me
        ? bestXI(me.players, (p) => p.gws[0]?.xpts ?? p.proj).xi.reduce(
            (a, p) => a + (p.gws[0]?.xpts ?? p.proj),
            0,
          )
        : 0,
    [me],
  );

  if (!managers.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        No roster data yet — run <code>./draft.sh --sport fpl --sync</code>.
      </p>
    );
  }

  const v = (p: FplPlayer) => (metric === "medium" ? p.horizon : p.ros);
  const claims = predictClaims(managers, players, config?.entryId ?? null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Rivals</h1>
        <span className="text-sm text-[var(--muted)]">
          Your projected next GW: <strong>{fmt(myProj, 0)}</strong>
        </span>
        <div className="ml-auto flex gap-1 text-xs">
          {(["medium", "season"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`rounded px-2 py-1 ${metric === m ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
            >
              {m === "medium" ? "next 6 GW" : "rest of season"}
            </button>
          ))}
        </div>
      </div>

      {/* ---- PROJECTED THIS GW ---- */}
      {rivalRows.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">RIVALS — projected next GW</h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Manager</th>
                  <th className="num">Proj GW</th>
                  <th className="num">vs you</th>
                  <th className="hide-sm">Their edge (they have, you don&apos;t)</th>
                </tr>
              </thead>
              <tbody>
                {rivalRows.map(({ m, proj, diffs }) => (
                  <tr key={m.entryId}>
                    <td className="font-medium">{m.name}</td>
                    <td className="num font-semibold">{fmt(proj, 0)}</td>
                    <td
                      className="num font-semibold"
                      style={{ color: proj > myProj ? "var(--bad)" : "var(--good)" }}
                    >
                      {proj > myProj ? "+" : ""}
                      {fmt(proj - myProj, 0)}
                    </td>
                    <td className="hide-sm text-xs text-[var(--muted)]">
                      {diffs.map((p) => `${p.name} (${fmt(v(p), 0)})`).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ---- LIKELY RIVAL CLAIMS ---- */}
      {claims.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            LIKELY RIVAL WAIVER CLAIMS — get there first
          </h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Rival</th>
                  <th>Weak spot</th>
                  <th>Likely target</th>
                  <th className="num">Their gain</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((c, i) => (
                  <tr key={i}>
                    <td>{c.rivalName}</td>
                    <td className="text-[var(--muted)]">
                      {c.weakPos} · {c.weakStarter}
                    </td>
                    <td className="font-medium">
                      {c.target.name} <span className="text-[var(--muted)]">{c.target.team}</span>
                    </td>
                    <td className="num font-semibold">+{fmt(c.gain, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ---- EFFECTIVE OWNERSHIP ---- */}
      {effOwn.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            EFFECTIVE OWNERSHIP — in your league only
          </h2>
          <p className="text-sm text-[var(--muted)]">
            What matters is how many of the {managers.length} managers you&apos;re racing own each
            player. Low % + high ROS = a real advantage if you can get them; high % = neutral.
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Team</th>
                  <th className="num">Owned</th>
                  <th className="num">ROS</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {effOwn.map((e) => (
                  <tr
                    key={e.p.extId}
                    style={e.mine ? { background: "rgba(31,111,235,0.08)" } : undefined}
                  >
                    <td className="font-medium">{e.p.name}</td>
                    <td className="text-[var(--muted)]">{e.p.team}</td>
                    <td
                      className="num font-semibold"
                      style={{
                        color: e.pct >= 60 ? "var(--muted)" : e.pct <= 34 ? "var(--good)" : undefined,
                      }}
                    >
                      {e.pct}%
                    </td>
                    <td className="num">{fmt(e.p.ros, 0)}</td>
                    <td className="text-xs">
                      {e.mine ? (
                        <span className="text-[var(--accent)]">you</span>
                      ) : e.p.available ? (
                        <span className="text-[var(--good)]">free agent</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ---- ROSTERS ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">MANAGER ROSTERS</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {managers.map((mg) => (
            <ManagerCard key={mg.entryId} mg={mg} metric={metric} v={v} />
          ))}
        </div>
      </section>

      <Legend
        items={[
          ["Proj GW", "their best legal XI's projected points next gameweek"],
          ["vs you", "their projection minus yours — red means they out-project you"],
          ["Their edge", "players they own that you don't — where they can gain on you"],
          ["Owned", "share of your league that holds this player"],
          ["value", `projected draft points — ${metric === "medium" ? "next 6 GW" : "rest of season"}`],
          ["⚑", "one booking from a suspension"],
        ]}
      />
    </div>
  );
}

function ManagerCard({
  mg,
  metric,
  v,
}: {
  mg: Manager;
  metric: "medium" | "season";
  v: (p: FplPlayer) => number;
}) {
  const total = metric === "medium" ? mg.total.medium : mg.total.season;
  return (
    <div className={`card p-3 ${mg.isMine ? "ring-1 ring-[var(--accent)]" : ""}`}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-semibold">
          {mg.name} {mg.isMine && <span className="text-xs text-[var(--accent)]">(you)</span>}
        </span>
        <span className="text-sm text-[var(--muted)]">Σ {fmt(total, 0)}</span>
      </div>
      <div className="table-wrap">
        <table className="dtable text-xs">
          <tbody>
            {POS_ORDER.map((pos) => {
              const list = mg.byPos[pos] ?? [];
              return list.map((p, i) => (
                <tr key={p.extId}>
                  {i === 0 && (
                    <td rowSpan={list.length} className="align-top font-bold text-white">
                      <span className="rounded px-1" style={{ background: POS_COLOR[pos] }}>
                        {pos}
                      </span>
                    </td>
                  )}
                  <td className="font-medium">
                    {p.name}
                    {p.suspRisk && (
                      <span className="ml-1 text-[var(--warn)]" title={`${p.ycToBan} booking from a ban`}>
                        ⚑
                      </span>
                    )}
                    {p.unavailable && (
                      <span className="ml-1 text-[10px] text-[var(--bad)]">
                        {p.status === "s" ? "susp" : p.status === "i" ? "inj" : "doubt"}
                      </span>
                    )}
                  </td>
                  <td className="text-[var(--muted)]">
                    {p.team}
                    {p.nextOpp ? <span className="ml-1 opacity-70">· {p.nextOpp}</span> : null}
                  </td>
                  <td className="num font-semibold">{fmt(v(p), 0)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
