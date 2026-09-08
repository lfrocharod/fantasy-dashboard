"use client";

import { useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import type { TickerRow } from "@/lib/ucl/queries";

const DIFF_BG: Record<number, string> = {
  1: "rgba(34,197,94,0.32)",
  2: "rgba(132,204,22,0.24)",
  3: "rgba(148,163,184,0.20)",
  4: "rgba(249,115,22,0.26)",
  5: "rgba(239,68,68,0.34)",
};

type View = "att" | "def" | "blend";
const LABEL: Record<View, string> = {
  att: "For attackers",
  def: "For defenders / GK",
  blend: "Blended",
};

export function FixtureGrid({ rows, mds }: { rows: TickerRow[]; mds: number[] }) {
  const [view, setView] = useState<View>("att");
  const pick = useMemo(
    () =>
      (c: { difficulty: number; attDifficulty: number; defDifficulty: number }) =>
        view === "att" ? c.attDifficulty : view === "def" ? c.defDifficulty : c.difficulty,
    [view],
  );

  const sorted = useMemo(() => {
    const avg = (r: TickerRow) =>
      r.cells.length ? r.cells.reduce((s, c) => s + pick(c), 0) / r.cells.length : 0;
    return [...rows].sort((a, b) => avg(a) - avg(b) || a.team.localeCompare(b.team));
  }, [rows, pick]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-[var(--muted)]">
          {view === "att"
            ? "How hard it is to get goals / assists — driven by the opponent's defensive solidity."
            : view === "def"
              ? "How hard it is to keep a clean sheet — driven by the opponent's attacking threat."
              : "A 50/50 blend of both sides."}{" "}
          Sorted easiest run first.
        </p>
        <div className="ml-auto flex gap-1 text-xs">
          {(["att", "def", "blend"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded px-2 py-1 ${view === v ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
            >
              {LABEL[v]}
            </button>
          ))}
        </div>
      </div>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Team</th>
              {mds.map((m) => (
                <th key={m} className="num">
                  MD{m}
                </th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const avg = r.cells.length
                ? r.cells.reduce((s, c) => s + pick(c), 0) / r.cells.length
                : 0;
              return (
                <tr key={r.teamId}>
                  <td className="whitespace-nowrap font-medium">{r.team}</td>
                  {mds.map((m) => {
                    const c = r.cells.find((x) => x.matchday === m);
                    if (!c) {
                      return (
                        <td key={m} className="num text-[var(--muted)]">
                          –
                        </td>
                      );
                    }
                    const d = pick(c);
                    return (
                      <td
                        key={m}
                        className="num"
                        style={{ background: DIFF_BG[d] }}
                        title={`${c.home ? "vs" : "@"} ${c.opp} — ${LABEL[view].toLowerCase()} ${d}/5`}
                      >
                        <span className="font-semibold">
                          {c.oppCode || c.opp.slice(0, 3).toUpperCase()}
                        </span>
                        <span className="ml-1 text-[10px] text-[var(--muted)]">{c.home ? "H" : "A"}</span>
                      </td>
                    );
                  })}
                  <td className="num font-semibold">{avg.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Legend
        items={[
          ["For attackers", "opponent's defensive strength — green = leaky, target their forwards / captaincy"],
          ["For defenders / GK", "opponent's attacking threat — green = low, clean sheets likely, buy a defender"],
          ["Green (1–2) / Grey (3) / Red (4–5)", "easy / neutral / tough"],
          ["H / A", "home or away"],
          ["Avg", "mean over the shown matchdays for the selected view"],
        ]}
      />
    </div>
  );
}
