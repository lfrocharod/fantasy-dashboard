import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { FDR_TEXT } from "@/shared/fdr";
import { fmt, signed } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, StatCard, SubHeading } from "@/shared/ui";

type Rule = Api["NflStandingsResponse"]["rule"];
const KEY = "nfl_seeding_override";

// ESPN reports the seeding rule, but you may know your league better — the
// override is a per-browser preference.
function readOverride(): Rule | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "TOTAL_POINTS_SCORED" || v === "H2H_RECORD" ? v : null;
  } catch {
    return null;
  }
}
function writeOverride(v: Rule | null) {
  try {
    if (v) localStorage.setItem(KEY, v);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable — the choice just won't persist */
  }
}

export default function NflStandingsPage() {
  const [override, setOverride] = useState<Rule | null>(readOverride);
  const q = $api.useQuery("get", "/api/nfl/standings", { params: { query: override ? { seeding: override } : {} } }, {
    placeholderData: (prev) => prev,
  });
  const choose = (v: Rule, espnRule: Rule) => {
    const next = v === espnRule && !override ? null : v;
    setOverride(next);
    writeOverride(next);
  };
  return <QueryView query={q}>{(d) => <Standings d={d} override={override} choose={(v) => choose(v, d.espnRule)} />}</QueryView>;
}

function Standings({ d, override, choose }: { d: Api["NflStandingsResponse"]; override: Rule | null; choose: (v: Rule) => void }) {
  if (d.rows.length === 0) return <EmptyState title="No standings yet" hint="The next NFL sync pulls the league table." />;
  const { byPoints, pace } = d;
  const wlt = (s: Api["NflStandingRow"]) => `${s.wins}-${s.losses}${s.ties ? `-${s.ties}` : ""}`;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">League</h1>
        <div className="ml-auto flex flex-wrap items-center gap-1 text-xs">
          <span className="text-[var(--muted)]">Playoff seeding:</span>
          {([["TOTAL_POINTS_SCORED", "Total points"], ["H2H_RECORD", "Wins (W/L)"]] as const).map(([v, label]) => (
            <button key={v} type="button" onClick={() => choose(v)} aria-pressed={d.rule === v}
              className={`rounded px-2 py-1 ${d.rule === v ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}>
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
          <b>Playoffs are seeded by total points scored, not record.</b> The top {d.playoffTeams} teams by season points
          make it — your weekly W/L is cosmetic. So <b>play your highest‑ceiling lineup every week</b>, never the safe
          floor to “win” a matchup.
        </div>
      )}

      {pace && (
        <section className="space-y-2">
          <SubHeading>Your pace to the cut-line</SubHeading>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Right now" value={`#${pace.curRank || "–"}`}
              sub={<span style={{ color: pace.curGap >= 0 ? "var(--good)" : "var(--bad)" }}>{signed(pace.curGap, 0)} vs {d.playoffTeams}th</span>} />
            <StatCard label="Your scoring pace" value={fmt(pace.myPace, 1)} sub={`pts / week (${pace.played}g)`} />
            <StatCard label="Projected finish"
              value={<span style={{ color: pace.projMargin >= 0 ? "var(--good)" : "var(--bad)" }}>{pace.projMargin >= 0 ? "IN" : "OUT"} {signed(pace.projMargin, 0)}</span>}
              sub="pts vs the cut line" />
            <StatCard label="To climb in" value={pace.perWeekGap <= 0 ? "—" : `+${fmt(pace.perWeekGap, 1)}`}
              sub={pace.perWeekGap <= 0 ? "on pace, hold it" : `pts/week over ${pace.weeksLeft}w`} />
          </div>
          <p className="text-xs text-[var(--muted)]">
            {pace.projMargin >= 0
              ? `Projected to finish ${fmt(pace.projMargin, 0)} points inside the top ${d.playoffTeams}. Keep starting your ceiling — don't get cute.`
              : `You're projected ${fmt(-pace.projMargin, 0)} short. You need about ${fmt(pace.myPace + pace.perWeekGap, 1)} pts/week (${fmt(pace.perWeekGap, 1)} above your current pace) the rest of the way — that's the bar for every start/sit and waiver call.`}
          </p>
        </section>
      )}

      <section className="space-y-2">
        <SubHeading>Standings {byPoints ? "· by season points" : "· by record"}</SubHeading>
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
              {d.rows.map((s, i) => (
                <tr key={s.teamId} style={s.mine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                  <td className="num" style={s.inLine ? { color: "var(--good)", fontWeight: 600 } : undefined}>{i + 1}</td>
                  <td className="font-medium">
                    {s.name} {s.mine && <span className="text-xs text-[var(--accent)]">(you)</span>}
                  </td>
                  <td className="num font-semibold">{byPoints ? fmt(s.pf, 0) : wlt(s)}</td>
                  <td className="num hide-sm text-[var(--muted)]">{byPoints ? wlt(s) : fmt(s.pf, 0)}</td>
                  <td className="num">{byPoints ? fmt(s.projPf, 0) : fmt(s.projWins, 1)}</td>
                  <td className="num font-semibold"
                    style={{ color: s.playoffPct == null ? undefined : s.playoffPct >= 60 ? "var(--good)" : s.playoffPct <= 25 ? "var(--bad)" : undefined }}>
                    {s.playoffPct == null ? "–" : `${fmt(s.playoffPct, 0)}%`}
                  </td>
                  <td className="num hide-sm">{s.byePct == null ? "–" : `${fmt(s.byePct, 0)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          Playoff odds from 3,000 simulations of the remaining regular season — each matchup is two Normal(projected
          score, 24) draws; seeded by {byPoints ? "total points scored" : "wins, then points-for"}. Green rank = currently
          in the top {d.playoffTeams}.
        </p>
      </section>

      {d.byes.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Your bye-week gaps</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">Week</th>
                  <th>Off (line up a streamer)</th>
                </tr>
              </thead>
              <tbody>
                {d.byes.map((b) => (
                  <tr key={b.week}>
                    <td className="num font-semibold">{b.week}</td>
                    <td>
                      {b.players.map((p) => (
                        <span key={p.extId} className="mr-2">
                          <PosBadge position={p.pos} small /> {p.name}
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

      {d.playoffRuns.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Playoff schedule (weeks {d.playoffWeeks.join("–")}) — easiest run first</SubHeading>
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
                {d.playoffRuns.map(({ player: p, avg, weeks }) => (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td className="num font-semibold" style={{ color: FDR_TEXT[Math.round(avg)] }}>{fmt(avg, 1)}</td>
                    <td className="text-xs">
                      {weeks.length ? weeks.map((m) => `W${m.week} ${m.opp}`).join(", ") : "schedule not out yet — estimated from nearer matchups"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--muted)]">
            If the Week {d.playoffWeeks[0]}–{d.playoffWeeks.at(-1)} schedule isn't published yet, the difficulty is
            estimated from each player's nearer-term matchups — treat it as directional. Target trade acquisitions with a
            green playoff run.
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
