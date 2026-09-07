"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import { FDR_BG_MAP, clubFixtures, loadBoard, type FplPlayer } from "../lib";

export default function FplFixturesPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);

  useEffect(() => {
    loadBoard().then((d) => setPlayers(d.players));
  }, []);

  const clubs = useMemo(() => clubFixtures(players), [players]);
  const gws = clubs[0]?.cells.map((c) => c.gw) ?? [];

  if (!clubs.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Run <code>./draft.sh --sport fpl --sync</code> first.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Fixture ticker</h1>
      <p className="text-sm text-[var(--muted)]">
        Every Premier League club, next {gws.length} gameweeks. Easiest run first — good windows to
        target that club&apos;s attackers (green) or bring in a defender.
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
            {clubs.map((c) => (
              <tr key={c.team}>
                <td className="sticky left-0 bg-[var(--surface)] font-medium">{c.team}</td>
                {c.cells.map((cell) => (
                  <td
                    key={cell.gw}
                    className="num"
                    style={{ background: cell.fdr ? FDR_BG_MAP[cell.fdr] : undefined }}
                    title={cell.fdr ? `difficulty ${cell.fdr}/5` : ""}
                  >
                    {cell.opp || "–"}
                    <span className="ml-1 text-[9px] text-[var(--muted)]">
                      {cell.home === null ? "" : cell.home ? "H" : "A"}
                    </span>
                  </td>
                ))}
                <td className="num font-semibold">{fmt(c.avgFdr, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["Green (1–2)", "easy fixture — favour this club's attackers, buy a defender"],
          ["Grey (3)", "neutral"],
          ["Orange/Red (4–5)", "tough — fade attackers, clean sheets unlikely"],
          ["H / A", "home / away"],
          ["Avg", "mean difficulty over the shown gameweeks"],
        ]}
      />
    </div>
  );
}
