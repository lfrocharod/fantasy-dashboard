"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  FDR_BG,
  POS_COLOR,
  groupTeams,
  loadNfl,
  optimalLineup,
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

// crude win prob from projected margin (NFL weekly stdev ~ 28)
function winProb(margin: number): number {
  return Math.round(100 / (1 + Math.exp(-margin / 16)));
}

const POS_SORT = ["QB", "RB", "WR", "TE", "K", "DST"];

export default function NflOverviewPage() {
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
  const myMatch = schedule.find(
    (m) => m.week === week && (m.home === config?.myTeamId || m.away === config?.myTeamId),
  );
  const oppId = myMatch ? (myMatch.home === config?.myTeamId ? myMatch.away : myMatch.home) : null;
  const oppTeam = teams.find((t) => t.teamId === oppId);

  const mine = useMemo(() => optimalLineup(myRoster, slots, 0), [myRoster, slots]);
  const theirs = useMemo(
    () => (oppTeam ? optimalLineup(oppTeam.players, slots, 0) : null),
    [oppTeam, slots],
  );
  const optIds = useMemo(
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
  const changes =
    mine.starters.filter((s) => s.p && (s.p.slot === "BE" || s.p.slot === "IR" || !s.p.slot)).length +
    myRoster.filter((p) => !optIds.has(p.extId) && p.slot && p.slot !== "BE" && p.slot !== "IR").length;

  const injured = myRoster.filter((p) => p.injury !== "ACTIVE" && optIds.has(p.extId));
  const byes = myRoster.filter((p) => p.onBye && optIds.has(p.extId));

  const ordered = [...myRoster].sort(
    (a, b) => POS_SORT.indexOf(a.pos) - POS_SORT.indexOf(b.pos) || weekPoints(b, 0) - weekPoints(a, 0),
  );

  const byPoints = (config?.nflSeedingRule ?? "H2H_RECORD") === "TOTAL_POINTS_SCORED";
  const checks: { ok: boolean; text: string; href?: string }[] = [
    {
      ok: changes === 0,
      text: changes === 0 ? "ESPN lineup matches the optimal one" : `${changes} lineup change(s) recommended`,
      href: "/nfl/optimizer",
    },
    ...(byPoints
      ? [
          {
            ok: true,
            text: "Playoffs seed by total points — start your highest-ceiling lineup, not the safe floor",
          },
        ]
      : []),
    {
      ok: injured.length === 0,
      text: injured.length
        ? `${injured.length} starter(s) carrying an injury tag: ${injured.map((p) => p.name).join(", ")}`
        : "No injury tags on your projected starters",
    },
    {
      ok: byes.length === 0,
      text: byes.length ? `${byes.length} projected starter(s) on BYE — fill the slot` : "No starters on bye this week",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Week {week} overview</h1>
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

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">THIS WEEK — checklist</h2>
        <div className="card divide-y divide-[var(--border)]">
          {checks.map((c, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-2 text-sm">
              <span
                className="rounded px-1.5 py-0.5 text-[10px] font-bold text-white"
                style={{ background: c.ok ? "var(--good)" : "var(--warn)" }}
              >
                {c.ok ? "OK" : "DO"}
              </span>
              <span>{c.text}</span>
              {c.href && !c.ok && (
                <Link href={c.href} className="ml-auto text-xs text-[var(--accent)]">
                  open Optimizer →
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">YOUR ROSTER</h2>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num">Wk proj</th>
                <th className="num hide-sm">ROS</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((p) => {
                const m = p.matchups[0];
                const starting = optIds.has(p.extId);
                return (
                  <tr key={p.extId} style={starting ? undefined : { opacity: 0.55 }}>
                    <td className="font-medium">
                      <Tag pos={p.pos} /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                      <InjTag s={p.injury} />
                      {p.onBye && <span className="ml-1 text-[10px] text-[var(--warn)]">BYE</span>}
                    </td>
                    <td>
                      <span
                        className="rounded px-1 text-xs font-medium"
                        style={m?.fdr ? { background: FDR_BG[m.fdr] } : undefined}
                        title={m?.fdr ? `matchup ${m.fdr}/5` : ""}
                      >
                        {p.onBye ? "BYE" : m?.opp || "—"}
                      </span>
                    </td>
                    <td className="num font-semibold">{fmt(weekPoints(p, 0))}</td>
                    <td className="num hide-sm">{fmt(p.rosProj, 0)}</td>
                    <td className="text-[10px] text-[var(--muted)]">{starting ? "start" : "bench"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <Legend
        items={[
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Wk proj / ROS", "projected PPR points this week / rest of season"],
          ["dimmed row", "not in your optimal lineup this week"],
          ["Win %", "from the projected margin vs this week's opponent"],
        ]}
      />
    </div>
  );
}
