"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { FDR_BG_MAP, clubDossiers, loadBoard, type FplPlayer } from "../lib";

const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};

export default function FplTeamsPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);

  useEffect(() => {
    loadBoard().then((d) => setPlayers(d.players));
  }, []);

  const dossiers = useMemo(() => clubDossiers(players), [players]);

  if (!dossiers.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Run <code>./draft.sh --sport fpl --sync</code> first.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Team watch</h1>
      <p className="text-sm text-[var(--muted)]">
        One card per Premier League club, easiest fixture run first: the probable XI (by modelled
        start-probability), set-piece takers, injury doubts, and the highest-value players. Read it to
        make your own calls.
      </p>

      {dossiers.map((d) => (
        <Section
          key={d.team}
          title={d.team}
          right={<span className="text-xs text-[var(--muted)]">avg FDR {fmt(d.avgFdr, 1)}</span>}
        >
          <div className="card space-y-3 p-3">
            <div className="flex flex-wrap gap-1">
              {d.fixtures.map((c) => (
                <span
                  key={c.gw}
                  className="rounded px-2 py-1 text-xs"
                  style={{ background: c.fdr ? FDR_BG_MAP[c.fdr] : undefined }}
                >
                  GW{c.gw} {c.home === null ? "" : c.home ? "v" : "@"} {c.opp}
                </span>
              ))}
            </div>

            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">SET PIECES</div>
                <div>
                  PK: {d.setPieces.pk.map((p) => p.name).join(", ") || <span className="text-[var(--muted)]">unknown</span>}
                </div>
                {d.setPieces.fk.length > 0 && <div>FK: {d.setPieces.fk.map((p) => p.name).join(", ")}</div>}
                {d.setPieces.ck.length > 0 && <div>CK: {d.setPieces.ck.map((p) => p.name).join(", ")}</div>}
              </div>
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">DOUBTS / OUT</div>
                {d.doubts.length ? (
                  d.doubts.slice(0, 6).map((p) => (
                    <div key={p.extId}>
                      {p.name}{" "}
                      <span className="text-[var(--muted)]">{p.news || p.status}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-[var(--muted)]">none flagged</div>
                )}
              </div>
            </div>

            <div className="table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Probable XI</th>
                    <th className="num">Start%</th>
                    <th className="num">ROS/GW</th>
                    <th className="num hide-sm">Form</th>
                  </tr>
                </thead>
                <tbody>
                  {d.probableXI.map((p) => (
                    <tr key={p.extId}>
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
                        {p.setPiece && (
                          <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">
                            {p.setPiece.replace("PK2", "PK²")}
                          </span>
                        )}
                      </td>
                      <td className="num">{p.pStart ? `${Math.round(p.pStart * 100)}%` : "–"}</td>
                      <td className="num font-semibold">{fmt(p.rosPpg)}</td>
                      <td className="num hide-sm">{fmt(p.form)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {d.bench.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Also in the pool: </span>
                {d.bench
                  .map(
                    (p) =>
                      `${p.name} (${p.pos}${
                        p.pStart ? `, ${Math.round(p.pStart * 100)}%` : ""
                      })`,
                  )
                  .join(", ")}
              </div>
            )}
          </div>
        </Section>
      ))}

      <Legend
        items={[
          ["Start%", "modelled chance of starting the next match"],
          ["ROS/GW", "projected draft points per gameweek, rest of season"],
          ["PK / FK / CK", "penalty / free-kick / corner duty (edit set_piece_roles to correct)"],
        ]}
      />
    </div>
  );
}
