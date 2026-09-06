"use client";

import { useEffect, useMemo, useState } from "react";
import { PosBadge, StatusDot } from "@/components/ui";
import { fmt } from "@/lib/format";
import { POSITIONS, type Position } from "@/lib/ucl/formation";
import type { PlayerRow } from "@/lib/ucl/queries";

type SortKey = "xpts" | "value" | "price" | "selectedPct" | "uefaForm";

export default function PlayersPage() {
  const [players, setPlayers] = useState<PlayerRow[]>([]);
  const [ownedIds, setOwnedIds] = useState<number[]>([]);
  const [matchday, setMatchday] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const [position, setPosition] = useState<Position | "">("");
  const [maxPrice, setMaxPrice] = useState("");
  const [search, setSearch] = useState("");
  const [hideOwned, setHideOwned] = useState(false);
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
    return [...list].sort((a, b) => (Number(b[sort] ?? 0) - Number(a[sort] ?? 0)));
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
            <option value="price">Price</option>
            <option value="selectedPct">Ownership</option>
            <option value="uefaForm">UEFA form</option>
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

      <div className="card overflow-x-auto">
        <table className="grid">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th>Team</th>
              <th className="num">Price</th>
              <th className="num">Own%</th>
              <th className="num">Form</th>
              <th className="num">P(start)</th>
              <th className="num">xPts</th>
              <th className="num">xPts(C)</th>
              <th className="num">Value</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.playerId}>
                <td>
                  <PosBadge position={p.position} />
                </td>
                <td>
                  {p.name} <StatusDot code={p.statusCode} detail={p.statusDetail} />
                </td>
                <td>{p.teamName}</td>
                <td className="num">{fmt(p.price)}</td>
                <td className="num">{fmt(p.selectedPct, 0)}</td>
                <td className="num">{fmt(p.uefaForm)}</td>
                <td className="num">{p.pStart != null ? `${Math.round(p.pStart * 100)}%` : "–"}</td>
                <td className="num font-semibold">{fmt(p.xpts)}</td>
                <td className="num">{fmt(p.xptsCaptain)}</td>
                <td className="num">{fmt(p.value, 2)}</td>
                <td>{owned.has(p.playerId) ? <span className="text-[var(--muted)]">owned</span> : ""}</td>
              </tr>
            ))}
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={11} className="text-center text-[var(--muted)]">
                  No players — has the ingestion job run and produced projections?
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
