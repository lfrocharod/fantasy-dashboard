"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { FDR_BG, POS_COLOR, loadNfl, nflClubDossiers, type NflPlayer } from "../lib";

export default function NflTeamsPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);

  useEffect(() => {
    loadNfl().then((d) => setPlayers(d.players));
  }, []);

  const dossiers = useMemo(() => nflClubDossiers(players), [players]);

  if (!dossiers.length) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Team watch</h1>
      <p className="text-sm text-[var(--muted)]">
        One card per NFL team, easiest fixture run first: the fantasy-relevant projected starters
        (QB1, RB1-2, WR1-3, TE1), injury designations, bye week, and the next weeks&apos; matchups.
      </p>

      {dossiers.map((d) => (
        <Section
          key={d.team}
          title={d.team}
          right={
            <span className="text-xs text-[var(--muted)]">
              avg matchup {fmt(d.avgFdr, 1)}
              {d.bye ? ` · bye W${d.bye}` : ""}
            </span>
          }
        >
          <div className="card space-y-3 p-3">
            <div className="flex flex-wrap gap-1">
              {d.fixtures.map((c) => (
                <span
                  key={c.week}
                  className="rounded px-2 py-1 text-xs"
                  style={{
                    background:
                      c.opp === "BYE"
                        ? "rgba(148,163,184,0.25)"
                        : c.fdr
                          ? FDR_BG[c.fdr]
                          : undefined,
                  }}
                >
                  W{c.week} {c.opp === "BYE" ? "BYE" : `${c.home ? "v" : "@"} ${c.opp}`}
                </span>
              ))}
            </div>

            <div className="table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Projected starter</th>
                    <th className="num">Start%</th>
                    <th className="num">Wk proj</th>
                    <th className="num">ROS</th>
                    <th className="hide-sm">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.starters.map((p) => (
                    <tr key={p.extId}>
                      <td>
                        <span
                          className="rounded px-1 text-[10px] font-bold text-white"
                          style={{ background: POS_COLOR[p.pos] }}
                        >
                          {p.pos}
                        </span>
                      </td>
                      <td className="font-medium">{p.name}</td>
                      <td className="num">{p.pctStarted ? `${Math.round(p.pctStarted)}%` : "–"}</td>
                      <td className="num font-semibold">{fmt(p.weekProj)}</td>
                      <td className="num">{fmt(p.rosProj, 0)}</td>
                      <td className="hide-sm text-xs text-[var(--muted)]">
                        {p.injury !== "ACTIVE" ? p.injury : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {d.bench.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Next man up: </span>
                {d.bench.map((p) => `${p.name} (${p.pos})`).join(", ")}
              </div>
            )}

            {d.doubts.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Injury report: </span>
                {d.doubts
                  .slice(0, 8)
                  .map((p) => `${p.name} (${p.injury})`)
                  .join(", ")}
              </div>
            )}
          </div>
        </Section>
      ))}

      <Legend
        items={[
          ["Start%", "share of ESPN leagues starting this player — the crowd's read on the depth chart"],
          ["Wk proj / ROS", "projected PPR points this week / rest of season"],
          ["Fixture chip", "difficulty 1 (green) … 5 (red); grey = bye"],
          ["Projected starter", "most-started player at that slot who isn't OUT/IR"],
        ]}
      />
    </div>
  );
}
