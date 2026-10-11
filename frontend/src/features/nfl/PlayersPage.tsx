import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { fmt, signed } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading, Toggle } from "@/shared/ui";
import { OppTag, Usage } from "./common";

const POS = ["ALL", "QB", "RB", "WR", "TE", "DST", "K"] as const;
type Pos = (typeof POS)[number];
type Horizon = "week" | "ros";

export default function NflPlayersPage() {
  const [horizon, setHorizon] = useState<Horizon>("ros");
  const [pos, setPos] = useState<Pos>("ALL");
  const q = $api.useQuery("get", "/api/nfl/players", { params: { query: { horizon, position: pos } } }, {
    placeholderData: (prev) => prev,
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Players &amp; free agents</h1>
        <div className="ml-auto">
          <Toggle value={horizon} options={[["week", "this week"], ["ros", "rest of season"]] as const} onChange={setHorizon} />
        </div>
      </div>
      <QueryView query={q}>{(d) => <Players d={d} pos={pos} setPos={setPos} />}</QueryView>
    </div>
  );
}

function Players({ d, pos, setPos }: { d: Api["NflPlayersResponse"]; pos: Pos; setPos: (p: Pos) => void }) {
  const weekly = d.horizon === "week";
  if (d.freeAgents.length === 0 && d.stream.length === 0 && pos === "ALL") {
    return <EmptyState title="No players yet" hint="Waiting for the first NFL sync." />;
  }
  return (
    <>
      {d.holes.length > 0 && (
        <div className="card space-y-2 p-3 text-sm">
          {d.holes.map(({ gap, fill, reason }) => (
            <div key={gap.extId}>
              <span className="text-[var(--bad)]">●</span> <b>{gap.name}</b> ({gap.pos}, {reason}){" "}
              {fill ? (
                <>
                  → best available: <b>{fill.name}</b> <span className="text-[var(--muted)]">{fill.team}</span> (
                  {fmt(fill.weekPoints)} proj{fill.matchups[0]?.opp ? `, ${fill.matchups[0].opp}` : ""})
                </>
              ) : (
                <span className="text-[var(--muted)]">→ nothing worthwhile on waivers</span>
              )}
            </div>
          ))}
        </div>
      )}

      {d.stream.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Streaming — best available, next 3 weeks</SubHeading>
          <div className="grid gap-3 sm:grid-cols-2">
            {d.stream.map((g) => (
              <div key={g.position} className="card p-3 text-sm">
                <div className="mb-1 font-semibold">
                  <PosBadge position={g.position} small /> {g.position}
                </div>
                <table className="dtable">
                  <thead>
                    <tr>
                      <th>Player</th>
                      {[0, 1, 2].map((i) => (
                        <th key={i} className="num">W{d.week + i}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {g.options.map(({ player: p, weeks, best }) => (
                      <tr key={p.extId}>
                        <td className="font-medium">
                          {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                        </td>
                        {weeks.map((w, i) => (
                          <td key={d.week + i} className="num tabular-nums" style={w.fdr ? { background: FDR_BG[w.fdr] } : undefined}
                            title={w.opp ? `${w.opp} · matchup ${w.fdr}/5` : "bye"}>
                            <span className={i === best ? "font-bold" : undefined}>{w.proj > 0 ? fmt(w.proj) : "–"}</span>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <p className="text-xs text-[var(--muted)]">
            Ranked by combined 3-week projection; the bold week is each option's best matchup — stream the one whose good
            week is now, hold for the one whose good week is later. Cell colour = that week's matchup (green easy … red
            hard).
          </p>
        </section>
      )}

      <Toggle value={pos} options={POS} onChange={setPos} />

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Player</th>
              <th>Wk</th>
              <th className="num hide-sm">Usage</th>
              <th className="num">Wk proj</th>
              <th className="num hide-sm" title="expected fantasy points per game from the ffopportunity opportunity model (last ~4 games)">xFP/g</th>
              <th className="num hide-sm" title="expected total touchdowns per game (ffopportunity)">xTD</th>
              <th className="num hide-sm" title="fantasy points per game over (+) or under (−) what their opportunity expects — persistent + = TD-luck regression risk, − = buy-low">+/− exp</th>
              <th className="num">ROS</th>
              <th className="num hide-sm">VOR</th>
              <th className="num">vs your worst</th>
              <th className="num hide-sm">% rost</th>
            </tr>
          </thead>
          <tbody>
            {d.freeAgents.map(({ player: p, upgrade }) => (
              <tr key={p.extId}>
                <td className="font-medium">
                  <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                  {p.injury === "QUESTIONABLE" && <span className="ml-1 text-[10px] text-[var(--warn)]">Q</span>}
                  <OppTag p={p} />
                </td>
                <td>
                  <span className="rounded px-1 text-xs" style={p.matchups[0]?.fdr ? { background: FDR_BG[p.matchups[0].fdr] } : undefined}>
                    {p.matchups[0]?.opp || "—"}
                  </span>
                </td>
                <td className="num hide-sm text-xs">
                  <Usage p={p} />
                </td>
                <td className="num">{fmt(p.weekPoints)}</td>
                <td className="num hide-sm">{p.expGames ? fmt(p.xfpG, 1) : "–"}</td>
                <td className="num hide-sm">{p.expGames ? fmt(p.xtdG, 2) : "–"}</td>
                <td className="num hide-sm"
                  style={{ color: !p.expGames ? undefined : p.fpOe >= 2 ? "var(--bad)" : p.fpOe <= -2 ? "var(--good)" : "var(--muted)" }}>
                  {p.expGames ? signed(p.fpOe, 1) : "–"}
                </td>
                <td className="num font-semibold">{fmt(p.rosProj, 0)}</td>
                <td className="num hide-sm">{fmt(p.vor, 0)}</td>
                <td className="num font-semibold" style={{ color: upgrade > 0 ? "var(--good)" : "var(--muted)" }}>
                  {upgrade > 0 ? "+" : ""}
                  {fmt(upgrade, weekly ? 1 : 0)}
                </td>
                <td className="num hide-sm">{fmt(p.pctOwned, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend
        items={[
          ["Wk proj / ROS", "projected points this week / rest of season"],
          ["Usage", "recent snap share (or target share) — ▲/▼ = rising/falling snaps, W = workhorse, rot = rotational. From nflverse; blank until the season has games played"],
          ["xFP/g · xTD", "expected fantasy points and expected touchdowns per game from the ffopportunity opportunity model (last ~4 games) — what the volume/quality of touches is worth, before finishing luck"],
          ["+/− exp", "points per game over (red) or under (green) that expectation — a persistent gap flags TD-luck regression (fade) or a buy-low"],
          ["VOR", "value over replacement — points above the last startable player at the position"],
          ["vs your worst", "how much better than your weakest starter at that position, on opportunity-adjusted ROS (docks TD/finishing-luck overperformers, credits the unlucky) — a real upgrade if green"],
          ["buy-low / sell-high", "scoring well under / over what their touches & targets expect — the ROS number and ranking already fold this in"],
          ["% rost", "rostered across ESPN leagues — a rough 'how contested on waivers' signal"],
          ["hidden", "players marked OUT / IR / SUSP are excluded"],
        ]}
      />
    </>
  );
}
