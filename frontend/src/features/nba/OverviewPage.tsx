import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { DraftSetup } from "@/features/draft/DraftSetup";
import { fmt, signed } from "@/shared/format";
import { Checklist, EmptyState, Legend, QueryView, StatCard, SubHeading } from "@/shared/ui";
import { ESPN_SETUP_HINT, Who, dayLabel } from "./common";
import { Streams } from "./Streams";

export default function NbaOverviewPage() {
  const q = $api.useQuery("get", "/api/nba/overview");
  return <QueryView query={q}>{(o) => <Overview o={o} />}</QueryView>;
}

const TODAY_TONE: Record<string, string> = {
  start: "var(--good)", bench: "var(--warn)", "no game": "var(--muted)", IR: "var(--muted)", out: "var(--bad)",
};

function Overview({ o }: { o: Api["NbaOverview"] }) {
  const [setup, setSetup] = useState(!o.hasRoster);
  const s = o.score;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">
          {o.isPlayoffs ? "Playoffs · " : ""}Matchup {o.period}
          <span className="ml-2 text-sm font-normal text-[var(--muted)]">
            {dayLabel(o.firstDate)} – {dayLabel(o.lastDate)}
            {o.leagueName && ` · ${o.leagueName}`}
          </span>
        </h1>
        <button type="button" className="btn text-xs" onClick={() => setSetup((v) => !v)}>
          {setup ? "Hide setup" : "Setup"}
        </button>
      </div>
      {setup && <DraftSetup sport="nba" />}

      {!o.hasRoster ? (
        <EmptyState title="No roster yet" hint={ESPN_SETUP_HINT} />
      ) : (
        <>
          {o.seasonOver ? (
            <EmptyState title="The fantasy season is over" />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="You" value={fmt(s?.myProj ?? 0, 0)}
                sub={s ? `${fmt(s.myPoints, 0)} banked + ${fmt(s.myRemaining, 0)} to come` : undefined} />
              <StatCard label={s?.oppName ?? "Opponent"} value={s ? fmt(s.oppProj, 0) : "–"}
                sub={s ? `${fmt(s.oppPoints, 0)} banked + ${fmt(s.oppRemaining, 0)} to come` : undefined} />
              <StatCard label="Win chance" value={s?.winPct != null ? `${s.winPct}%` : "–"}
                sub={s ? `margin ${signed(s.myProj - s.oppProj, 0)}` : undefined} />
              <StatCard label="Days left" value={o.daysLeft}
                sub={o.todayDate ? `next game day ${dayLabel(o.todayDate)}` : undefined} />
            </div>
          )}

          {o.checklist.length > 0 && (
            <section className="space-y-2">
              <SubHeading>This matchup — checklist</SubHeading>
              <Checklist items={o.checklist} />
            </section>
          )}

          <section className="space-y-2">
            <SubHeading>Your roster</SubHeading>
            <div className="card table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Next game</th>
                    <th className="num">FP/g</th>
                    <th className="num">Games left</th>
                    <th className="num hide-sm">Starts</th>
                    <th className="num">Proj</th>
                    <th className="num hide-sm">ROS</th>
                    <th>Slot</th>
                  </tr>
                </thead>
                <tbody>
                  {o.roster.map(({ player: p, starts, lost, today }) => (
                    <tr key={p.extId} style={p.slot === "IR" ? { opacity: 0.55 } : undefined}>
                      <td>
                        <Who p={p} />
                      </td>
                      <td className="text-xs">
                        <span style={{ color: TODAY_TONE[today] }}>{today}</span>
                        {p.today && <span className="ml-1 text-[var(--muted)]">{p.today}</span>}
                      </td>
                      <td className="num">{fmt(p.fppg)}</td>
                      <td className="num">{p.gamesLeft}</td>
                      <td className="num hide-sm">
                        {starts}
                        {lost > 0 && <span className="ml-1 text-[10px] text-[var(--warn)]" title="games on the bench">−{lost}</span>}
                      </td>
                      <td className="num font-semibold">{fmt(p.weekPoints, 0)}</td>
                      <td className="num hide-sm">{fmt(p.ros, 0)}</td>
                      <td className="text-xs text-[var(--muted)]">{p.slot}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {o.streams.length > 0 && <Streams streams={o.streams} />}

          <p className="text-xs text-[var(--muted)]">
            Pickups:{" "}
            {o.moves.limit == null
              ? "no limit"
              : o.moves.perDay
                ? `${o.moves.limit} a day`
                : `${o.moves.left ?? "?"} of ${o.moves.limit} left this matchup`}
            {o.moves.waiverNote && ` · ${o.moves.waiverNote}`}
          </p>
          {o.warnings.length > 0 && (
            <p className="text-xs text-[var(--warn)]">Calendar check: {o.warnings.join("; ")}</p>
          )}

          <Legend
            items={[
              ["FP/g", "fantasy points per game in your league's scoring — ESPN's projection early on, your player's own average as games pile up"],
              ["Games left", "his NBA team's games from today to the end of this matchup"],
              ["Starts / −n", "games the daily optimizer starts him / games he'd sit because your slots are full"],
              ["Proj", "expected points over the days left if he started every game — injury tags count less the further ahead"],
              ["ROS", "rest-of-season points: per-game rate × games left × the share he's expected to play"],
              ["next game", "start / bench is the best lineup for the next game day; no game = his team is off"],
            ]}
          />
        </>
      )}
    </div>
  );
}
