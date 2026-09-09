"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend, PosBadge, StatusDot } from "@/components/ui";
import { fmt } from "@/lib/format";
import { POSITIONS, type Position } from "@/lib/ucl/formation";
import type { PlayerRow } from "@/lib/ucl/queries";
import { hasUsableXg } from "@/lib/ucl/xg";

type SortKey =
  | "xpts" | "value" | "price" | "selectedPct" | "differential" | "hotScore"
  | "xgi90" | "npxg90" | "xa90" | "sh90";

// Season non-penalty xG / xA per 90 — `player_stats` combined scope, written
// from Sofascore's per-league statistics, so it covers every CL club (all
// leagues), not just the big-5 the Understat layer sees. Only shown once the
// sample clears the same bar the projection model trusts it at (~3 matches /
// 200 league minutes).
const hasXg = hasUsableXg;
const npxg90 = (p: PlayerRow) => (hasXg(p) ? (p.xgNpxg90 ?? 0) : null);
const xa90 = (p: PlayerRow) => (hasXg(p) ? (p.xgXa90 ?? 0) : null);
const sh90 = (p: PlayerRow) => (hasXg(p) ? (p.xgShots90 ?? 0) : null);
const xgi90 = (p: PlayerRow) => (hasXg(p) ? (p.xgNpxg90 ?? 0) + (p.xgXa90 ?? 0) : null);

function sortVal(p: PlayerRow, k: SortKey): number {
  if (k === "differential")
    return (p.xpts ?? 0) / Math.max(3, p.selectedPct ?? 100);
  if (k === "hotScore") return p.hotScore ?? 0;
  if (k === "xgi90") return xgi90(p) ?? -1;
  if (k === "npxg90") return npxg90(p) ?? -1;
  if (k === "xa90") return xa90(p) ?? -1;
  if (k === "sh90") return sh90(p) ?? -1;
  return Number(p[k as keyof PlayerRow] ?? 0);
}

