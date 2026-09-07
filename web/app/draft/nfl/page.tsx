"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import {
  POS_FILTERS,
  fillRoster,
  matchesPos,
  myPickNumbers,
  rosterNeeds,
  sortPlayers,
  type BoardPick,
  type BoardPlayer,
  type DraftConfig,
  type PosFilter,
  type SortKey,
} from "./lib";
import { DraftSetup } from "./Setup";

const POS_COLOR: Record<string, string> = {
  QB: "#8957e5", RB: "#1a7f37", WR: "#1f6feb", TE: "#b7791f", K: "#6b7280", DST: "#cf222e",
};

export default function NflDraftPage() {
  const [players, setPlayers] = useState<BoardPlayer[]>([]);
  const [picks, setPicks] = useState<BoardPick[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [pos, setPos] = useState<PosFilter>("ALL");
  const [sort, setSort] = useState<SortKey>("vbd");
  const [search, setSearch] = useState("");
  const [hideKD, setHideKD] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch("/api/draft/board?sport=nfl", { cache: "no-store" });
    const d = await r.json();
    setPlayers(
      (d.players ?? []).map((p: Record<string, unknown>) => ({
        extId: p.extId, name: p.name, team: p.team, positions: p.positions,
        primaryPos: p.primaryPos, projPoints: p.projPoints, adp: p.adp,
        providerRank: p.providerRank, ecrRank: p.ecrRank, ecrTier: p.ecrTier,
        ecrPosRank: p.ecrPosRank, ecrStd: p.ecrStd, vbd: p.vbd, byeWeek: p.byeWeek,
        injuryStatus: p.injuryStatus, outlook: p.outlook,
      })),
    );
    setPicks(d.picks ?? []);
    setConfig(d.config ?? null);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  const drafted = useMemo(() => new Set(picks.map((p) => p.playerExtId)), [picks]);
  const byId = useMemo(() => new Map(players.map((p) => [p.extId, p])), [players]);
  const mine = useMemo(
    () => picks.filter((p) => p.isMine).map((p) => byId.get(p.playerExtId)).filter(Boolean) as BoardPlayer[],
    [picks, byId],
  );

  const available = useMemo(() => {
    let list = players.filter((p) => !drafted.has(p.extId) && matchesPos(p, pos));
    if (hideKD && pos === "ALL") list = list.filter((p) => !["K", "DST"].includes(p.primaryPos));
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((p) => p.name.toLowerCase().includes(q));
    }
    return sortPlayers(list, sort).slice(0, 200);
  }, [players, drafted, pos, hideKD, search, sort]);

  const filled = useMemo(
    () => (config ? fillRoster(mine, config.roster) : []),
    [mine, config],
  );
  const needs = useMemo(() => rosterNeeds(filled), [filled]);

  const nextOverall = picks.length + 1;
  const round = config ? Math.floor((nextOverall - 1) / config.teams) + 1 : 0;
  const myUpcoming = useMemo(() => {
    if (!config?.mySlot) return [] as number[];
    return myPickNumbers(config.mySlot, config.teams).filter((n) => n >= nextOverall).slice(0, 3);
  }, [config, nextOverall]);

  async function pick(extId: string, isMine: boolean) {
    setBusy(true);
    await fetch("/api/draft/pick", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sport: "nfl", extId, isMine }),
    });
    await load();
    setBusy(false);
  }
  async function undo() {
    setBusy(true);
    await fetch("/api/draft/pick?sport=nfl", { method: "DELETE" });
    await load();
    setBusy(false);
  }
  async function reset() {
    if (!confirm("Clear ALL picks (manual + synced)?")) return;
    setBusy(true);
    await fetch("/api/draft/pick?sport=nfl&all=1", { method: "DELETE" });
    await load();
    setBusy(false);
  }

  const bestByPos = useMemo(() => {
    const out: Record<string, BoardPlayer | undefined> = {};
    for (const P of ["QB", "RB", "WR", "TE"]) {
      out[P] = sortPlayers(
        players.filter((p) => !drafted.has(p.extId) && p.primaryPos === P),
        "vbd",
      )[0];
    }
    return out;
  }, [players, drafted]);

  if (!players.length) {
    return (
      <div className="space-y-3">
        <Header onSetup={() => setShowSetup((v) => !v)} />
        {showSetup && <DraftSetup onSaved={load} />}
        <div className="card p-8 text-center text-sm text-[var(--muted)]">
          No board yet. Run <code>python -m fantasy_ingest.draft --sport nfl</code> on your machine,
          then reload.
        </div>
      </div>
    );
  }

  let lastTier: number | null = null;

  return (
    <div className="space-y-4">
      <Header onSetup={() => setShowSetup((v) => !v)} />
      {showSetup && <DraftSetup onSaved={load} />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        {/* ---- board ---- */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {POS_FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setPos(f)}
                className="btn"
                style={f === pos ? { background: "var(--accent)", borderColor: "var(--accent)", color: "#fff" } : undefined}
              >
                {f}
              </button>
            ))}
            <select className="input ml-auto" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="vbd">Sort: VBD</option>
              <option value="projPoints">Sort: Proj pts</option>
              <option value="adp">Sort: ADP</option>
              <option value="ecrRank">Sort: Expert rank</option>
            </select>
            <input className="input w-40" placeholder="search" value={search} onChange={(e) => setSearch(e.target.value)} />
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={hideKD} onChange={(e) => setHideKD(e.target.checked)} /> hide K/DST
            </label>
          </div>

          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Pos</th>
                  <th>Player</th>
                  <th className="hide-sm">Bye</th>
                  <th className="num">Proj</th>
                  <th className="num">VBD</th>
                  <th className="num hide-sm">ADP</th>
                  <th className="num">ECR</th>
                  <th className="hide-sm">±</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {available.map((p) => {
                  const showTier =
                    (sort === "ecrRank" || sort === "vbd") && p.ecrTier != null && p.ecrTier !== lastTier;
                  if (p.ecrTier != null && (sort === "ecrRank" || sort === "vbd")) lastTier = p.ecrTier;
                  return (
                    <Fragment key={p.extId}>
                      {showTier && (
                        <tr>
                          <td colSpan={9} className="bg-[var(--surface-2)] text-xs font-semibold text-[var(--muted)]">
                            Tier {p.ecrTier}
                          </td>
                        </tr>
                      )}
                      <tr>
                        <td>
                          <span
                            className="inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold text-white"
                            style={{ background: POS_COLOR[p.primaryPos] ?? "#6b7280" }}
                          >
                            {p.primaryPos}
                          </span>
                        </td>
                        <td>
                          <span className="font-medium">{p.name}</span>{" "}
                          <span className="text-[var(--muted)]">{p.team}</span>
                          {p.injuryStatus && (
                            <span className="ml-1 text-[var(--bad)]" title={p.injuryStatus}>●</span>
                          )}
                          {p.ecrPosRank && (
                            <span className="ml-1 text-xs text-[var(--muted)]">{p.ecrPosRank}</span>
                          )}
                        </td>
                        <td className="hide-sm">{p.byeWeek ?? "–"}</td>
                        <td className="num">{fmt(p.projPoints, 0)}</td>
                        <td className="num font-semibold">{fmt(p.vbd, 0)}</td>
                        <td className="num hide-sm">{p.adp ? fmt(p.adp, 1) : "–"}</td>
                        <td className="num">{p.ecrRank ?? "–"}</td>
                        <td className="hide-sm" title={`expert disagreement (std ${fmt(p.ecrStd, 1)})`}>
                          {p.ecrStd >= 12 ? "⚠︎" : p.ecrStd >= 7 ? "~" : ""}
                        </td>
                        <td className="whitespace-nowrap">
                          <button className="btn btn-primary" disabled={busy} onClick={() => pick(p.extId, true)}>
                            Me
                          </button>{" "}
                          <button className="btn" disabled={busy} onClick={() => pick(p.extId, false)}>
                            gone
                          </button>
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          <Legend
            items={[
              ["Proj", "projected fantasy points for the full season"],
              ["VBD", "value over replacement — projected points above a waiver-level starter at that position"],
              ["ADP", "average draft position (ESPN)"],
              ["ECR", "expert consensus rank (FantasyPros)"],
              ["±", "how much the experts disagree — ⚠︎ high, ~ some"],
              ["Tier", "FantasyPros tier — a break marks a real talent drop-off"],
            ]}
          />
        </div>

        {/* ---- side panel ---- */}
        <div className="space-y-4">
          <div className="card p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-semibold">Pick {nextOverall}{round ? ` · Rd ${round}` : ""}</span>
              <span>
                <button className="btn" disabled={busy} onClick={undo}>undo</button>{" "}
                <button className="btn" disabled={busy} onClick={reset}>reset</button>
              </span>
            </div>
            {config?.mySlot ? (
              <div className="mt-1 text-[var(--muted)]">
                Your next: {myUpcoming.length ? myUpcoming.map((n) => `#${n}`).join(", ") : "—"}
                {myUpcoming[0] && ` (in ${myUpcoming[0] - nextOverall})`}
              </div>
            ) : (
              <div className="mt-1 text-xs text-[var(--warn)]">Set your draft slot in Setup for pick timing.</div>
            )}
          </div>

          <div className="card p-3">
            <div className="mb-2 text-sm font-semibold">
              My roster{" "}
              <span className="text-xs font-normal text-[var(--muted)]">
                {Object.entries(needs).map(([s, n]) => `${s}×${n}`).join("  ") || "full"}
              </span>
            </div>
            <table className="dtable">
              <tbody>
                {filled.map((row) =>
                  Array.from({ length: row.need }).map((_, i) => {
                    const pl = row.players[i];
                    return (
                      <tr key={`${row.slot}-${i}`}>
                        <td className="text-xs text-[var(--muted)]">{row.slot}</td>
                        <td>{pl ? `${pl.name}` : <span className="text-[var(--muted)]">—</span>}</td>
                        <td className="num text-xs text-[var(--muted)]">{pl ? fmt(pl.projPoints, 0) : ""}</td>
                      </tr>
                    );
                  }),
                )}
              </tbody>
            </table>
          </div>

          <div className="card p-3 text-sm">
            <div className="mb-2 font-semibold">Best available</div>
            {["QB", "RB", "WR", "TE"].map((P) => {
              const b = bestByPos[P];
              return (
                <div key={P} className="flex justify-between py-0.5">
                  <span>
                    <b>{P}</b> {b?.name ?? "–"}{" "}
                    <span className="text-[var(--muted)]">{b?.team}</span>
                  </span>
                  <span className="tabular-nums text-[var(--muted)]">{b ? fmt(b.vbd, 0) : ""}</span>
                </div>
              );
            })}
          </div>

          <div className="card p-3 text-xs text-[var(--muted)]">
            Live ESPN picks: run{" "}
            <code>python -m fantasy_ingest.draft --sport nfl --sync --loop 15</code> on your machine
            (needs ESPN cookies in Setup). Otherwise tap “gone” as picks happen.
          </div>
        </div>
      </div>
    </div>
  );
}

function Header({ onSetup }: { onSetup: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <h1 className="text-xl font-semibold">NFL Draft Board</h1>
      <button className="btn" onClick={onSetup}>Setup</button>
    </div>
  );
}
