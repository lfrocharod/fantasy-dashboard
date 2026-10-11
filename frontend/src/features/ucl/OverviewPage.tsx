import { $api, type Api } from "@/api/client";
import { FDR_TEXT } from "@/shared/fdr";
import { dateTime, fmt, lastName, money, timeUntil } from "@/shared/format";
import { Checklist, EmptyState, Legend, PosBadge, QueryView, Section, StatCard, StatusDot } from "@/shared/ui";
import { CaptaincyCard } from "./CaptaincyCard";
import { LiveMatchday } from "./LiveMatchday";
import { StrategyBanner } from "./StrategyBanner";

export default function OverviewPage() {
  const q = $api.useQuery("get", "/api/ucl/overview", {}, {
    // while a matchday is in play, keep the live panel fresh
    refetchInterval: (query) => (query.state.data?.live?.state === "live" ? 60_000 : false),
  });
  return <QueryView query={q}>{(o) => <Overview o={o} />}</QueryView>;
}

function Overview({ o }: { o: Api["UclOverview"] }) {
  if (!o.hasSquad || !o.cards) {
    return (
      <EmptyState
        title={`No squad loaded for matchday ${o.matchday}`}
        hint="Connect your UEFA account in Settings; the next scheduled sync pulls your squad."
      />
    );
  }
  const live = o.live;
  const c = o.cards;
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Matchday" value={o.matchday} />
        <StatCard
          label={live ? "Live" : "Deadline"}
          value={live ? (live.state === "finished" ? "✓ FT" : "🔴") : timeUntil(o.deadlineIso)}
          sub={live ? `${live.played}/${live.starters} played` : undefined}
        />
        <StatCard
          label={live ? "Proj. finish" : "Proj. total"}
          value={fmt(live ? live.projectedFinish : c.projTotal, 0)}
          sub={live ? `${fmt(live.securedPoints, 0)} secured` : "best XI + captain"}
        />
        <StatCard label="Captain pick" value={lastName(c.captainPickName)} sub={`${fmt(c.captainPickXpts)} xPts`} />
        <StatCard label="Squad value" value={money(c.squadValue)} />
        <StatCard label="League rank" value={c.rank ?? "–"} sub={c.leagueSize ? `of ${c.leagueSize}` : undefined} />
      </div>

      {live ? (
        <LiveMatchday live={live} history={o.liveHistory} rivals={o.liveRivals} />
      ) : (
        <>
          {o.strategy && <StrategyBanner s={o.strategy} />}
          {o.captaincy && <CaptaincyCard v={o.captaincy} />}
          <Section title="Pre-deadline checklist">
            <Checklist items={o.checklist} />
          </Section>
        </>
      )}

      <Section title="Your squad">
        <div className="card table-wrap">
          <SquadTable rows={o.squad} />
        </div>
        <Legend
          items={[
            ["Opp colour", "position-aware fixture difficulty (green easy … red hard): forwards weigh the opponent's defence, keepers their attack, defenders mostly clean-sheet risk plus some set-piece upside. (H) home, (A) away"],
            ["xPts", "expected points this matchday"],
            ["xMin", "expected minutes"],
            ["P(start)", "chance of starting — 100%/0% once the official lineup is out"],
            ["Form", "UEFA points per game this season"],
            ["xGI90", "expected goal involvements per 90 (non-penalty xG + xA), domestic-league season"],
            ["🅲", "highest projected scorer (see Optimizer for the constrained pick)"],
          ]}
        />
      </Section>

      {!live && (
        <Section title={`Matchday ${o.fixturesMatchday} fixtures`}>
          {o.fixtures.length === 0 ? (
            <EmptyState title="No fixtures loaded for this matchday" />
          ) : (
            <div className="card table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Kickoff</th>
                    <th>Home</th>
                    <th>Away</th>
                    <th className="num">Score</th>
                    <th className="num">xG (H)</th>
                    <th className="num">xG (A)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {o.fixtures.map((f) => {
                    const played = f.status === "finished" || f.status === "live";
                    return (
                      <tr key={f.matchId}>
                        <td>{f.kickoff ? dateTime(f.kickoff) : "TBD"}</td>
                        <td>{f.homeTeam}</td>
                        <td>{f.awayTeam}</td>
                        <td className="num font-semibold tabular-nums">{played ? `${f.homeGoals ?? 0}–${f.awayGoals ?? 0}` : "–"}</td>
                        <td className="num">{fmt(f.homeXg)}</td>
                        <td className="num">{fmt(f.awayXg)}</td>
                        <td>{f.status}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

function SquadTable({ rows }: { rows: Api["SquadTableRow"][] }) {
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Pos</th>
          <th>Player</th>
          <th>Team</th>
          <th>Opp</th>
          <th className="num">Price</th>
          <th className="num">Form</th>
          <th className="num">xGI90</th>
          <th className="num">P(start)</th>
          <th className="num">xMin</th>
          <th className="num">xPts</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const opp = r.opponent;
          const pct = r.startPct != null ? Math.round(r.startPct * 100) : null;
          return (
            <tr key={r.playerId}>
              <td>
                <PosBadge position={r.position} />
              </td>
              <td>
                {r.name} <StatusDot code={r.statusCode} detail={r.statusDetail} />
              </td>
              <td>{r.teamName}</td>
              <td
                className="font-medium"
                style={{ color: opp ? FDR_TEXT[opp.fdr.pos] : "var(--muted)" }}
                title={opp ? `${r.position} difficulty ${opp.fdr.pos}/5 — goals/assists ${opp.fdr.att}/5, clean sheet ${opp.fdr.def}/5` : "no fixture"}
              >
                {opp ? `${opp.name} (${opp.home ? "H" : "A"})` : "–"}
              </td>
              <td className="num">{fmt(r.price)}</td>
              <td className="num">{fmt(r.uefaForm)}</td>
              <td className="num text-[var(--muted)]">{fmt(r.xgi90, 2)}</td>
              <td className="num">
                {pct != null ? `${pct}%` : "–"}
                {r.confirmed === "start" && <span className="ml-1 text-[var(--good)]" title="confirmed starting XI">✓</span>}
                {r.confirmed === "bench" && <span className="ml-1 text-[var(--muted)]" title="confirmed on the bench">⑂</span>}
              </td>
              <td className="num">{fmt(r.expMinutes, 0)}</td>
              <td className="num font-semibold">{fmt(r.xpts)}</td>
              <td>{r.recommendedCaptain ? "🅲" : r.isCaptain ? "(c)" : ""}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