export default function PlayersPage() {
  const [players, setPlayers] = useState<PlayerRow[]>([]);
  const [ownedIds, setOwnedIds] = useState<number[]>([]);
  const [matchday, setMatchday] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const [position, setPosition] = useState<Position | "">("");
  const [maxPrice, setMaxPrice] = useState("");
  const [search, setSearch] = useState("");
  const [hideOwned, setHideOwned] = useState(true);
  const [sort, setSort] = useState<SortKey>("xpts");

  useEffect(() => {
    const ctl = new AbortController();
    const q = new URLSearchParams();
    if (position) q.set("position", position);
    if (maxPrice) q.set("maxPrice", maxPrice);
    if (search) q.set("search", search);
    q.set("limit", "250");
    setLoading(true);
    const t = setTimeout(() => {
      fetch(`/api/ucl/players?${q}`, { signal: ctl.signal })
        .then((r) => r.json())
        .then((d) => {
          setPlayers(d.players ?? []);
          setOwnedIds(d.ownedIds ?? []);
          setMatchday(d.matchday ?? null);
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 200);
    return () => {
      ctl.abort();
      clearTimeout(t);
    };
  }, [position, maxPrice, search]);

  const owned = useMemo(() => new Set(ownedIds), [ownedIds]);

  const rows = useMemo(() => {
    const list = hideOwned ? players.filter((p) => !owned.has(p.playerId)) : players;
    // Price and ownership read "best" as smallest (cheapest / biggest differential);
    // everything else reads "best" as largest. Best always sorts to the top.
    const asc = sort === "price" || sort === "selectedPct";
    return [...list].sort((a, b) =>
      asc ? sortVal(a, sort) - sortVal(b, sort) : sortVal(b, sort) - sortVal(a, sort),
    );
  }, [players, owned, hideOwned, sort]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Position</div>
          <select className="input" value={position} onChange={(e) => setPosition(e.target.value as Position | "")}>
            <option value="">All</option>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Max price (€m)</div>
          <input className="input w-28" inputMode="decimal" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="any" />
        </label>
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Search</div>
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="name" />
        </label>
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Sort by</div>
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="xpts">xPts</option>
            <option value="value">Value (xPts/€)</option>
            <option value="differential">Differential (xPts / owned%)</option>
            <option value="hotScore">Hot form</option>
            <option value="xgi90">xGI/90 (season)</option>
            <option value="npxg90">npxG/90 (season)</option>
            <option value="xa90">xA/90 (season)</option>
            <option value="sh90">Shots/90 (season)</option>
            <option value="price">Price</option>
            <option value="selectedPct">Ownership</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={hideOwned} onChange={(e) => setHideOwned(e.target.checked)} />
          Free agents only
        </label>
        <span className="ml-auto text-xs text-[var(--muted)]">
          {loading ? "loading…" : `${rows.length} players · MD ${matchday ?? "?"}`}
        </span>
      </div>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th className="hide-sm">Team</th>
              <th className="num">Price</th>
              <th className="num hide-sm">Own%</th>
              <th className="num hide-sm">L5 G+A</th>
              <th className="num hide-sm" title="expected goal involvements per 90 this domestic-league season (non-penalty xG + xA, Sofascore) — every CL club">
                xGI90
              </th>
              <th className="num hide-sm" title="shots per 90 this domestic-league season">Sh90</th>
              <th className="num hide-sm">Rtg</th>
              <th className="num">Start%</th>
              <th className="num">xPts</th>
              <th className="num hide-sm">xPts(C)</th>
              <th className="num">Value</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const cmp = p.components as Record<string, number> | undefined;
              const conf = cmp?.confirmed === 1 ? "start" : cmp?.confirmed === -1 ? "bench" : null;
              const sp = conf === "start" ? 1 : conf === "bench" ? 0 : (p.startProb ?? p.pStart ?? null);
              const disagree = conf ? 0 : Number(cmp?.start_disagreement ?? 0);
              const lev = p.role && p.role !== p.position && ["FWD", "MID"].includes(p.role);
              const l4 =
                p.recentMatches != null && p.recentMatches > 0
                  ? (p.recentGoals ?? 0) + (p.recentAssists ?? 0)
                  : null;
              return (
                  <tr key={p.playerId} style={p.teamOk === false ? { opacity: 0.4 } : undefined}>
                    <td>
                      <PosBadge position={p.position} />
                      {lev && (
                        <span
                          className="ml-1 text-[11px] font-semibold text-[var(--warn)]"
                          title={p.roleNote ?? ""}
                        >
                          →{p.role}
                        </span>
                      )}
                    </td>
                    <td>
                      {p.name} <StatusDot code={p.statusCode} detail={p.statusDetail} />
                      {p.teamOk === false && (
                        <span className="ml-1 text-[10px] text-[var(--bad)]" title={p.roleNote ?? ""}>
                          transferred?
                        </span>
                      )}
                      {(p.hotScore ?? 0) >= 0.9 && (
                        <span className="ml-1" title={`hot form: ${fmt(p.hotScore, 2)} G+A per 90`}>🔥</span>
                      )}
                      {p.setPiece && (
                        <span
                          className="ml-1 rounded border border-[var(--border)] px-1 text-[10px] font-semibold text-[var(--accent)]"
                          title="set-piece duty (penalties / free-kicks / corners)"
                        >
                          {p.setPiece.replace("PK2", "PK²")}
                        </span>
                      )}
                      {p.priceMomentum >= 0.25 && (
                        <span className="ml-1 text-[var(--good)]" title="net transfers in — price likely rising">📈</span>
                      )}
                      {p.priceMomentum <= -0.25 && (
                        <span className="ml-1 text-[var(--bad)]" title="net transfers out — price likely falling">📉</span>
                      )}
                      {(p.selectedPct ?? 100) < 8 && (p.xpts ?? 0) >= 4.5 && !owned.has(p.playerId) && (
                        <span
                          className="ml-1 rounded bg-[var(--good)] px-1 text-[10px] font-semibold text-white"
                          title="low ownership, high projection — a differential to gain rank"
                        >
                          DIFF
                        </span>
                      )}
                    </td>
                    <td className="hide-sm">{p.teamName}</td>
                    <td className="num">{fmt(p.price)}</td>
                    <td className="num hide-sm">{fmt(p.selectedPct, 0)}</td>
                    <td className="num hide-sm">
                      {l4 != null ? `${fmt(l4, 0)} / ${p.recentMatches}` : "–"}
                    </td>
                    <td
                      className="num hide-sm"
                      title={
                        xgi90(p) != null
                          ? `npxG/90 ${fmt(npxg90(p), 2)} + xA/90 ${fmt(xa90(p), 2)} · ${p.xgMatches} league matches, ${fmt(p.xgMinutes, 0)} min`
                          : "not enough domestic-league minutes yet (needs ~200)"
                      }
                    >
                      {xgi90(p) != null ? fmt(xgi90(p), 2) : "–"}
                    </td>
                    <td className="num hide-sm">{sh90(p) != null ? fmt(sh90(p), 1) : "–"}</td>
                    <td className="num hide-sm">{p.avgRating ? fmt(p.avgRating, 1) : "–"}</td>
                    <td className="num">
                      {sp != null ? `${Math.round(sp * 100)}%` : "–"}
                      {conf === "start" && (
                        <span className="ml-1 text-[var(--good)]" title="named in the confirmed starting XI">
                          ✓
                        </span>
                      )}
                      {conf === "bench" && (
                        <span className="ml-1 text-[var(--muted)]" title="confirmed on the bench">
                          ⑂
                        </span>
                      )}
                      {disagree >= 0.4 && (
                        <span
                          className="ml-1 text-[var(--warn)]"
                          title="start-probability sources disagree — rotation / fitness risk"
                        >
                          ⚠
                        </span>
                      )}
                    </td>
                    <td className="num font-semibold">{fmt(p.xpts)}</td>
                    <td className="num hide-sm">{fmt(p.xptsCaptain)}</td>
                    <td className="num">{fmt(p.value, 2)}</td>
                    <td>{owned.has(p.playerId) ? <span className="text-[var(--muted)]">owned</span> : ""}</td>
                  </tr>
              );
            })}
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={14} className="text-center text-[var(--muted)]">
                  No players — has the ingestion job run and produced projections?
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Legend
        items={[
          ["L5 G+A", "goals + assists over the last 5 matches (all competitions) / matches counted"],
          ["xGI90 / Sh90", "expected goal involvements (non-penalty xG + xA) and shots per 90 this DOMESTIC-LEAGUE season (Sofascore, all leagues) — a competition-scoped season rate, the underlying signal behind output. Shown once a player has ~180 league minutes. Hover xGI90 for the npxG/xA split."],
          ["Rtg", "average match rating over those games (Sofascore, ~10 scale)"],
          ["Start%", "estimated chance of starting"],
          ["✓ / ⑂ (next to Start%)", "named in the confirmed starting XI / confirmed on the bench (official lineup, ~1h before kick-off)"],
          ["⚠ (next to Start%)", "our start-probability sources disagree (recent lineups vs season minutes vs price) — treat as a rotation or fitness question"],
          ["xPts / xPts(C)", "expected points, and if captained — the model already folds season xG (xGI90) into this, so a strong xGI with a modest xPts usually means minutes/rotation risk, not an undervaluation"],
          ["Value", "xPts per €m"],
          ["DIFF", "low ownership + high projection — a rank-gaining differential"],
          ["📈 / 📉", "price likely to rise / fall from transfer traffic"],
          ["🔥", "in hot scoring form"],
          ["PK / PK² / FK / CK", "penalty / backup-penalty / free-kick / corner duty — extra points upside"],
          ["→FWD", "playing further forward than UEFA lists — leverage"],
          ["transferred?", "now at another club — excluded from the optimizer"],
        ]}
      />
    </div>
  );
}
