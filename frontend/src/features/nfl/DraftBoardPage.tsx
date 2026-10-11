import { useQueryClient } from "@tanstack/react-query";
import { Fragment, useMemo, useState } from "react";
import { $api, fetchClient, type Api } from "@/api/client";
import { DraftSetup } from "@/features/draft/DraftSetup";
import { fmt } from "@/shared/format";
import { Legend, PosBadge, QueryView } from "@/shared/ui";
import {
  fillRoster, matchesPos, myPickNumbers, POS_FILTERS, rosterNeeds, sortBoard, withTierBreaks, type PosFilter, type SortKey,
} from "./draftBoard";

const BOARD = { params: { query: { sport: "nfl" as const } } };

export default function NflDraftBoardPage() {
  const [setup, setSetup] = useState(false);
  // picks land from the ESPN sync or another device — keep the board current
  const q = $api.useQuery("get", "/api/draft/board", BOARD, { refetchInterval: 6_000 });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">NFL Draft Board</h1>
        <button type="button" className="btn" onClick={() => setSetup((v) => !v)}>
          {setup ? "Close" : "Setup"}
        </button>
      </div>
      {setup && <DraftSetup sport="nfl" />}
      <QueryView query={q}>{(b) => <Board b={b} />}</QueryView>
    </div>
  );
}

