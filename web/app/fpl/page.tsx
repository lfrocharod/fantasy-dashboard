"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  HORIZON_LABEL,
  POS,
  bestXI,
  sortPlayers,
  squadHorizon,
  stashCandidates,
  toPlayer,
  valueFor,
  weakSpots,
  type FplPlayer,
  type Horizon,
  type PosFilter,
  type SortKey,
} from "./lib";
import { FplSetup } from "./Setup";

const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280",
  DEF: "#1f6feb",
  MID: "#1a7f37",
  FWD: "#cf222e",
};
const STATUS_LABEL: Record<string, string> = {
  d: "doubt", i: "injured", s: "susp", u: "unavail", n: "out",
};

// fixture difficulty (1 easy … 5 hard) → cell background
const FDR_BG: Record<number, string> = {
  1: "rgba(34,197,94,0.32)",
  2: "rgba(132,204,22,0.24)",
  3: "rgba(148,163,184,0.14)",
  4: "rgba(249,115,22,0.24)",
  5: "rgba(239,68,68,0.30)",
};
function fdrBg(fdr: number, hasFixture: boolean): string {
  if (!hasFixture) return "transparent";
  return FDR_BG[fdr] ?? "transparent";
}

export default function FplDraftPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [pos, setPos] = useState<PosFilter>("ALL");
  const [sort, setSort] = useState<SortKey>("horizon");
  const [search, setSearch] = useState("");
  const [availableOnly, setAvailableOnly] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [showBoard, setShowBoard] = useState(false);
  const [matrixMode, setMatrixMode] = useState<"squad" | "targets">("squad");
  const [horizon, setHorizon] = useState<Horizon>("medium");

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
  const mineIds = useMemo(() => new Set(mySquad.map((p) => p.extId)), [mySquad]);

  // gameweek columns (from any player's gws array)
  const gwCols = useMemo(() => (players[0]?.gws ?? []).map((g) => g.gw), [players]);

  const lineup = useMemo(() => (mySquad.length >= 11 ? bestXI(mySquad) : null), [mySquad]);

  // weak-spot upgrades: only genuine holes (below replacement / rotation risk)
  const upgrades = useMemo(() => {
    if (!lineup) return [];
    const free = players.filter((p) => p.available && !mineIds.has(p.extId));
    return weakSpots(lineup.xi, free, horizon);
  }, [lineup, players, mineIds, horizon]);

  const stash = useMemo(() => stashCandidates(players, mineIds), [players, mineIds]);

  const matrixRows = useMemo(() => {
    if (matrixMode === "squad") {
      return [...mySquad].sort(
        (a, b) => ["GKP", "DEF", "MID", "FWD"].indexOf(a.pos) - ["GKP", "DEF", "MID", "FWD"].indexOf(b.pos) || b.horizon - a.horizon,
      );
    }
    let l = players.filter((p) => p.available && !mineIds.has(p.extId));
    if (pos !== "ALL") l = l.filter((p) => p.pos === pos);
    return sortPlayers(l, "horizon").slice(0, 30);
  }, [matrixMode, mySquad, players, mineIds, pos]);

  const boardList = useMemo(() => {
    let l = players;
    if (pos !== "ALL") l = l.filter((p) => p.pos === pos);
    if (availableOnly) l = l.filter((p) => p.available);
    if (search.trim()) {
      const q = search.toLowerCase();
      l = l.filter((p) => p.name.toLowerCase().includes(q));
    }
    return sortPlayers(l, sort).slice(0, 200);
  }, [players, pos, availableOnly, search, sort]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">
          FPL Draft — {config?.teams ?? 5}-team league{gwCols.length ? ` · GW${gwCols[0]}–${gwCols.at(-1)}` : ""}
        </h1>
        <button className="btn" onClick={() => setShowSetup((v) => !v)}>
          {showSetup ? "Close" : "Setup"}
        </button>
      </div>
      {showSetup && <FplSetup onSaved={load} />}

      {(config?.mySquad?.length ?? 0) === 0 && (
        <p className="card p-3 text-sm text-[var(--muted)]">
          Add your league ID + entry ID in Setup (no cookie needed), then run{" "}
          <code>./draft.sh --sport fpl --sync</code> from your machine.
        </p>
      )}

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
                        style={{ background: fdrBg(g.fdr, !!g.opp) }}
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
          <h2 className="text-sm font-semibold text-[var(--muted)]">STASH &amp; WAIT (injured, but worth a roster spot)</h2>
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

      {/* ---- FULL BOARD ---- */}
      <section className="space-y-2">
        <button
          className="text-sm font-semibold text-[var(--muted)]"
          onClick={() => setShowBoard((v) => !v)}
        >
          {showBoard ? "▾" : "▸"} FULL BOARD ({players.length} players)
        </button>
        {showBoard && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {POS.map((p) => (
                <button
                  key={p}
                  onClick={() => setPos(p)}
                  className={`rounded px-2 py-1 text-xs ${pos === p ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
                >
                  {p}
                </button>
              ))}
              <label className="ml-2 flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={availableOnly}
                  onChange={(e) => setAvailableOnly(e.target.checked)}
                />
                available only
              </label>
              <select
                className="input ml-auto text-xs"
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
              >
                <option value="horizon">Sort: horizon</option>
                <option value="proj">Sort: next GW</option>
                <option value="vbd">Sort: value over replacement</option>
                <option value="csProb">Sort: clean-sheet %</option>
                <option value="form">Sort: form</option>
                <option value="totalPoints">Sort: total points</option>
              </select>
              <input
                className="input text-xs"
                placeholder="search…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="card table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Player</th>
                    <th className="hide-sm">Team</th>
                    <th>Next</th>
                    <th className="num">Next</th>
                    <th className="num">Σ{gwCols.length}</th>
                    <th className="num hide-sm">CS%</th>
                    <th className="num hide-sm">xGI90</th>
                    <th className="num hide-sm">Form</th>
                    <th>Owner</th>
                  </tr>
                </thead>
                <tbody>
                  {boardList.map((p) => (
                    <tr
                      key={p.extId}
                      style={mineIds.has(p.extId) ? { background: "rgba(31,111,235,0.08)" } : undefined}
                    >
                      <td>
                        <span
                          className="rounded px-1 text-[10px] font-bold text-white"
                          style={{ background: POS_COLOR[p.pos] }}
                        >
                          {p.pos}
                        </span>
                      </td>
                      <td className="font-medium">
                        {p.name}
                        {p.setPiece && (
                          <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">
                            {p.setPiece}
                          </span>
                        )}
                        {STATUS_LABEL[p.status] && (
                          <span className="ml-1 text-[10px] text-[var(--bad)]" title={p.news}>
                            {STATUS_LABEL[p.status]}
                          </span>
                        )}
                      </td>
                      <td className="hide-sm">{p.team}</td>
                      <td className="text-xs">{p.nextOpp}</td>
                      <td className="num">{fmt(p.proj)}</td>
                      <td className="num font-semibold">{fmt(p.horizon, 0)}</td>
                      <td className="num hide-sm">{p.pos === "FWD" ? "–" : Math.round(p.csProb * 100)}</td>
                      <td className="num hide-sm">{fmt(p.xgi90, 2)}</td>
                      <td className="num hide-sm">{fmt(p.form)}</td>
                      <td className="text-xs">
                        {mineIds.has(p.extId) ? (
                          <span className="text-[var(--accent)]">you</span>
                        ) : p.available ? (
                          <span className="text-[var(--good)]">FA</span>
                        ) : (
                          <span className="text-[var(--muted)]">{p.ownerName || "owned"}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <Legend
        items={[
          ["Matrix cell", "colour = fixture difficulty (green easy … red hard); number = projected points"],
          ["Next / Σ", "projected draft points — one gameweek, then the sum over the shown horizon"],
          ["CS%", "clean-sheet probability (two-sided: opponent attack vs your team's defence). GKP/DEF worth 4, MID 1"],
          ["xGI90", "expected goal involvements per 90 (season)"],
          ["P / F / C", "first-choice penalties / free-kicks / corners"],
          ["Components", "projection folds in goals, assists, appearance, clean sheet, saves (GK), DEFCON and bonus on draft scoring"],
          ["FA", "free agent in your league; a name = the manager who has them"],
        ]}
      />
    </div>
  );
}
