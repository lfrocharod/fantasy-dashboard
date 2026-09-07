"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  POS_COLOR,
  groupTeams,
  loadNfl,
  optimalLineup,
  startSitCall,
  weekPoints,
  type NflPlayer,
} from "./lib";

interface Match {
  week: number;
  home: number;
  away: number;
  home_name: string;
  away_name: string;
}

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}
function InjTag({ s }: { s: string }) {
  if (s === "ACTIVE") return null;
  const short = { QUESTIONABLE: "Q", DOUBTFUL: "D", OUT: "O", IR: "IR", SUSPENSION: "SUS" }[s] ?? s[0];
  return <span className="ml-1 text-[10px] font-semibold text-[var(--bad)]">{short}</span>;
}
function Opp({ opp, fdr }: { opp: string; fdr: number }) {
  return (
    <span
      className="rounded px-1 text-xs"
      style={fdr ? { background: FDR_BG[fdr] } : undefined}
      title={fdr ? `matchup ${fdr}/5` : ""}
    >
      {opp || "—"}
    </span>
  );
}

// crude win prob from projected margin (NFL weekly stdev ~ 28)
function winProb(margin: number): number {
  return Math.round(100 / (1 + Math.exp(-margin / 16)));
}

export default function NflLineupPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const week = config?.nflWeek ?? 1;
  const slots = useMemo(
    () => config?.nflSlots ?? { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 },
    [config],
  );
  const myRoster = useMemo(() => {
    const ids = new Set(config?.nflMyRoster ?? []);
    return players.filter((p) => ids.has(p.extId));
  }, [players, config]);

  const teams = useMemo(() => groupTeams(players, config?.myTeamId ?? null), [players, config]);
  const schedule = (config?.schedule ?? []) as Match[];
  const myMatch = schedule.find((m) => m.week === week && (m.home === config?.myTeamId || m.away === config?.myTeamId));
  const oppId = myMatch ? (myMatch.home === config?.myTeamId ? myMatch.away : myMatch.home) : null;
  const oppTeam = teams.find((t) => t.teamId === oppId);

  const mine = useMemo(() => optimalLineup(myRoster, slots, 0), [myRoster, slots]);
  const theirs = useMemo(
    () => (oppTeam ? optimalLineup(oppTeam.players, slots, 0) : null),
    [oppTeam, slots],
  );
  const starterIds = useMemo(
    () => new Set(mine.starters.map((s) => s.p?.extId).filter(Boolean) as string[]),
    [mine],
  );

  if (myRoster.length === 0) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        No roster yet — set your ESPN league id + cookies in the Draft board&apos;s Setup, then run{" "}
        <code>./draft.sh --sport nfl --sync</code>.
      </p>
    );
  }

  const margin = theirs ? mine.total - theirs.total : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Week {week} lineup</h1>
        <span className="text-sm text-[var(--muted)]">
          projected <b>{fmt(mine.total, 0)}</b>
          {theirs && (
            <>
              {" "}vs {oppTeam?.name} <b>{fmt(theirs.total, 0)}</b> —{" "}
              <span style={{ color: margin >= 0 ? "var(--good)" : "var(--bad)" }}>
                {winProb(margin)}% win
              </span>
            </>
          )}
        </span>
      </div>

      {/* ---- OPTIMAL LINEUP ---- */}
      <section className="space-y-2">
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Slot</th>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num">Proj</th>
              </tr>
            </thead>
            <tbody>
              {mine.starters.map((s, i) => (
                <tr key={i}>
                  <td className="text-xs text-[var(--muted)]">{s.slot}</td>
                  <td className="font-medium">
                    {s.p ? (
                      <>
                        <Tag pos={s.p.pos} /> {s.p.name}{" "}
                        <span className="text-[var(--muted)]">{s.p.team}</span>
                        <InjTag s={s.p.injury} />
                      </>
                    ) : (
                      <span className="text-[var(--bad)]">— empty —</span>
                    )}
                  </td>
                  <td>{s.p && <Opp opp={s.p.matchups[0]?.opp ?? ""} fdr={s.p.matchups[0]?.fdr ?? 0} />}</td>
                  <td className="num font-semibold">{s.p ? fmt(weekPoints(s.p, 0)) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- START / SIT ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">START / SIT — every rostered player</h2>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num">Wk proj</th>
                <th className="num hide-sm">ROS</th>
                <th>Call</th>
              </tr>
            </thead>
            <tbody>
              {[...myRoster]
                .sort((a, b) => weekPoints(b, 0) - weekPoints(a, 0))
                .map((p) => {
                  const call = startSitCall(p, starterIds);
                  return (
                    <tr key={p.extId}>
                      <td className="font-medium">
                        <Tag pos={p.pos} /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                        <InjTag s={p.injury} />
                        {p.onBye && <span className="ml-1 text-[10px] text-[var(--warn)]">BYE</span>}
                      </td>
                      <td>
                        <Opp opp={p.matchups[0]?.opp ?? ""} fdr={p.matchups[0]?.fdr ?? 0} />
                      </td>
                      <td className="num font-semibold">{fmt(weekPoints(p, 0))}</td>
                      <td className="num hide-sm">{fmt(p.rosProj, 0)}</td>
                      <td
                        className="text-xs font-semibold"
                        style={{
                          color:
                            call === "START"
                              ? "var(--good)"
                              : call === "FLEX?"
                                ? "var(--warn)"
                                : "var(--muted)",
                        }}
                      >
                        {call}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---- OPPONENT ---- */}
      {theirs && oppTeam && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            {oppTeam.name} — their projected starters
          </h2>
          <p className="text-sm text-[var(--muted)]">
            You&apos;re {margin >= 4 ? "a clear favourite — play your safe floor" : margin <= -4 ? "the underdog — play ceiling / make a differential move" : "in a coin-flip — every start/sit call matters"}.
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Player</th>
                  <th>Matchup</th>
                  <th className="num">Proj</th>
                </tr>
              </thead>
              <tbody>
                {theirs.starters.map((s, i) => (
                  <tr key={i}>
                    <td className="text-xs text-[var(--muted)]">{s.slot}</td>
                    <td>
                      {s.p ? (
                        <>
                          <Tag pos={s.p.pos} /> {s.p.name}{" "}
                          <span className="text-[var(--muted)]">{s.p.team}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{s.p && <Opp opp={s.p.matchups[0]?.opp ?? ""} fdr={s.p.matchups[0]?.fdr ?? 0} />}</td>
                    <td className="num">{s.p ? fmt(weekPoints(s.p, 0)) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Proj", "projected PPR points this week (ESPN + FantasyPros blend)"],
          ["ROS", "rest-of-season projected points"],
          ["Call", "START = in your optimal XI · FLEX? = viable flex swing · SIT = leave it"],
          ["Win %", "from the projected margin vs this week's opponent (weekly stdev ~16)"],
        ]}
      />
    </div>
  );
}
