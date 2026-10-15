import { $api, type Api } from "@/api/client";
import { fmt, relTime, signed } from "@/shared/format";
import { EmptyState, Legend, QueryView, Section } from "@/shared/ui";
import { LiveRivalTable } from "./LiveMatchday";
import { StrategyBanner } from "./StrategyBanner";

export default function RivalsPage() {
  const q = $api.useQuery("get", "/api/ucl/rivals", {}, {
    refetchInterval: (query) => (query.state.data?.live ? 60_000 : false),
  });
  return <QueryView query={q}>{(d) => <Rivals d={d} />}</QueryView>;
}

function Rivals({ d }: { d: Api["UclRivalsResponse"] }) {
  const { matchday: md, report: r, live } = d;
  if (!r.ready) {
    return (
      <EmptyState
        title="Rival tracking populates after matchday 1"
        hint="Once the mini-league has a completed matchday, the scheduled sync pulls every rival's squad and this page projects their scores, differentials and template risk."
      />
    );
  }
  const managers = r.rivalCount + 1;
  return (
    <div className="space-y-6">
      {r.stale && (
        <div className="card p-3 text-sm" style={{ borderLeft: "3px solid var(--warn)" }}>
          <b style={{ color: "var(--warn)" }}>SQUADS MAY BE STALE</b>{" "}
          {r.squadsMatchday != null && r.squadsMatchday !== md
            ? `UEFA hasn't published matchday ${md} squads yet — projecting from matchday ${r.squadsMatchday}. `
            : ""}
          {r.squadsAsOf ? `Rival squads last captured ${relTime(r.squadsAsOf)}. ` : ""}
          If a rival has transferred since, their projection and differentials below won't reflect it until the next
          sync captures their squad.
        </div>
      )}

      {live && live.rows.some((x) => x.mine) && (
        <Section
          title={live.state === "finished" ? `Matchday ${live.matchday} — final` : `Live — matchday ${live.matchday}`}
          right={
            live.state === "finished" ? undefined : (
              <span className="text-xs text-[var(--muted)]">refreshes every few minutes while matches are on</span>
            )
          }
        >
          <LiveRivalTable rivals={live} />
          <p className="text-xs text-[var(--muted)]">
            {live.state === "finished"
              ? ""
              : "Secured = points already banked; projected finish blends banked points with xPts for players still to play. "}
            Rivals are scored from their saved XI and captain, without auto-subs; your row uses the auto-sub-aware
            number from the Overview.
          </p>
        </Section>
      )}

      {r.strategy && <StrategyBanner s={r.strategy} />}

      {r.captainPicks.length > 0 && (
        <div className="card p-3 text-sm">
          <b className="text-[var(--muted)]">Armband across the league: </b>
          {r.captainPicks.map((c, i) => (
            <span key={c.playerId}>
              {i > 0 && " · "}
              <span className={c.mine ? "font-semibold text-[var(--accent)]" : ""}>
                {c.name} ({c.count}/{managers}){c.mine ? " — you" : ""}
              </span>
            </span>
          ))}
          <div className="mt-1 text-xs text-[var(--muted)]">
            {r.strategy?.mode === "chase"
              ? "You're chasing — captaining the same player as the field locks in the gap. Go off-template."
              : r.strategy?.mode === "protect"
                ? "You're protecting — captaining with the field caps your downside. Match the popular pick."
                : "Match the field to neutralise the armband, or differ to create a swing."}
          </div>
        </div>
      )}

      <p className="text-sm text-[var(--muted)]">
        Projected matchday {md} scores for your {r.rivalCount} mini-league rival{r.rivalCount === 1 ? "" : "s"}, from
        their saved squads — their actual XI and captain where UEFA exposes them, otherwise a top-11-by-xPts estimate.
        Your projected score: <strong>{fmt(r.myProjectedPoints)}</strong>
        {r.myRank ? ` · currently rank ${r.myRank}` : ""}
        {r.squadsAsOf ? ` · rival squads as of ${relTime(r.squadsAsOf)}` : ""}.
      </p>

      <Section title="Rivals — projected this matchday">
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Manager</th>
                <th className="num">Total</th>
                <th className="num">Proj MD</th>
                <th className="num">vs you</th>
                <th className="num hide-sm">Shared</th>
                <th className="hide-sm">Their differentials (they have, you don't)</th>
              </tr>
            </thead>
            <tbody>
              {r.rivals.map((v) => (
                <tr key={v.entryId}>
                  <td className="num">{v.rank}</td>
                  <td className="font-medium">
                    {v.managerName || v.teamName || v.entryId}
                    {v.teamName && v.managerName && (
                      <span className="block text-xs text-[var(--muted)]">{v.teamName}</span>
                    )}
                  </td>
                  <td className="num">{v.totalPoints}</td>
                  <td className="num font-semibold">{fmt(v.projectedPoints)}</td>
                  <td className="num font-semibold" style={{ color: v.gapVsMe > 0 ? "var(--bad)" : "var(--good)" }}>
                    {signed(v.gapVsMe)}
                  </td>
                  <td className="num hide-sm">{v.overlap}/15</td>
                  <td className="hide-sm text-xs">
                    {v.theirDifferentials.map((p) => `${p.name} (${fmt(p.xpts)})`).join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {r.commonThreats.length > 0 && (
        <Section title="Cover candidates — owned by most rivals, not by you">
          <OwnedTable rows={r.commonThreats} rivals={r.rivalCount} md={md} label="Owned by" />
          <p className="mt-2 text-xs text-[var(--muted)]">
            If you're protecting a lead, owning these caps your downside. If you're chasing, fade them and attack with
            the differentials above instead.
          </p>
        </Section>
      )}

      {r.templateRisk.length > 0 && (
        <Section title="Your template picks — how exposed you are">
          <OwnedTable rows={r.templateRisk} rivals={r.rivalCount} md={md} label="Rivals who also own" />
        </Section>
      )}

      {r.effectiveOwnership.length > 0 && (
        <Section title="Effective ownership — in your mini-league only">
          <p className="text-sm text-[var(--muted)]">
            What matters isn't global ownership — it's how many of the {managers} managers you're actually racing own
            each player. Low % + high xPts = a real rank-gaining differential; high % = template (safe, no edge).
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Team</th>
                  <th className="num">Owned</th>
                  <th className="num">xPts (MD{md})</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {r.effectiveOwnership.slice(0, 30).map((p) => (
                  <tr key={p.playerId} style={p.mine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                    <td className="font-medium">{p.name}</td>
                    <td className="text-[var(--muted)]">{p.team}</td>
                    <td
                      className="num font-semibold"
                      style={{ color: p.ownedPct >= 60 ? "var(--muted)" : p.ownedPct <= 25 ? "var(--good)" : undefined }}
                    >
                      {p.ownedPct}%
                    </td>
                    <td className="num">{fmt(p.xpts)}</td>
                    <td className="text-xs">
                      {p.mine ? (
                        <span className="text-[var(--accent)]">you</span>
                      ) : p.ownedPct <= 25 && p.xpts >= 4.5 ? (
                        <span className="text-[var(--good)]">differential</span>
                      ) : p.ownedPct >= 60 ? (
                        <span className="text-[var(--muted)]">template</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <Legend
        items={[
          ["Proj MD", "their projected matchday points — actual XI + captain when available, else top 11 by xPts + top scorer doubled"],
          ["Owned", "% of your mini-league (rivals + you) that has this player"],
          ["vs you", "their projection minus yours — red means they out-project you this matchday"],
          ["Shared", "players in common with your squad, out of 15"],
          ["Their differentials", "players they own that you don't — where they can gain on you"],
          ["Cover candidates", "widely-owned among rivals but missing from your squad — differential risk against you"],
          ["Template picks", "your players that rivals also hold — safe, but no edge"],
        ]}
      />
    </div>
  );
}

function OwnedTable({ rows, rivals, md, label }: { rows: Api["OwnedPlayer"][]; rivals: number; md: number; label: string }) {
  return (
    <div className="card table-wrap">
      <table className="dtable">
        <thead>
          <tr>
            <th>Player</th>
            <th className="num">{label}</th>
            <th className="num">xPts (MD{md})</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.playerId}>
              <td className="font-medium">{p.name}</td>
              <td className="num">
                {p.ownedByRivals}/{rivals}
              </td>
              <td className="num font-semibold">{fmt(p.xpts)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
