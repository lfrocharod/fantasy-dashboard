"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import { FDR_BG, loadNfl, nflClubFixtures, type NflPlayer } from "../lib";

export default function NflFixturesPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);

  useEffect(() => {
    loadNfl().then((d) => setPlayers(d.players));
  }, []);

  const clubs = useMemo(() => nflClubFixtures(players), [players]);
  const weeks = clubs[0]?.cells.map((c) => c.week) ?? [];

  if (!clubs.length) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Fixture ticker</h1>
      <p className="text-sm text-[var(--muted)]">
        Every NFL team, next {weeks.length} weeks — matchup difficulty for that team&apos;s skill
        players (opponent defence vs the run/pass). Easiest run first: target streamers, DST and
        buy-low windows.
      </p>
      <div className="card table-wrap">
        <table className="dtable text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-[var(--surface)]">Team</th>
              {weeks.map((w) => (
                <th key={w} className="num">
                  W{w}
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
                    key={cell.week}
                    className="num"
                    style={{
                      background:
                        cell.opp === "BYE"
                          ? "rgba(148,163,184,0.25)"
                          : cell.fdr
                            ? FDR_BG[cell.fdr]
                            : undefined,
                    }}
                    title={cell.fdr ? `difficulty ${cell.fdr}/5` : ""}
                  >
                    {cell.opp || "–"}
                    {cell.opp && cell.opp !== "BYE" && (
                      <span className="ml-1 text-[9px] text-[var(--muted)]">
                        {cell.home ? "H" : "A"}
                      </span>
                    )}
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
          ["Green (1–2)", "soft matchup — start that team's skill players, stream their DST is risky"],
          ["Red (4–5)", "tough — fade, consider a bye/streamer instead"],
          ["grey BYE", "team is on bye that week"],
          ["Avg", "mean difficulty over the shown weeks"],
        ]}
      />
    </div>
  );
}
