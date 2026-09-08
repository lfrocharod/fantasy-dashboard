"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  POS_COLOR,
  groupTeams,
  loadNfl,
  simPlayoffs,
  type NflPlayer,
  type SchedRow,
  type Standing,
} from "../lib";

function Tag({ pos }: { pos: string }) {
  return (
    <span className="rounded px-1 text-[10px] font-bold text-white" style={{ background: POS_COLOR[pos] ?? "#6b7280" }}>
      {pos}
    </span>
  );
}
const FDR_C: Record<number, string> = {
  1: "#1a7f37", 2: "#4b9e2f", 3: "var(--muted)", 4: "#d1741f", 5: "#cf222e",
};

export default function NflStandingsPage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const week = config?.nflWeek ?? 1;
  const regWeeks = config?.nflPlayoffWeeks?.length ? config.nflPlayoffWeeks[0] - 1 : 15;
  const playoffTeams = config?.nflPlayoffTeams ?? 4;
  const espnRule = config?.nflSeedingRule ?? "H2H_RECORD";

  // ESPN reports the seeding rule, but let the user override it if they know
  // their league better (persisted locally).
  const [override, setOverride] = useState<"" | "TOTAL_POINTS_SCORED" | "H2H_RECORD">("");
  useEffect(() => {
    try {
      const v = localStorage.getItem("nfl_seeding_override");
      if (v === "TOTAL_POINTS_SCORED" || v === "H2H_RECORD") setOverride(v);
    } catch {
      /* ignore */
    }
  }, []);
  const setSeeding = (v: "" | "TOTAL_POINTS_SCORED" | "H2H_RECORD") => {
    setOverride(v);
    try {
      if (v) localStorage.setItem("nfl_seeding_override", v);
      else localStorage.removeItem("nfl_seeding_override");
    } catch {
      /* ignore */
    }
  };
  const rule = override || espnRule;
  const byPoints = rule === "TOTAL_POINTS_SCORED";
  const standings = useMemo(() => (config?.standings ?? []) as Standing[], [config]);

  const odds = useMemo(() => {
    const managers = groupTeams(players, config?.myTeamId ?? null);
    const schedule = (config?.schedule ?? []) as SchedRow[];
    const slots = config?.nflSlots ?? { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 };
    if (!managers.length || !schedule.length) return [];
    return simPlayoffs(
      managers, standings, schedule, slots, week, regWeeks, playoffTeams, config?.myTeamId ?? null, rule,
    );
  }, [players, config, standings, week, regWeeks, playoffTeams, rule]);
  const oddsByTeam = useMemo(() => new Map(odds.map((o) => [o.teamId, o])), [odds]);

  const playoffWeeks = useMemo(
    () => (config?.nflPlayoffWeeks?.length ? config.nflPlayoffWeeks : [16, 17]) as number[],
    [config],
  );
  const roster = useMemo(() => {
    const ids = new Set(config?.nflMyRoster ?? []);
    return players.filter((p) => ids.has(p.extId)).sort((a, b) => b.rosProj - a.rosProj);
  }, [players, config]);
  const byes = useMemo(() => {
    const out: { week: number; players: NflPlayer[] }[] = [];
    for (let w = week; w <= week + 8 && w <= regWeeks; w++) {
      const off = roster.filter(
        (p) => p.bye === w && ["QB", "RB", "WR", "TE", "K", "DST"].includes(p.pos),
      );
      if (off.length) out.push({ week: w, players: off });
    }
    return out;
  }, [roster, week, regWeeks]);
  const playoffSos = useMemo(
    () =>
      roster
        .map((p) => {
          const pw = p.matchups.filter((m) => playoffWeeks.includes(m.week) && m.fdr);
          const src = pw.length ? pw : p.matchups.filter((m) => m.fdr);
          const avg = src.length ? src.reduce((a, m) => a + m.fdr, 0) / src.length : 3;
          return { p, avg, pw: p.matchups.filter((m) => playoffWeeks.includes(m.week)) };
        })
        .sort((a, b) => a.avg - b.avg),
    [roster, playoffWeeks],
  );

  if (!standings.length) {
    return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync to pull standings.</p>;
  }

  const table = [...standings].sort((a, b) =>
    byPoints
      ? b.pf - a.pf || b.wins - a.wins
      : b.wins - a.wins || a.losses - b.losses || b.pf - a.pf,
  );

  // pace to the playoff cut-line (total-points leagues only)
  const pace = (() => {
    if (!byPoints) return null;
    const meS = standings.find((s) => s.team_id === config?.myTeamId);
    const meO = oddsByTeam.get(config?.myTeamId ?? -1);
    if (!meS) return null;
    const played = Math.max(1, week - 1);
    const weeksLeft = Math.max(1, regWeeks - week + 1);
    const myPace = meS.pf / played;
    const curCut = table[playoffTeams - 1]?.pf ?? 0;
    const curRank = table.findIndex((s) => s.team_id === config?.myTeamId) + 1;
    const byProjPf = [...odds].sort((a, b) => b.projPf - a.projPf);
    const projCut = byProjPf[playoffTeams - 1]?.projPf ?? 0;
    const myProjPf = meO?.projPf ?? meS.pf + myPace * weeksLeft;
    const projMargin = myProjPf - projCut; // + = projected in, − = projected out
    // extra points/week needed to lift your projection to the cut line
    const perWeekGap = projMargin >= 0 ? 0 : -projMargin / weeksLeft;
    return {
      curRank, curGap: meS.pf - curCut, played, weeksLeft, myPace,
      projMargin, perWeekGap, playoffPct: meO?.playoffPct ?? null,
    };
  })();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">League</h1>
        <div className="ml-auto flex items-center gap-1 text-xs">
          <span className="text-[var(--muted)]">Playoff seeding:</span>
          {(
            [
              ["TOTAL_POINTS_SCORED", "Total points"],
              ["H2H_RECORD", "Wins (W/L)"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              onClick={() => setSeeding(v === espnRule && !override ? "" : v)}
              className={`rounded px-2 py-1 ${rule === v ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
            >
              {label}
            </button>
          ))}
          <span className="text-[var(--muted)]">
            {override ? "(your setting)" : "(most leagues seed by W/L; total points is the tie-break)"}
          </span>
        </div>
      </div>

      {byPoints && (
        <div className="card border-l-2 border-[var(--accent)] p-3 text-sm">
          <b>Playoffs are seeded by total points scored, not record.</b> The top {playoffTeams} teams
          by season points make it — your weekly W/L is cosmetic. So{" "}
          <b>play your highest‑ceiling lineup every week</b>, never the safe floor to “win” a matchup.
        </div>
      )}

      {pace && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">YOUR PACE TO THE CUT-LINE</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">Right now</div>
              <div className="text-lg font-semibold">#{pace.curRank || "–"}</div>
              <div className="text-xs" style={{ color: pace.curGap >= 0 ? "var(--good)" : "var(--bad)" }}>
                {pace.curGap >= 0 ? "+" : ""}
                {fmt(pace.curGap, 0)} vs {playoffTeams}th
              </div>
            </div>
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">Your scoring pace</div>
              <div className="text-lg font-semibold">{fmt(pace.myPace, 1)}</div>
              <div className="text-xs text-[var(--muted)]">pts / week ({pace.played}g)</div>
            </div>
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">Projected finish</div>
              <div
                className="text-lg font-semibold"
                style={{ color: pace.projMargin >= 0 ? "var(--good)" : "var(--bad)" }}
              >
                {pace.projMargin >= 0 ? "IN" : "OUT"} {pace.projMargin >= 0 ? "+" : ""}
                {fmt(pace.projMargin, 0)}
              </div>
              <div className="text-xs text-[var(--muted)]">pts vs the cut line</div>
            </div>
            <div className="card p-3">
              <div className="text-xs text-[var(--muted)]">To climb in</div>
              <div className="text-lg font-semibold">
                {pace.perWeekGap <= 0 ? "—" : `+${fmt(pace.perWeekGap, 1)}`}
              </div>
              <div className="text-xs text-[var(--muted)]">
                {pace.perWeekGap <= 0 ? "on pace, hold it" : `pts/week over ${pace.weeksLeft}w`}
              </div>
            </div>
          </div>
          <p className="text-xs text-[var(--muted)]">
            {pace.projMargin >= 0
              ? `Projected to finish ${fmt(pace.projMargin, 0)} points inside the top ${playoffTeams}. Keep starting your ceiling — don't get cute.`
              : `You're projected ${fmt(-pace.projMargin, 0)} short. You need about ${fmt(pace.myPace + pace.perWeekGap, 1)} pts/week (${fmt(pace.perWeekGap, 1)} above your current pace) the rest of the way — that's the bar for every start/sit and waiver call.`}
          </p>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">
          STANDINGS {byPoints ? "· by season points" : "· by record"}
        </h2>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Team</th>
                <th className="num">{byPoints ? "PF" : "W-L-T"}</th>
                <th className="num hide-sm">{byPoints ? "W-L-T" : "PF"}</th>
                <th className="num">{byPoints ? "Proj PF" : "Proj wins"}</th>
                <th className="num">Playoffs</th>
                <th className="num hide-sm">Top-2</th>
              </tr>
            </thead>
            <tbody>
              {table.map((s, i) => {
                const o = oddsByTeam.get(s.team_id);
                const mine = s.team_id === config?.myTeamId;
                const inLine = i < playoffTeams;
                return (
                  <tr key={s.team_id} style={mine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                    <td className="num" style={inLine ? { color: "var(--good)", fontWeight: 600 } : undefined}>
                      {i + 1}
                    </td>
                    <td className="font-medium">
                      {s.name} {mine && <span className="text-xs text-[var(--accent)]">(you)</span>}
                    </td>
                    <td className="num font-semibold">
                      {byPoints ? fmt(s.pf, 0) : `${s.wins}-${s.losses}${s.ties ? `-${s.ties}` : ""}`}
                    </td>
                    <td className="num hide-sm text-[var(--muted)]">
                      {byPoints ? `${s.wins}-${s.losses}${s.ties ? `-${s.ties}` : ""}` : fmt(s.pf, 0)}
                    </td>
                    <td className="num">
                      {o ? (byPoints ? fmt(o.projPf, 0) : fmt(o.projWins, 1)) : "–"}
                    </td>
                    <td
                      className="num font-semibold"
                      style={{
                        color: o
                          ? o.playoffPct >= 60
                            ? "var(--good)"
                            : o.playoffPct <= 25
                              ? "var(--bad)"
                              : undefined
                          : undefined,
                      }}
                    >
                      {o ? `${fmt(o.playoffPct, 0)}%` : "–"}
                    </td>
                    <td className="num hide-sm">{o ? `${fmt(o.byePct, 0)}%` : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          Playoff odds from 3,000 simulations of the remaining regular season — each matchup is two
          Normal(projected score, 24) draws; seeded by{" "}
          {byPoints ? "total points scored" : "wins, then points-for"}. Green rank = currently in the
          top {playoffTeams}.
        </p>
      </section>

      {byes.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">YOUR BYE-WEEK GAPS</h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">Week</th>
                  <th>Off (line up a streamer)</th>
                </tr>
              </thead>
              <tbody>
                {byes.map((b) => (
                  <tr key={b.week}>
                    <td className="num font-semibold">{b.week}</td>
                    <td>
                      {b.players.map((p) => (
                        <span key={p.extId} className="mr-2">
                          <Tag pos={p.pos} /> {p.name}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {roster.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">
            PLAYOFF SCHEDULE (weeks {playoffWeeks.join("–")}) — easiest run first
          </h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">Avg difficulty</th>
                  <th>Playoff opponents</th>
                </tr>
              </thead>
              <tbody>
                {playoffSos.map(({ p, avg, pw }) => (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      <Tag pos={p.pos} /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td className="num font-semibold" style={{ color: FDR_C[Math.round(avg)] }}>
                      {fmt(avg, 1)}
                    </td>
                    <td className="text-xs">
                      {pw.length
                        ? pw.map((m) => `W${m.week} ${m.opp}`).join(", ")
                        : "schedule not out yet — estimated from nearer matchups"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--muted)]">
            If the Week {playoffWeeks[0]}–{playoffWeeks.at(-1)} schedule isn&apos;t published yet, the
            difficulty is estimated from each player&apos;s nearer-term matchups — treat it as
            directional. Target trade acquisitions with a green playoff run.
          </p>
        </section>
      )}

      <Legend
        items={[
          ["PF", "points for — total scored this season"],
          [byPoints ? "Proj PF" : "Proj wins", byPoints ? "mean projected final season points" : "mean final win total across the simulations"],
          ["Playoffs / Top-2", "share of sims finishing in a playoff seed / a top-2 (bye) seed"],
          ["Bye gaps", "weeks you'll be short a starter — line up a streamer"],
          ["Playoff avg", "mean matchup difficulty across your fantasy playoff weeks (1 green … 5 red)"],
        ]}
      />
    </div>
  );
}
