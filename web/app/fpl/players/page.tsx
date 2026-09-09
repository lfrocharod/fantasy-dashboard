"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend, Range } from "@/components/ui";
import { fmt } from "@/lib/format";
import {
  POS,
  loadBoard,
  oppTag,
  sortPlayers,
  type FplPlayer,
  type PosFilter,
  type SortKey,
} from "../lib";

const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};
const STATUS_LABEL: Record<string, string> = {
  d: "doubt", i: "injured", s: "susp", u: "unavail", n: "out",
};

export default function FplPlayersPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [mineIds, setMineIds] = useState<Set<string>>(new Set());
  const [pos, setPos] = useState<PosFilter>("ALL");
  const [sort, setSort] = useState<SortKey>("horizon");
  const [search, setSearch] = useState("");
  const [availableOnly, setAvailableOnly] = useState(true);

  useEffect(() => {
    loadBoard().then((d) => {
      setPlayers(d.players);
      setMineIds(new Set(d.config?.mySquad ?? []));
    });
  }, []);

  const gwCols = useMemo(() => (players[0]?.gws ?? []).map((g) => g.gw), [players]);

  const list = useMemo(() => {
    let l = players;
    if (pos !== "ALL") l = l.filter((p) => p.pos === pos);
    if (availableOnly) l = l.filter((p) => p.available);
    if (search.trim()) {
      const q = search.toLowerCase();
      l = l.filter((p) => p.name.toLowerCase().includes(q));
    }
    return sortPlayers(l, sort).slice(0, 250);
  }, [players, pos, availableOnly, search, sort]);

  if (!players.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Run <code>./draft.sh --sport fpl --sync</code> first.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Players &amp; free-agent finder</h1>

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
          free agents only
        </label>
        <select
          className="input ml-auto text-xs"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
        >
          <option value="horizon">Sort: next 6 GW</option>
          <option value="proj">Sort: next GW</option>
          <option value="vbd">Sort: value over replacement</option>
          <option value="csProb">Sort: clean-sheet %</option>
          <option value="form">Sort: form</option>
          <option value="totalPoints">Sort: total points</option>
          <option value="xgi90">Sort: xGI/90</option>
          <option value="ict90">Sort: ICT/90</option>
          <option value="thr90">Sort: Threat/90</option>
          <option value="cre90">Sort: Creativity/90</option>
        </select>
        <input
          className="input text-xs"
          placeholder="search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="text-xs text-[var(--muted)]">{list.length} shown</span>
      </div>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th className="hide-sm">Team</th>
              <th>Opp</th>
              <th className="num">xPts</th>
              <th className="num hide-sm">Range</th>
              <th className="num" title={`sum of projected points over the next ${gwCols.length} gameweeks`}>
                xPts·{gwCols.length}
              </th>
              <th className="num hide-sm">Start%</th>
              <th className="num hide-sm">CS%</th>
              <th className="num hide-sm">xGI90</th>
              <th className="num hide-sm">ICT90</th>
              <th className="num hide-sm" title="expected goals conceded per 90 while on the pitch — lower is better for DEF/GK value">
                xGC90
              </th>
              <th className="num hide-sm">Form</th>
              <th>Owner</th>
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
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
                  {oppTag(p) && (
                    <span
                      className="ml-1 text-[10px] font-semibold"
                      style={{ color: oppTag(p) === "value" ? "var(--good)" : "var(--warn)" }}
                      title="season underlying stats (xGI/90, xGC/90) vs current output"
                    >
                      {oppTag(p)}
                    </span>
                  )}
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
                    <span className="ml-1 text-[var(--warn)]" title={`${p.ycToBan} booking from a ban`}>
                      ⚑
                    </span>
                  )}
                </td>
                <td className="hide-sm">{p.team}</td>
                <td className="text-xs text-[var(--muted)]">{p.nextOpp}</td>
                <td className="num">{fmt(p.proj)}</td>
                <td className="num hide-sm">
                  <Range lo={p.gws[0]?.lo ?? 0} hi={p.gws[0]?.hi ?? 0} mean={p.proj} digits={1} />
                </td>
                <td className="num font-semibold">{fmt(p.horizon, 0)}</td>
                <td className="num hide-sm">{p.pStart ? `${Math.round(p.pStart * 100)}%` : "–"}</td>
                <td className="num hide-sm">{p.pos === "FWD" ? "–" : Math.round(p.csProb * 100)}</td>
                <td className="num hide-sm">{fmt(p.xgi90, 2)}</td>
                <td
                  className="num hide-sm"
                  title={
                    p.ict90
                      ? `Influence ${fmt(p.inf90, 1)} · Creativity ${fmt(p.cre90, 1)} · Threat ${fmt(p.thr90, 1)} (per 90)`
                      : ""
                  }
                >
                  {p.ict90 ? fmt(p.ict90, 1) : "–"}
                </td>
                <td className="num hide-sm">
                  {p.pos === "FWD" || !p.xgc90 ? "–" : fmt(p.xgc90, 2)}
                </td>
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

      <Legend
        items={[
          ["xPts / xPts·N", "projected draft points — next gameweek, then the sum over the next N shown"],
          ["Range", "~15th–85th percentile next-GW outcome (blank · mean · haul) — wider for boom/bust attackers, tighter for a nailed defender's appearance + DEFCON floor"],
          ["Start%", "modelled chance of starting the next match"],
          ["CS%", "clean-sheet probability (opponent attack vs your team's defence). GKP/DEF worth 4, MID 1"],
          ["xGI90", "expected goal involvements per 90 — non-penalty xG + xA, this Premier League season"],
          ["ICT90", "FPL's Influence-Creativity-Threat index per 90 (hover for the I/C/T split), this Premier League season"],
          ["xGC90", "expected goals conceded per 90 while on the pitch — defensive solidity for GK/DEF/MID value; lower is better. Hidden for forwards."],
          ["P / F / C", "first-choice penalties / free-kicks / corners"],
          ["FA", "free agent in your league; a name = the manager who has them"],
        ]}
      />
    </div>
  );
}
