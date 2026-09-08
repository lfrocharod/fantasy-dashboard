"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import { FDR_BG_MAP, clubFixtures, loadBoard, type FplPlayer } from "../lib";

type View = "att" | "def" | "blend";
const LABEL: Record<View, string> = {
  att: "For attackers",
  def: "For defenders / GK",
  blend: "Blended",
};

export default function FplFixturesPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [view, setView] = useState<View>("att");

  useEffect(() => {
    loadBoard().then((d) => setPlayers(d.players));
  }, []);

  const clubs = useMemo(() => clubFixtures(players), [players]);
  const gws = clubs[0]?.cells.map((c) => c.gw) ?? [];
  const pick = useMemo(
    () =>
      (c: { fdr: number; fdrAtt: number; fdrDef: number }) =>
        view === "att" ? c.fdrAtt : view === "def" ? c.fdrDef : c.fdr,
    [view],
  );

  const sorted = useMemo(() => {
    const avg = (cells: { fdr: number; fdrAtt: number; fdrDef: number }[]) => {
      const r = cells.filter((c) => pick(c));
      return r.length ? r.reduce((a, c) => a + pick(c), 0) / r.length : 3;
    };
    return [...clubs].sort((a, b) => avg(a.cells) - avg(b.cells) || a.team.localeCompare(b.team));
  }, [clubs, pick]);

  if (!clubs.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Run <code>./draft.sh --sport fpl --sync</code> first.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Fixture ticker</h1>
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
      <p className="text-sm text-[var(--muted)]">
        {view === "att"
          ? "How hard it is to get goals / assists — the opponent's defensive solidity."
          : view === "def"
            ? "How hard it is to keep a clean sheet — the opponent's attacking threat."
            : "A 50/50 blend."}{" "}
        Every PL club, next {gws.length} GWs, easiest run first.
      </p>
      <div className="card table-wrap">
        <table className="dtable text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-[var(--surface)]">Club</th>
              {gws.map((g) => (
                <th key={g} className="num">
                  GW{g}
                </th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => {
              const rated = c.cells.filter((x) => pick(x));
              const avg = rated.length ? rated.reduce((a, x) => a + pick(x), 0) / rated.length : 3;
              return (
                <tr key={c.team}>
                  <td className="sticky left-0 bg-[var(--surface)] font-medium">{c.team}</td>
                  {c.cells.map((cell) => {
                    const d = pick(cell);
                    return (
                      <td
                        key={cell.gw}
                        className="num"
                        style={{ background: d ? FDR_BG_MAP[d] : undefined }}
                        title={d ? `${LABEL[view].toLowerCase()} ${d}/5` : ""}
                      >
                        {cell.opp || "–"}
                        <span className="ml-1 text-[9px] text-[var(--muted)]">
                          {cell.home === null ? "" : cell.home ? "H" : "A"}
                        </span>
                      </td>
                    );
                  })}
                  <td className="num font-semibold">{fmt(avg, 1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["For attackers", "opponent's defensive strength — green = leaky, target this club's attackers"],
          ["For defenders / GK", "opponent's attacking threat — green = low, clean sheets likely"],
          ["Green (1–2) / Grey (3) / Red (4–5)", "easy / neutral / tough"],
          ["H / A", "home / away"],
          ["Avg", "mean over the shown gameweeks for the selected view"],
        ]}
      />
    </div>
  );
}
