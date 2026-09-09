"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Checklist, Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import { bestXI, squadHorizon, toPlayer, type FplPlayer } from "./lib";
import { FDR_TEXT } from "@/lib/fdr";
import { FplFixtureRun } from "./FplFixtureRun";
import { FplLive } from "./FplLive";
import { FplSetup } from "./Setup";

const POS_ORDER = ["GKP", "DEF", "MID", "FWD"];
const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};
const STATUS_LABEL: Record<string, string> = {
  d: "doubt", i: "injured", s: "susp", u: "unavail", n: "out",
};

interface Check {
  ok: boolean;
  text: string;
}

function buildChecklist(
  xi: FplPlayer[],
  bench: FplPlayer[],
  nextGw: number,
  src: string | null,
): Check[] {
  const c: Check[] = [];
  const live = src === "my-team";
  c.push({
    ok: live,
    text: live
      ? "Showing your live Pick Team XI from FPL"
      : src && src.startsWith("event/")
        ? `Showing your last fielded XI (GW${src.slice(6)}) — add the pl_profile cookie in Settings so we read your live Pick Team`
        : "No lineup pulled yet — showing the model's best XI (run the FPL sync)",
  });
  const notNailed = xi.filter((p) => p.pStart > 0 && p.pStart < 0.7);
  c.push({
    ok: notNailed.length === 0,
    text: notNailed.length
      ? `${notNailed.length} starter(s) not nailed: ${notNailed.map((p) => `${p.name} ${Math.round(p.pStart * 100)}%`).join(", ")}`
      : "Every starter is a nailed-on starter (≥70%)",
  });
  const inj = xi.filter((p) => p.unavailable);
  c.push({
    ok: inj.length === 0,
    text: inj.length
      ? `${inj.length} unavailable in your XI: ${inj.map((p) => p.name).join(", ")}`
      : "No injured / suspended players in your XI",
  });
  const susp = xi.filter((p) => p.suspRisk);
  c.push({
    ok: susp.length === 0,
    text: susp.length
      ? `One booking from a ban: ${susp.map((p) => p.name).join(", ")}`
      : "No suspension risk in your XI this week",
  });
  const weakBench = bench.filter((p) => !p.unavailable && p.proj >= 2).length;
  c.push({
    ok: weakBench >= 2,
    text: weakBench >= 2 ? "Bench has cover if someone doesn't play" : "Thin bench — a non-starter could cost you points",
  });
  c.push({ ok: true, text: `Set your lineup before the GW${nextGw || "?"} deadline` });
  return c;
}

