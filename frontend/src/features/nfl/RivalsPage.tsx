import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading } from "@/shared/ui";
import { MatchupChip } from "./common";

const POS_SORT = ["QB", "RB", "WR", "TE", "K", "DST"];

export default function NflRivalsPage() {
  const q = $api.useQuery("get", "/api/nfl/rivals");
  return <QueryView query={q}>{(d) => <Rivals d={d} />}</QueryView>;
}

function Rivals({ d }: { d: Api["NflRivalsResponse"] }) {
  if (d.teams.length === 0) return <EmptyState title="No rosters yet" hint="Waiting for the first NFL sync." />;
  const o = d.opponent;
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Rivals</h1>
      {o && (
        <section className="space-y-2">
          <SubHeading>
            Week {d.week} — {o.name}
          </SubHeading>
          <p className="text-sm text-[var(--muted)]">
            Projected <b>{fmt(o.myProj, 0)}</b> – <b>{fmt(o.theirProj, 0)}</b>. {o.advice}
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Player</th>
                  <th>Matchup</th>
                  <th className="num">Proj</th>
                </tr>
              </thead>
              <tbody>
                {o.lineup.map(({ slot, player: p }, i) => (
                  <tr key={`${slot}-${p?.extId ?? i}`}>
                    <td className="text-xs text-[var(--muted)]">{slot}</td>
                    <td className="font-medium">
                      {p ? (
                        <>
                          <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{p && <MatchupChip p={p} />}</td>
                    <td className="num">{p ? fmt(p.weekPoints) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="space-y-2">
        <SubHeading>Every roster</SubHeading>
        <div className="grid gap-4 lg:grid-cols-2">
          {d.teams.map((mg) => (
            <RosterCard key={mg.teamId} mg={mg} />
          ))}
        </div>
      </section>

      <Legend
        items={[
          ["Proj", "projected PPR points this week"],
          ["Matchup colour", "1 (green) easy … 5 (red) hard — opponent defence vs that position"],
          ["Σ ROS", "roster's total projected points for the rest of the season"],
        ]}
      />
    </div>
  );
}

function RosterCard({ mg }: { mg: Api["NflManager"] }) {
  return (
    <div className={`card p-3 ${mg.isMine ? "ring-1 ring-[var(--accent)]" : ""}`}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-semibold">
          {mg.name} {mg.isMine && <span className="text-xs text-[var(--accent)]">(you)</span>}
        </span>
        <span className="text-sm text-[var(--muted)]">Σ ROS {fmt(mg.rosTotal, 0)}</span>
      </div>
      <div className="table-wrap">
        <table className="dtable text-xs">
          <tbody>
            {POS_SORT.flatMap((pos) => {
              const list = mg.byPos[pos] ?? [];
              return list.map((p, i) => (
                <tr key={p.extId}>
                  {i === 0 && (
                    <td rowSpan={list.length} className="align-top">
                      <PosBadge position={pos} small />
                    </td>
                  )}
                  <td className="font-medium">
                    {p.name}
                    {p.injury !== "ACTIVE" && <span className="ml-1 text-[10px] text-[var(--bad)]">{p.injury[0]}</span>}
                  </td>
                  <td className="text-[var(--muted)]">
                    {p.team}
                    {p.matchups[0]?.opp && <span className="ml-1 opacity-70">· {p.matchups[0].opp}</span>}
                  </td>
                  <td className="num font-semibold">{fmt(p.rosProj, 0)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
