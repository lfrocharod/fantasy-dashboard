import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, Range, SubHeading } from "@/shared/ui";
import { InjTag, MatchupChip } from "./common";

const MODE_COPY = {
  ceiling: { label: "CEILING", tone: "var(--accent)", why: "you need variance — start the higher-upside options, not the safe floor" },
  floor: { label: "FLOOR", tone: "var(--good)", why: "you're a solid favourite — start the safe floor and don't hand back the edge" },
  mean: { label: "BALANCED", tone: "var(--muted)", why: "close matchup — start your best straight projection" },
} as const;
const CALL_COLOR = { START: "var(--good)", "FLEX?": "var(--warn)", SIT: "var(--muted)" } as const;

export default function NflOptimizerPage() {
  const q = $api.useQuery("get", "/api/nfl/optimizer");
  return <QueryView query={q}>{(d) => <Optimizer d={d} />}</QueryView>;
}

function Optimizer({ d }: { d: Api["NflOptimizer"] }) {
  if (!d.hasRoster) return <EmptyState title="No roster yet" hint="Waiting for the first NFL sync." />;
  const mc = MODE_COPY[d.mode];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Optimizer — week {d.week}</h1>
        <span className="text-sm text-[var(--muted)]">
          projects <b>{fmt(d.meanTotal, 0)}</b>{" "}
          <span className="text-xs">
            ({fmt(d.loTotal, 0)}–{fmt(d.hiTotal, 0)})
          </span>
        </span>
      </div>

      <div className="card p-3 text-sm" style={{ borderLeft: `3px solid ${mc.tone}` }}>
        <b style={{ color: mc.tone }}>{mc.label} LINEUP</b>{" "}
        <span className="text-[var(--muted)]">
          — {d.seedByPoints ? "league seeds on total points, so always chase upside" : `${d.winPct}% to win this week`}: {mc.why}.
        </span>
      </div>

      {d.toStart.length > 0 || d.toBench.length > 0 ? (
        <div className="card p-3 text-sm">
          <b className="text-[var(--warn)]">Lineup changes to make in ESPN:</b>
          <ul className="mt-1 space-y-0.5">
            {d.toStart.map((p) => (
              <li key={p.extId}>
                ▲ Start <b>{p.name}</b> ({p.pos}, {fmt(p.weekPoints)} proj)
              </li>
            ))}
            {d.toBench.map((p) => (
              <li key={p.extId} className="text-[var(--muted)]">
                ▼ Bench {p.name} ({p.slot}, {fmt(p.weekPoints)} proj)
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="card p-3 text-sm text-[var(--good)]">Your ESPN lineup already matches the optimal one.</p>
      )}

      <section className="space-y-2">
        <SubHeading>Optimal lineup</SubHeading>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Slot</th>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num">Proj</th>
                <th className="num hide-sm">Range</th>
              </tr>
            </thead>
            <tbody>
              {d.lineup.map(({ slot, player: p }, i) => (
                <tr key={`${slot}-${p?.extId ?? i}`}>
                  <td className="text-xs text-[var(--muted)]">{slot}</td>
                  <td className="font-medium">
                    {p ? (
                      <>
                        <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                        <InjTag s={p.injury} />
                      </>
                    ) : (
                      <span className="text-[var(--bad)]">— empty —</span>
                    )}
                  </td>
                  <td>{p && <MatchupChip p={p} />}</td>
                  <td className="num font-semibold">{p ? fmt(p.weekPoints) : "–"}</td>
                  <td className="num hide-sm">{p ? <Range lo={p.lo} mean={p.weekPoints} hi={p.hi} /> : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2">
        <SubHeading>Start / sit — every rostered player</SubHeading>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Matchup</th>
                <th className="num hide-sm">Usage</th>
                <th className="num">Wk proj</th>
                <th className="num hide-sm">Range</th>
                <th className="num hide-sm">ROS</th>
                <th>Call</th>
              </tr>
            </thead>
            <tbody>
              {d.startSit.map(({ player: p, call }) => (
                <tr key={p.extId}>
                  <td className="font-medium">
                    <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    <InjTag s={p.injury} />
                    {p.onBye && <span className="ml-1 text-[10px] text-[var(--warn)]">BYE</span>}
                  </td>
                  <td>
                    <MatchupChip p={p} />
                  </td>
                  <td className="num hide-sm text-xs">
                    {p.usageGames >= 1 ? (
                      <span title={`last ${p.usageGames}g · ${Math.round(p.snapPct * 100)}% snaps · wopr ${p.wopr.toFixed(2)}`}
                        style={{ color: p.usageTag === "workhorse" ? "var(--good)" : p.usageTag === "rotational" ? "var(--warn)" : undefined }}>
                        {p.snapPct ? `${Math.round(p.snapPct * 100)}%` : "–"}
                        {p.snapTrend >= 0.08 ? " ▲" : p.snapTrend <= -0.08 ? " ▼" : ""}
                      </span>
                    ) : (
                      <span className="text-[var(--muted)]">–</span>
                    )}
                  </td>
                  <td className="num font-semibold">{fmt(p.weekPoints)}</td>
                  <td className="num hide-sm">
                    <Range lo={p.lo} hi={p.hi} />
                  </td>
                  <td className="num hide-sm">{fmt(p.rosProj, 0)}</td>
                  <td className="text-xs font-semibold" style={{ color: CALL_COLOR[call] }}>
                    {call}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Legend
        items={[
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Proj / ROS", "projected PPR points this week / rest of season"],
          ["Range", "~15th–85th percentile week (floor–ceiling): wider for boom/bust spots (WR/TE/DST, committee backs), tighter for a locked-in workhorse"],
          ["FLOOR / CEILING / BALANCED lineup", "which side of the range to optimise: chase ceiling as an underdog or in a points-seeded league, protect the floor as a favourite"],
          ["Call", "START = in your optimal lineup · FLEX? = viable flex swing · SIT = leave it"],
        ]}
      />
    </div>
  );
}