export default function FplOverviewPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch("/api/draft/board?sport=fpl", { cache: "no-store" });
    const d = await r.json();
    setPlayers((d.players ?? []).map(toPlayer));
    setConfig(d.config ?? null);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byId = useMemo(() => new Map(players.map((p) => [p.extId, p])), [players]);
  const mySquad = useMemo(
    () => (config?.mySquad ?? []).map((id) => byId.get(id)).filter(Boolean) as FplPlayer[],
    [config, byId],
  );
  const gwCols = useMemo(() => (players[0]?.gws ?? []).map((g) => g.gw), [players]);
  const nextGw = gwCols[0] ?? 0;

  // Your ACTUAL XI, straight from the FPL app's Pick Team tab (slots 1-11).
  // Fall back to the model's best XI only if we haven't pulled a lineup yet.
  const setXi = useMemo(() => {
    const lu = config?.fplLineup?.picks ?? [];
    if (!lu.length) return null;
    const start = lu.filter((p) => p.starter).map((p) => byId.get(p.extId)).filter(Boolean) as FplPlayer[];
    const bench = lu.filter((p) => !p.starter).map((p) => byId.get(p.extId)).filter(Boolean) as FplPlayer[];
    const src = config?.fplLineup?.source ?? "";
    return start.length >= 11 ? { xi: start, bench, src } : null;
  }, [config, byId]);

  const model = useMemo(() => (mySquad.length >= 11 ? bestXI(mySquad) : null), [mySquad]);
  const xi = useMemo(() => setXi?.xi ?? model?.xi ?? [], [setXi, model]);
  const bench = useMemo(() => setXi?.bench ?? model?.bench ?? [], [setXi, model]);
  const fromApp = !!setXi;
  const formation = xi.length
    ? `${xi.filter((p) => p.pos === "DEF").length}-${xi.filter((p) => p.pos === "MID").length}-${xi.filter((p) => p.pos === "FWD").length}`
    : "";

  // swaps the model would make vs the XI you have set
  const swaps = useMemo(() => {
    if (!setXi || !model) return [];
    const setIds = new Set(setXi.xi.map((p) => p.extId));
    const modelIds = new Set(model.xi.map((p) => p.extId));
    const out = setXi.xi.filter((p) => !modelIds.has(p.extId));
    const inn = model.xi.filter((p) => !setIds.has(p.extId));
    return out
      .map((o) => {
        const i = inn.find((x) => x.pos === o.pos) ?? inn[0];
        return i ? { out: o, in: i, gain: (i.gws[0]?.xpts ?? i.proj) - (o.gws[0]?.xpts ?? o.proj) } : null;
      })
      .filter(Boolean)
      .filter((s) => s!.gain > 0.4) as { out: FplPlayer; in: FplPlayer; gain: number }[];
  }, [setXi, model]);

  const standings = useMemo(
    () =>
      (config?.standings ?? []) as {
        entry_id: number | null;
        rank: number;
        total: number;
      }[],
    [config],
  );
  const myRank = standings.find((s) => String(s.entry_id) === String(config?.entryId))?.rank;
  const nextGwProj = xi.reduce((a, p) => a + (p.gws[0]?.xpts ?? p.proj), 0);
  const rosPerGw = mySquad.length
    ? squadHorizon(mySquad, gwCols.map((_g, i) => i)) / Math.max(1, gwCols.length)
    : 0;

  const startSet = useMemo(() => new Set(xi.map((p) => p.extId)), [xi]);
  const ordered = useMemo(
    () => POS_ORDER.flatMap((pos) => mySquad.filter((p) => p.pos === pos).sort((a, b) => {
      const sa = startSet.has(a.extId) ? 1 : 0;
      const sb = startSet.has(b.extId) ? 1 : 0;
      return sb - sa || b.ros - a.ros;
    })),
    [mySquad, startSet],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">
          FPL Draft — {config?.teams ?? 5}-team league
          {gwCols.length ? ` · GW${gwCols[0]}–${gwCols.at(-1)}` : ""}
        </h1>
        <button className="btn" onClick={() => setShowSetup((v) => !v)}>
          {showSetup ? "Close" : "Setup"}
        </button>
      </div>
      {showSetup && <FplSetup onSaved={load} />}

      {(config?.mySquad?.length ?? 0) === 0 ? (
        <p className="card p-3 text-sm text-[var(--muted)]">
          Add your league ID + entry ID in Setup (no cookie needed), then run{" "}
          <code>./draft.sh --sport fpl --sync</code> from your machine.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">Next GW</div>
              <div className="text-lg font-semibold">GW{nextGw || "?"}</div>
            </div>
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">Your XI proj</div>
              <div className="text-lg font-semibold">{fmt(nextGwProj, 0)}</div>
              <div className="text-xs text-[var(--muted)]">{fromApp ? formation : "model best XI"}</div>
            </div>
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">Squad ROS / GW</div>
              <div className="text-lg font-semibold">{fmt(rosPerGw, 1)}</div>
            </div>
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">League rank</div>
              <div className="text-lg font-semibold">
                {myRank ?? "–"}
                {standings.length ? (
                  <span className="text-xs font-normal text-[var(--muted)]"> of {standings.length}</span>
                ) : null}
              </div>
            </div>
          </div>

          {config?.fplLive && (config?.fplLineup?.picks?.length ?? 0) >= 11 && (
            <FplLive
              live={config.fplLive}
              squad={mySquad}
              picks={config.fplLineup.picks}
            />
          )}

          {swaps.length > 0 && (
            <div className="card border-l-2 border-[var(--warn)] p-3 text-sm">
              <b className="text-[var(--warn)]">Bench call vs your set XI:</b>
              <ul className="mt-1 space-y-0.5">
                {swaps.map((s, i) => (
                  <li key={i}>
                    Start <b>{s.in.name}</b> for {s.out.name}{" "}
                    <span className="text-[var(--good)]">(+{fmt(s.gain)} proj)</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-[var(--muted)]">PRE-DEADLINE CHECKLIST</h2>
            <Checklist items={buildChecklist(xi, bench, nextGw, setXi?.src ?? null)} />
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-[var(--muted)]">
              YOUR SQUAD{" "}
              {fromApp && (
                <span className="font-normal text-[var(--muted)]">
                  · {setXi?.src === "my-team" ? "live Pick Team" : "last fielded XI"} ({formation})
                </span>
              )}
            </h2>
            <div className="card table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Player</th>
                    <th>Team</th>
                    <th>Opp (GW{nextGw || "?"})</th>
                    <th className="num">Start%</th>
                    <th className="num">Next</th>
                    <th className="num">ROS</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {ordered.map((p) => {
                    const g = p.gws[0];
                    const starting = startSet.has(p.extId);
                    return (
                      <tr key={p.extId} style={starting ? undefined : { opacity: 0.55 }}>
                        <td>
                          <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[p.pos] }}>
                            {p.pos}
                          </span>
                        </td>
                        <td className="font-medium">
                          {p.name}
                          {p.setPiece && (
                            <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">
                              {p.setPiece.replace("PK2", "PK²")}
                            </span>
                          )}
                          {STATUS_LABEL[p.status] && (
                            <span className="ml-1 text-[10px] text-[var(--bad)]" title={p.news}>
                              {STATUS_LABEL[p.status]}
                            </span>
                          )}
                          {p.suspRisk && (
                            <span className="ml-1 text-[var(--warn)]" title={`${p.ycToBan} booking from a ban`}>⚑</span>
                          )}
                        </td>
                        <td className="text-[var(--muted)]">{p.team}</td>
                        <td
                          className="font-medium"
                          style={{ color: g?.opp ? FDR_TEXT[g.fdr] ?? "var(--muted)" : "var(--muted)" }}
                          title={
                            g?.opp
                              ? `${p.pos} difficulty ${g.fdr}/5` +
                                (g.fdrAtt ? ` — goals/assists ${g.fdrAtt}/5, clean sheet ${g.fdrDef}/5` : "")
                              : "no fixture"
                          }
                        >
                          {g?.opp ? g.opp.replace(/ \(/g, " (") : "–"}
                        </td>
                        <td className="num">{p.pStart ? `${Math.round(p.pStart * 100)}%` : "–"}</td>
                        <td className="num font-semibold">{fmt(p.proj)}</td>
                        <td className="num">{fmt(p.ros, 0)}</td>
                        <td className="text-[10px] text-[var(--muted)]">{starting ? "XI" : "bench"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {mySquad.length > 0 && <FplFixtureRun squad={mySquad} />}

          <Legend
            items={[
              ["XI / bench", fromApp ? "your actual FPL lineup (live Pick Team with the pl_profile cookie, otherwise your last fielded XI)" : "the model's best legal XI (no saved lineup pulled yet)"],
              [
                "Opp colour",
                "position-aware fixture difficulty (green easy … red hard): forwards weigh the opponent's defensive solidity, keepers their attacking threat, defenders mostly clean-sheet risk plus some set-piece upside, midfielders mostly attacking",
              ],
              ["Start%", "modelled chance of starting the next match"],
              ["Next / ROS", "projected draft points next GW / rest of season"],
              ["⚑", "one booking from a suspension"],
            ]}
          />
        </>
      )}
    </div>
  );
}
