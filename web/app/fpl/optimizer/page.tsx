"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import {
  HORIZON_LABEL,
  POS,
  bestXI,
  loadBoard,
  sortPlayers,
  squadHorizon,
  stashCandidates,
  valueFor,
  weakSpots,
  type FplPlayer,
  type Horizon,
  type PosFilter,
} from "../lib";
import { FDR_BG } from "@/lib/fdr";

const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};
const STATUS_LABEL: Record<string, string> = {
  d: "doubt", i: "injured", s: "susp", u: "unavail", n: "out",
};

export default function FplOptimizerPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [mineIds, setMineIds] = useState<Set<string>>(new Set());
  const [pos, setPos] = useState<PosFilter>("ALL");
  const [matrixMode, setMatrixMode] = useState<"squad" | "targets">("squad");
  const [horizon, setHorizon] = useState<Horizon>("medium");

  useEffect(() => {
    loadBoard().then((d) => {
      setPlayers(d.players);
      setMineIds(new Set(d.config?.mySquad ?? []));
    });
  }, []);

  const byId = useMemo(() => new Map(players.map((p) => [p.extId, p])), [players]);
  const mySquad = useMemo(
    () => [...mineIds].map((id) => byId.get(id)).filter(Boolean) as FplPlayer[],
    [mineIds, byId],
  );
  const gwCols = useMemo(() => (players[0]?.gws ?? []).map((g) => g.gw), [players]);
  const lineup = useMemo(() => (mySquad.length >= 11 ? bestXI(mySquad) : null), [mySquad]);

  const upgrades = useMemo(() => {
    if (!lineup) return [];
    const free = players.filter((p) => p.available && !mineIds.has(p.extId));
    return weakSpots(lineup.xi, free, horizon);
  }, [lineup, players, mineIds, horizon]);

  const stash = useMemo(() => stashCandidates(players, mineIds), [players, mineIds]);

  const matrixRows = useMemo(() => {
    if (matrixMode === "squad") {
      return [...mySquad].sort(
        (a, b) =>
          ["GKP", "DEF", "MID", "FWD"].indexOf(a.pos) - ["GKP", "DEF", "MID", "FWD"].indexOf(b.pos) ||
          b.horizon - a.horizon,
      );
    }
    let l = players.filter((p) => p.available && !mineIds.has(p.extId));
    if (pos !== "ALL") l = l.filter((p) => p.pos === pos);
    return sortPlayers(l, "horizon").slice(0, 30);
  }, [matrixMode, mySquad, players, mineIds, pos]);

  if (!players.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Run <code>./draft.sh --sport fpl --sync</code> first.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Optimizer</h1>

      {/* ---- ROTATION MATRIX ---- */}
      {gwCols.length > 0 && (
        <section className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-[var(--muted)]">ROTATION PLANNER</h2>
            <div className="ml-auto flex gap-1 text-xs">
              <button
                onClick={() => setMatrixMode("squad")}
                className={`rounded px-2 py-1 ${matrixMode === "squad" ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
              >
                My squad
              </button>
              <button
                onClick={() => setMatrixMode("targets")}
                className={`rounded px-2 py-1 ${matrixMode === "targets" ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
              >
                Free-agent targets
              </button>
            </div>
          </div>
          {matrixMode === "targets" && (
            <div className="flex flex-wrap gap-1">
              {POS.map((p) => (
                <button
                  key={p}
                  onClick={() => setPos(p)}
                  className={`rounded px-2 py-0.5 text-xs ${pos === p ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
          <div className="card table-wrap">
            <table className="dtable text-xs">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-[var(--surface)]">Player</th>
                  {gwCols.map((g) => (
                    <th key={g} className="num">
                      GW{g}
                    </th>
                  ))}
                  <th className="num">Σ{gwCols.length}</th>
                  <th className="num hide-sm">CS%</th>
                </tr>
              </thead>
              <tbody>
                {matrixRows.map((p) => (
                  <tr key={p.extId}>
                    <td className="sticky left-0 whitespace-nowrap bg-[var(--surface)] font-medium">
                      <span
                        className="mr-1 rounded px-1 text-[9px] font-bold text-white"
                        style={{ background: POS_COLOR[p.pos] }}
                      >
                        {p.pos}
                      </span>
                      {p.name}
                      {p.setPiece && <span className="ml-1 text-[9px] text-[var(--accent)]">{p.setPiece}</span>}
                      {STATUS_LABEL[p.status] && (
                        <span className="ml-1 text-[9px] text-[var(--bad)]">{STATUS_LABEL[p.status]}</span>
                      )}
                    </td>
                    {p.gws.map((g) => (
                      <td
                        key={g.gw}
                        className="num"
                        style={{ background: g.opp ? FDR_BG[g.fdr] ?? "transparent" : "transparent" }}
                        title={g.opp ? `${g.opp} · difficulty ${g.fdr}/5 · proj ${fmt(g.xpts)}` : "no fixture"}
                      >
                        <div className="font-semibold">{g.opp ? fmt(g.xpts) : "–"}</div>
                        <div className="text-[9px] text-[var(--muted)]">{g.opp.replace(/ \(/g, "(")}</div>
                      </td>
                    ))}
                    <td className="num font-semibold">{fmt(p.horizon, 0)}</td>
                    <td className="num hide-sm">{p.pos === "FWD" ? "–" : `${Math.round(p.csProb * 100)}`}</td>
                  </tr>
                ))}
              </tbody>
              {matrixMode === "squad" && lineup && (
                <tfoot>
                  <tr className="border-t border-[var(--border)] font-semibold">
                    <td className="sticky left-0 bg-[var(--surface)]">Best XI total</td>
                    {gwCols.map((_g, gi) => {
                      const { xi } = bestXI(mySquad, (pp) => pp.gws[gi]?.xpts ?? 0);
                      const t = xi.reduce((a, pp) => a + (pp.gws[gi]?.xpts ?? 0), 0);
                      return (
                        <td key={gi} className="num">
                          {fmt(t, 0)}
                        </td>
                      );
                    })}
                    <td className="num">{fmt(squadHorizon(mySquad, gwCols.map((_g, i) => i)), 0)}</td>
                    <td className="hide-sm" />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          <p className="text-xs text-[var(--muted)]">
            <b>Cell colour = fixture difficulty</b> (green easy → red hard); the number is that
            player&apos;s projected points. Σ is the sum over the shown gameweeks. The footer is your
            best legal XI total per GW (no captaincy in draft) — watch it for the weeks a waiver or
            trade buys you the most.
          </p>
        </section>
      )}

      {/* ---- WEAK SPOTS ---- */}
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">WAIVER CLAIMS</h2>
          <div className="ml-auto flex gap-1 text-xs">
            {(["short", "medium", "season"] as const).map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`rounded px-2 py-1 ${horizon === h ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
              >
                {HORIZON_LABEL[h]}
              </button>
            ))}
          </div>
        </div>
        {upgrades.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No free agent clearly improves your XI over the {HORIZON_LABEL[horizon]} window.
          </p>
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Drop</th>
                  <th>Claim</th>
                  <th className="num hide-sm">Next</th>
                  <th className="num">+ pts</th>
                </tr>
              </thead>
              <tbody>
                {upgrades.map((u) => (
                  <tr key={u.in.extId}>
                    <td>
                      {u.out.name}{" "}
                      <span className="text-[var(--muted)]">({fmt(valueFor(u.out, horizon), 0)})</span>
                    </td>
                    <td className="font-medium">
                      {u.in.name}{" "}
                      <span className="text-[var(--muted)]">{u.in.team} · {u.in.nextOpp}</span>
                      {u.in.suspRisk && (
                        <span className="ml-1 text-[var(--warn)]" title={`${u.in.ycToBan} booking from a ban`}>
                          ⚑
                        </span>
                      )}
                    </td>
                    <td className="num hide-sm">{fmt(u.in.proj)}</td>
                    <td className="num font-semibold text-[var(--good)]">+{fmt(u.gain, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-[var(--muted)]">
          {horizon === "short"
            ? "Short-term: just needs to feature this week — suspension risk doesn't matter."
            : "Medium/long: fit, nailed starters only, and players a booking from a ban are excluded."}
        </p>
      </section>

      {/* ---- STASH / WAIT ---- */}
      {stash.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            STASH &amp; WAIT (injured, but worth a roster spot)
          </h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="hide-sm">News</th>
                  <th className="num">When fit</th>
                  <th className="num hide-sm">Total pts</th>
                </tr>
              </thead>
              <tbody>
                {stash.map((p) => (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td className="hide-sm text-xs text-[var(--muted)]">{p.news || p.status}</td>
                    <td className="num font-semibold">{fmt(p.fitNext)}</td>
                    <td className="num hide-sm">{p.totalPoints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["Matrix cell", "colour = fixture difficulty (green easy … red hard); number = projected points"],
          ["Σ", "sum of projected points over the shown gameweeks"],
          ["CS%", "clean-sheet probability (opponent attack vs your team's defence)"],
          ["+ pts", "projected gain over the player you'd drop, across the selected window"],
          ["When fit", "projected next-GW output once the injury clears"],
        ]}
      />
    </div>
  );
}