function Board({ b }: { b: Api["DraftBoard"] }) {
  const qc = useQueryClient();
  const [pos, setPos] = useState<PosFilter>("ALL");
  const [sort, setSort] = useState<SortKey>("vbd");
  const [search, setSearch] = useState("");
  const [hideKD, setHideKD] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const drafted = useMemo(() => new Set(b.picks.map((p) => p.playerExtId)), [b.picks]);
  const byId = useMemo(() => new Map(b.players.map((p) => [p.extId, p])), [b.players]);
  const mine = useMemo(
    () => b.picks.filter((p) => p.isMine).flatMap((p) => byId.get(p.playerExtId) ?? []),
    [b.picks, byId],
  );
  const available = useMemo(() => {
    const s = search.trim().toLowerCase();
    const list = b.players.filter(
      (p) => !drafted.has(p.extId) && matchesPos(p, pos) && !(hideKD && pos === "ALL" && (p.primaryPos === "K" || p.primaryPos === "DST")) &&
        (!s || p.name.toLowerCase().includes(s)),
    );
    const rows = sortBoard(list, sort).slice(0, 200);
    // tier headers only mean something when sorted by value or expert rank
    return sort === "ecrRank" || sort === "vbd" ? withTierBreaks(rows) : rows.map((p) => ({ p, tierBreak: false }));
  }, [b.players, drafted, pos, hideKD, search, sort]);
  const filled = useMemo(() => fillRoster(mine, b.roster), [mine, b.roster]);
  const needs = rosterNeeds(filled);
  const bestByPos = useMemo(
    () => Object.fromEntries(["QB", "RB", "WR", "TE"].map((P) => [P, sortBoard(b.players.filter((p) => !drafted.has(p.extId) && p.primaryPos === P), "vbd")[0]])),
    [b.players, drafted],
  );

  const nextOverall = b.picks.length + 1;
  const round = b.teams ? Math.floor((nextOverall - 1) / b.teams) + 1 : 0;
  const upcoming = b.mySlot ? myPickNumbers(b.mySlot, b.teams).filter((n) => n >= nextOverall).slice(0, 3) : [];

  async function run(call: () => Promise<{ response: Response }>) {
    setBusy(true);
    setError(null);
    const { response } = await call();
    if (!response.ok) setError(response.status === 403 ? "Read-only demo." : `Failed (${response.status})`);
    await qc.invalidateQueries({ queryKey: ["get", "/api/draft/board"] });
    setBusy(false);
  }
  const pick = (extId: string, isMine: boolean) =>
    run(() => fetchClient.POST("/api/draft/pick", { body: { sport: "nfl", extId, isMine } }));
  const undo = () => run(() => fetchClient.DELETE("/api/draft/pick", { params: { query: { sport: "nfl" } } }));
  const reset = () => {
    setConfirmReset(false);
    return run(() => fetchClient.DELETE("/api/draft/pick", { params: { query: { sport: "nfl", all: true } } }));
  };

  if (b.players.length === 0) {
    return (
      <div className="card p-8 text-center text-sm text-[var(--muted)]">
        No board yet — the pre-draft board builds on the next scheduled sync once your league is set up.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {POS_FILTERS.map((f) => (
            <button key={f} type="button" onClick={() => setPos(f)} className="btn" aria-pressed={f === pos}
              style={f === pos ? { background: "var(--accent)", borderColor: "var(--accent)", color: "#fff" } : undefined}>
              {f}
            </button>
          ))}
          <select className="input ml-auto" value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="sort by">
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
              {available.map(({ p, tierBreak }) => {
                return (
                  <Fragment key={p.extId}>
                    {tierBreak && (
                      <tr>
                        <td colSpan={9} className="bg-[var(--surface-2)] text-xs font-semibold text-[var(--muted)]">
                          Tier {p.ecrTier}
                        </td>
                      </tr>
                    )}
                    <tr>
                      <td>
                        <PosBadge position={p.primaryPos} />
                      </td>
                      <td>
                        <span className="font-medium">{p.name}</span> <span className="text-[var(--muted)]">{p.team}</span>
                        {p.injuryStatus && <span className="ml-1 text-[var(--bad)]" title={p.injuryStatus}>●</span>}
                        {p.ecrPosRank && <span className="ml-1 text-xs text-[var(--muted)]">{p.ecrPosRank}</span>}
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
                        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => pick(p.extId, true)}>
                          Me
                        </button>{" "}
                        <button type="button" className="btn" disabled={busy} onClick={() => pick(p.extId, false)}>
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

      <div className="space-y-4">
        <div className="card p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-semibold">
              Pick {nextOverall}
              {round ? ` · Rd ${round}` : ""}
            </span>
            <span className="flex gap-1">
              <button type="button" className="btn" disabled={busy || b.picks.length === 0} onClick={undo}>undo</button>
              {confirmReset ? (
                <>
                  <button type="button" className="btn" style={{ color: "var(--bad)" }} disabled={busy} onClick={reset}>
                    clear all?
                  </button>
                  <button type="button" className="btn" onClick={() => setConfirmReset(false)}>no</button>
                </>
              ) : (
                <button type="button" className="btn" disabled={busy || b.picks.length === 0} onClick={() => setConfirmReset(true)}>
                  reset
                </button>
              )}
            </span>
          </div>
          {b.mySlot ? (
            <div className="mt-1 text-[var(--muted)]">
              Your next: {upcoming.length ? upcoming.map((n) => `#${n}`).join(", ") : "—"}
              {upcoming[0] != null && ` (in ${upcoming[0] - nextOverall})`}
            </div>
          ) : (
            <div className="mt-1 text-xs text-[var(--warn)]">Set your draft slot in Setup for pick timing.</div>
          )}
          {error && <div className="mt-1 text-xs text-[var(--bad)]">{error}</div>}
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
              {filled.flatMap((row) =>
                Array.from({ length: row.need }, (_, i) => {
                  const pl = row.players[i];
                  return (
                    <tr key={`${row.slot}-${i}`}>
                      <td className="text-xs text-[var(--muted)]">{row.slot}</td>
                      <td>{pl ? pl.name : <span className="text-[var(--muted)]">—</span>}</td>
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
            const best = bestByPos[P];
            return (
              <div key={P} className="flex justify-between py-0.5">
                <span>
                  <b>{P}</b> {best?.name ?? "–"} <span className="text-[var(--muted)]">{best?.team}</span>
                </span>
                <span className="tabular-nums text-[var(--muted)]">{best ? fmt(best.vbd, 0) : ""}</span>
              </div>
            );
          })}
        </div>

        <div className="card p-3 text-xs text-[var(--muted)]">
          Live ESPN picks: on draft night run <code>fantasy draft-board --sport nfl --sync --loop 15</code> (needs ESPN
          cookies in Setup). Otherwise tap “gone” as picks happen.
        </div>
      </div>
    </div>
  );
}
