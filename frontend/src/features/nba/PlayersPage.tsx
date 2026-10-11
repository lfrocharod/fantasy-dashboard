import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { fmt, signed } from "@/shared/format";
import { EmptyState, Legend, QueryView, Toggle } from "@/shared/ui";
import { Who } from "./common";
import { Streams } from "./Streams";

const POS = ["ALL", "PG", "SG", "SF", "PF", "C"] as const;
type Pos = (typeof POS)[number];
type Sort = "week" | "fppg" | "ros" | "trend";
type Show = "free" | "all";

export default function NbaPlayersPage() {
  const [sort, setSort] = useState<Sort>("week");
  const [pos, setPos] = useState<Pos>("ALL");
  const [show, setShow] = useState<Show>("free");
  const q = $api.useQuery("get", "/api/nba/players", { params: { query: { sort, position: pos, show } } }, {
    placeholderData: (prev) => prev,
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Players &amp; free agents</h1>
        <div className="ml-auto flex flex-wrap gap-2">
          <Toggle value={show} options={[["free", "free agents"], ["all", "everyone"]] as const} onChange={setShow} />
          <Toggle
            value={sort}
            options={[["week", "this matchup"], ["fppg", "per game"], ["ros", "rest of season"], ["trend", "trending"]] as const}
            onChange={setSort}
          />
        </div>
      </div>
      <QueryView query={q}>{(d) => <Players d={d} pos={pos} setPos={setPos} />}</QueryView>
    </div>
  );
}

function Players({ d, pos, setPos }: { d: Api["NbaPlayersResponse"]; pos: Pos; setPos: (p: Pos) => void }) {
  if (d.rows.length === 0 && pos === "ALL") {
    return <EmptyState title="No players yet" hint="Waiting for the first NBA sync." />;
  }
  return (
    <>
      {d.show === "free" && d.streams.length > 0 && <Streams streams={d.streams} />}
      <Toggle value={pos} options={POS} onChange={setPos} />
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Player</th>
              <th className="num">FP/g</th>
              <th className="num hide-sm">Season</th>
              <th className="num hide-sm">L15</th>
              <th className="num">Games</th>
              <th className="num hide-sm">Next</th>
              <th className="num">Matchup</th>
              <th className="num">ROS</th>
              <th className="num hide-sm">PTS/REB/AST</th>
              <th className="num hide-sm">% rost</th>
            </tr>
          </thead>
          <tbody>
            {d.rows.map(({ player: p }) => (
              <tr key={p.extId}>
                <td>
                  <Who p={p}>
                    {d.show === "all" && p.ownerName && <span className="ml-1 text-[10px] text-[var(--muted)]">{p.ownerName}</span>}
                    {p.status === "WAIVERS" && <span className="ml-1 text-[10px] text-[var(--warn)]">waivers</span>}
                  </Who>
                </td>
                <td className="num font-semibold">{fmt(p.fppg)}</td>
                <td className="num hide-sm">{p.gpNow ? `${fmt(p.fppgNow)} (${p.gpNow})` : "–"}</td>
                <td className="num hide-sm">{p.gpL15 ? fmt(p.fppgL15) : "–"}</td>
                <td className="num">{p.gamesLeft}</td>
                <td className="num hide-sm">{p.gamesNext}</td>
                <td className="num">{fmt(p.weekPoints, 0)}</td>
                <td className="num">{fmt(p.ros, 0)}</td>
                <td className="num hide-sm text-xs">
                  {p.line.pts ? `${fmt(p.line.pts)}/${fmt(p.line.reb)}/${fmt(p.line.ast)}` : "–"}
                </td>
                <td className="num hide-sm">
                  {fmt(p.pctOwned, 0)}
                  {Math.abs(p.pctChange) >= 1 && (
                    <span className="ml-1 text-[10px]" style={{ color: p.pctChange > 0 ? "var(--good)" : "var(--bad)" }}>
                      {signed(p.pctChange, 0)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["FP/g", "per-game fantasy points the app plans with: ESPN's projection, handing over to the season average as games are played"],
          ["Season / L15", "this season's average (games) / the last 15 days"],
          ["Games / Next", "his team's games over the rest of this matchup / next matchup"],
          ["Matchup", "expected points over the days left in this matchup if he started every game"],
          ["ROS", "rest-of-season points (rate × games left × share expected played)"],
          ["% rost", "rostered across ESPN leagues, with this week's change — a trending pickup"],
          ["waivers", "recently dropped: a claim, not an instant add"],
        ]}
      />
    </>
  );
}
