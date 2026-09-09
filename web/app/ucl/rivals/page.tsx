import { EmptyState, Legend, Section } from "@/components/ui";
import { fmt, relTime } from "@/lib/format";
import { getCurrentMatchday, getLiveRivals, getRivals } from "@/lib/ucl/queries";

export const dynamic = "force-dynamic";

export default async function RivalsPage() {
  const md = await getCurrentMatchday();
  const [r, liveRivals] = await Promise.all([getRivals(md), getLiveRivals()]);
  const live = liveRivals && liveRivals.rows.length > 0 ? liveRivals : null;

  if (!r.ready) {
    return (
      <EmptyState
        title="Rival tracking populates after matchday 1"
        hint="Once the mini-league has a completed matchday, ./run.sh pulls every rival's squad and this page projects their scores, differentials and template risk."
      />
    );
  }

  const STRAT_TONE: Record<string, string> = {
    protect: "var(--good)",
    hold: "var(--warn)",
    chase: "var(--accent)",
    free: "var(--muted)",
  };

  const myLive = live?.rows.find((x) => x.mine) ?? null;

  return (
    <div className="space-y-6">
      {r.stale && (
        <div className="card p-3 text-sm" style={{ borderLeft: "3px solid var(--warn)" }}>
          <b style={{ color: "var(--warn)" }}>SQUADS MAY BE STALE</b>{" "}
          {r.squadsMatchday != null && r.squadsMatchday !== md
            ? `UEFA hasn't published matchday ${md} squads yet — projecting from matchday ${r.squadsMatchday}. `
            : ""}
          {r.squadsAsOf
            ? `Rival squads last captured ${relTime(r.squadsAsOf)}. `
            : ""}
          If a rival has transferred since, their projection and differentials
          below won&apos;t reflect it — re-run <code>./run.sh</code> (needs a fresh
          UEFA cookie) to refresh.
        </div>
      )}

      {live && myLive && (
        <Section
          title={`Live — matchday ${live.matchday}`}
          right={<span className="text-xs text-[var(--muted)]">updates when ./run.sh --live runs</span>}
        >
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Manager</th>
                  <th className="num">Played</th>
                  <th className="num">Secured</th>
                  <th className="num">Proj. finish</th>
                  <th className="num">vs you</th>
                </tr>
              </thead>
              <tbody>
                {live.rows.map((v) => (
                  <tr key={v.entryId} className={v.mine ? "font-semibold" : undefined}>
                    <td className="num">{v.rank || "–"}</td>
                    <td>
                      {v.managerName || v.teamName || v.entryId}
                      {v.mine && <span className="ml-1 text-[var(--accent)]">you</span>}
                    </td>
                    <td className="num">{v.played}</td>
                    <td className="num">{fmt(v.secured, 0)}</td>
                    <td className="num font-semibold">{fmt(v.projected, 0)}</td>
                    <td
                      className="num"
                      style={{
                        color: v.mine
                          ? "var(--muted)"
                          : (v.liveGapVsMe ?? 0) > 0
                            ? "var(--bad)"
                            : "var(--good)",
                      }}
                    >
                      {v.mine
                        ? "–"
                        : `${(v.liveGapVsMe ?? 0) >= 0 ? "+" : ""}${fmt(v.liveGapVsMe, 0)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--muted)]">
            Secured = points already banked; projected finish blends banked points with xPts for
            players still to play. Rivals use a top-11 + captain estimate; your row uses the
            auto-sub-aware number from the Overview.
          </p>
        </Section>
      )}

      {r.strategy && (
        <div
          className="card p-3 text-sm"
          style={{ borderLeft: `3px solid ${STRAT_TONE[r.strategy.mode]}` }}
        >
          <b style={{ color: STRAT_TONE[r.strategy.mode] }}>
            {r.strategy.mode === "protect"
              ? "PROTECT"
              : r.strategy.mode === "hold"
                ? "HOLD"
                : r.strategy.mode === "chase"
                  ? "CHASE"
                  : "FREE ROLL"}
          </b>{" "}
          {r.strategy.text}
        </div>
      )}

      {r.captainPicks.length > 0 && (
        <div className="card p-3 text-sm">
          <b className="text-[var(--muted)]">Armband across the league: </b>
          {r.captainPicks.map((c, i) => (
            <span key={c.playerId}>
              {i > 0 && " · "}
              <span className={c.mine ? "font-semibold text-[var(--accent)]" : ""}>
                {c.name} ({c.count}/{r.rivalCount + 1}){c.mine ? " — you" : ""}
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
        Projected matchday {md} scores for your {r.rivalCount} mini-league rival
        {r.rivalCount === 1 ? "" : "s"}, from their saved squads — their actual XI and captain where
        UEFA exposes them, otherwise a top-11-by-xPts estimate. Your projected score:{" "}
        <strong>{fmt(r.myProjectedPoints)}</strong>
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
                <th className="hide-sm">Their differentials (they have, you don&apos;t)</th>
              </tr>
            </thead>
            <tbody>
              {r.rivals.map((v) => (
                <tr key={v.entryId}>
                  <td className="num">{v.rank}</td>
                  <td className="font-medium">
                    {v.managerName || v.teamName || v.entryId}
                    {v.teamName && v.managerName ? (
                      <span className="block text-xs text-[var(--muted)]">{v.teamName}</span>
                    ) : null}
                  </td>
                  <td className="num">{v.totalPoints}</td>
                  <td className="num font-semibold">{fmt(v.projectedPoints)}</td>
                  <td
                    className="num font-semibold"
                    style={{ color: v.gapVsMe > 0 ? "var(--bad, #ef4444)" : "var(--good)" }}
                  >
                    {v.gapVsMe > 0 ? "+" : ""}
                    {fmt(v.gapVsMe)}
                  </td>
                  <td className="num hide-sm">{v.overlap}/15</td>
                  <td className="hide-sm text-xs">
                    {v.theirDifferentials
                      .map((p) => `${p.name} (${fmt(p.xpts)})`)
                      .join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {r.commonThreats.length > 0 && (
        <Section title="Cover candidates — owned by most rivals, not by you">
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">Owned by</th>
                  <th className="num">xPts (MD{md})</th>
                </tr>
              </thead>
              <tbody>
                {r.commonThreats.map((p) => (
                  <tr key={p.playerId}>
                    <td className="font-medium">{p.name}</td>
                    <td className="num">
                      {p.ownedByRivals}/{r.rivalCount}
                    </td>
                    <td className="num font-semibold">{fmt(p.xpts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">
            If you&apos;re protecting a lead, owning these caps your downside. If you&apos;re chasing,
            fade them and attack with the differentials above instead.
          </p>
        </Section>
      )}

      {r.templateRisk.length > 0 && (
        <Section title="Your template picks — how exposed you are">
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">Rivals who also own</th>
                  <th className="num">xPts (MD{md})</th>
                </tr>
              </thead>
              <tbody>
                {r.templateRisk.map((p) => (
                  <tr key={p.playerId}>
                    <td className="font-medium">{p.name}</td>
                    <td className="num">
                      {p.ownedByRivals}/{r.rivalCount}
                    </td>
                    <td className="num">{fmt(p.xpts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {r.effectiveOwnership.length > 0 && (
        <Section title="Effective ownership — in your mini-league only">
          <p className="text-sm text-[var(--muted)]">
            What matters isn&apos;t global ownership — it&apos;s how many of the {r.rivalCount + 1}{" "}
            managers you&apos;re actually racing own each player. Low % + high xPts = a real
            rank-gaining differential; high % = template (safe, no edge).
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
                      style={{
                        color:
                          p.ownedPct >= 60 ? "var(--muted)" : p.ownedPct <= 25 ? "var(--good)" : undefined,
                      }}
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
